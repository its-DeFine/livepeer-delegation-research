#!/usr/bin/env python3
"""
Filecoin (FIL) — lock + burn metrics (DePIN benchmark) and contrast vs Livepeer.

Goal
----
Provide a reproducible, on-chain "anti-extraction primitives" benchmark for Filecoin:

- A large portion of supply is locked as miner pledge collateral (Power actor).
- Fees/penalties accumulate in the Burnt Funds actor.
- Rewards are not designed to be instantly liquid (protocol-level vesting; not derived here).

Then contrast those on-chain primitives with Livepeer's on-chain extraction proxies:
- rewards claimed vs WithdrawStake (sell-pressure proxy),
- tight-window WithdrawStake → bridge → L1 → exchange routing traces.

We intentionally keep this lightweight and RPC-only:
- Filecoin JSON-RPC via Lotus methods (public endpoint default: Glif).
- Livepeer comparison uses local artifacts generated in this repo.

Outputs
-------
- research/filecoin-lock-burn-metrics.json
- research/filecoin-lock-burn-metrics.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 80

FILECOIN_RPC_DEFAULT = "https://api.node.glif.io"

# Filecoin builtin actors (ID addresses)
F_REWARD = "f02"
F_POWER = "f04"
F_MARKET = "f05"
F_BURNT_FUNDS = "f099"

# Epoch time is 30s ⇒ epochs/day = 86400/30 = 2880.
EPOCHS_PER_DAY = 2880

FIL_DECIMALS = 18
FIL_SCALE = Decimal(10) ** FIL_DECIMALS


class RpcError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/filecoin-lock-burn"):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(self.rpc_url, data=body, headers={"content-type": "application/json", "user-agent": self.user_agent}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except HTTPError as e:
            retry_after_s: int | None = None
            try:
                ra = e.headers.get("Retry-After")
                if isinstance(ra, str) and ra.strip().isdigit():
                    retry_after_s = int(ra.strip())
            except Exception:
                retry_after_s = None
            raise RpcError(
                f"HTTP {e.code}: {e.reason}",
                status_code=int(getattr(e, "code", 0)) or None,
                retry_after_s=retry_after_s,
            ) from e
        except URLError as e:
            raise RpcError(f"URL error: {e.reason}") from e
        except Exception as e:
            raise RpcError(f"RPC transport error: {e}") from e

        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise RpcError(f"invalid JSON-RPC response: {raw[:200]!r}") from e

        if isinstance(data, dict) and data.get("error"):
            raise RpcError(str(data["error"]))
        return data.get("result") if isinstance(data, dict) else data


def _rpc_with_retries(client: RpcClient, method: str, params: list, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return client.call(method, params)
        except RpcError as e:
            msg = str(e).lower()
            retryable_http = getattr(e, "status_code", None) in (429, 502, 503, 504)
            retryable = any(
                s in msg
                for s in (
                    "timeout",
                    "timed out",
                    "too many requests",
                    "rate limit",
                    "temporarily unavailable",
                    "service unavailable",
                    "bad gateway",
                    "gateway timeout",
                    "connection reset",
                    "internal error",
                )
            )
            if (not retryable and not retryable_http) or attempt == max_tries:
                raise

            sleep_s = min(2 ** (attempt - 1), 30.0)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))


def _atto_to_fil(atto: int) -> Decimal:
    return Decimal(int(atto)) / FIL_SCALE


def _format_fil(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _get_actor_balance_atto(client: RpcClient, actor: str) -> int:
    res = _rpc_with_retries(client, "Filecoin.StateGetActor", [actor, None])
    if not isinstance(res, dict) or "Balance" not in res:
        raise RpcError(f"unexpected StateGetActor response for {actor}: {res}")
    return int(str(res["Balance"]))


def _read_state(client: RpcClient, actor: str) -> Dict[str, Any]:
    res = _rpc_with_retries(client, "Filecoin.StateReadState", [actor, None])
    if not isinstance(res, dict) or "State" not in res or not isinstance(res["State"], dict):
        raise RpcError(f"unexpected StateReadState response for {actor}: {res}")
    return dict(res["State"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fil-rpc", default=os.environ.get("FILECOIN_RPC_URL") or FILECOIN_RPC_DEFAULT)
    parser.add_argument("--out-json", default="research/filecoin-lock-burn-metrics.json")
    parser.add_argument("--out-md", default="research/filecoin-lock-burn-metrics.md")
    parser.add_argument("--livepeer-rewards-withdraw-json", default="research/rewards-withdraw-timeseries.json")
    parser.add_argument("--livepeer-timing-traces-json", default="research/extraction-timing-traces.json")
    parser.add_argument("--livepeer-fingerprints-json", default="research/extraction-fingerprints.json")
    args = parser.parse_args()

    fil = RpcClient(str(args.fil_rpc), user_agent="livepeer-delegation-research/filecoin-lock-burn")

    head = _rpc_with_retries(fil, "Filecoin.ChainHead", [])
    height = int(head.get("Height") or 0) if isinstance(head, dict) else 0

    burnt_atto = _get_actor_balance_atto(fil, F_BURNT_FUNDS)
    reward_state = _read_state(fil, F_REWARD)
    power_state = _read_state(fil, F_POWER)
    market_state = _read_state(fil, F_MARKET)

    this_epoch_reward_atto = int(str(reward_state.get("ThisEpochReward") or "0"))
    total_power_reward_atto = int(str(reward_state.get("TotalStoragePowerReward") or "0"))

    total_pledge_atto = int(str(power_state.get("TotalPledgeCollateral") or "0"))
    this_epoch_pledge_atto = int(str(power_state.get("ThisEpochPledgeCollateral") or "0"))

    provider_locked_atto = int(str(market_state.get("TotalProviderLockedCollateral") or "0"))
    client_locked_atto = int(str(market_state.get("TotalClientLockedCollateral") or "0"))
    client_fee_atto = int(str(market_state.get("TotalClientStorageFee") or "0"))

    burnt_fil = _atto_to_fil(burnt_atto)
    total_pledge_fil = _atto_to_fil(total_pledge_atto)
    this_epoch_pledge_fil = _atto_to_fil(this_epoch_pledge_atto)
    provider_locked_fil = _atto_to_fil(provider_locked_atto)
    client_locked_fil = _atto_to_fil(client_locked_atto)
    client_fee_fil = _atto_to_fil(client_fee_atto)
    this_epoch_reward_fil = _atto_to_fil(this_epoch_reward_atto)
    total_power_reward_fil = _atto_to_fil(total_power_reward_atto)
    daily_reward_estimate_fil = this_epoch_reward_fil * Decimal(EPOCHS_PER_DAY)

    burn_vs_pledge = Decimal(0)
    if total_pledge_fil > 0:
        burn_vs_pledge = burnt_fil / total_pledge_fil

    # Livepeer contrast (local artifacts).
    lp_rewards_withdraw = _load_json(args.livepeer_rewards_withdraw_json)
    lp_traces = _load_json(args.livepeer_timing_traces_json)
    lp_fp = _load_json(args.livepeer_fingerprints_json)

    lp_tot = lp_rewards_withdraw.get("totals") if isinstance(lp_rewards_withdraw, dict) else {}
    lp_rewards_claimed_lpt = str((lp_tot or {}).get("rewards_lpt") or "")
    lp_withdraw_lpt = str((lp_tot or {}).get("withdraw_lpt") or "")

    lp_trace_tot = lp_traces.get("totals") if isinstance(lp_traces, dict) else {}
    lp_matched_to_exchange = int((lp_trace_tot or {}).get("matched_receipt_to_exchange") or 0)
    lp_senders = int((lp_trace_tot or {}).get("senders") or 0)

    lp_fp_tot = lp_fp.get("totals") if isinstance(lp_fp, dict) else {}
    lp_top50_proxy_withdrawn_lpt = str((lp_fp_tot or {}).get("proxy_rewards_withdrawn_lpt_total_top50") or "")

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "filecoin": {
            "rpc": str(args.fil_rpc),
            "head_height": int(height),
            "actors": {"reward": F_REWARD, "power": F_POWER, "market": F_MARKET, "burnt_funds": F_BURNT_FUNDS},
            "burnt_funds_fil": str(burnt_fil),
            "power_total_pledge_collateral_fil": str(total_pledge_fil),
            "power_this_epoch_pledge_collateral_fil": str(this_epoch_pledge_fil),
            "market_total_provider_locked_collateral_fil": str(provider_locked_fil),
            "market_total_client_locked_collateral_fil": str(client_locked_fil),
            "market_total_client_storage_fee_fil": str(client_fee_fil),
            "reward_this_epoch_reward_fil": str(this_epoch_reward_fil),
            "reward_total_storage_power_reward_fil": str(total_power_reward_fil),
            "daily_reward_estimate_fil": str(daily_reward_estimate_fil),
            "burn_vs_pledge_ratio": str(burn_vs_pledge),
        },
        "livepeer_contrast": {
            "rewards_withdraw_timeseries_json": str(args.livepeer_rewards_withdraw_json),
            "extraction_timing_traces_json": str(args.livepeer_timing_traces_json),
            "extraction_fingerprints_json": str(args.livepeer_fingerprints_json),
            "rewards_claimed_lpt_total": lp_rewards_claimed_lpt,
            "withdraw_stake_lpt_total": lp_withdraw_lpt,
            "timing_traces_senders": lp_senders,
            "timing_traces_matched_receipt_to_labeled_exchange": lp_matched_to_exchange,
            "top50_proxy_rewards_withdrawn_lpt_total": lp_top50_proxy_withdrawn_lpt,
        },
        "notes": [
            "FIL reward vesting and many other supply mechanics are protocol rules; this report focuses on on-chain balances and locked-fund aggregates surfaced by builtin actors.",
            "The Livepeer section is a contrast using existing on-chain evidence packs; it is not a claim that the same phenomena are directly comparable across chains.",
        ],
    }

    _write_json(args.out_json, out_json)

    lines: list[str] = []
    lines.append("---")
    lines.append('title: "Filecoin lock + burn metrics (DePIN benchmark)"')
    lines.append('description: "On-chain snapshot of Filecoin’s lock/burn primitives, contrasted with Livepeer’s on-chain extraction proxies."')
    lines.append('sidebar_label: "Filecoin vs Livepeer"')
    lines.append("---")
    lines.append("")
    lines.append("# Filecoin lock + burn metrics (DePIN benchmark)")
    lines.append("")
    lines.append("This evidence pack adds a DePIN reference point (Filecoin) to the Livepeer extraction discussion.")
    lines.append("")
    lines.append("## Filecoin: on-chain lock + burn primitives (snapshot)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Filecoin RPC: `{out_json['filecoin']['rpc']}`")
    lines.append(f"- Head height: `{out_json['filecoin']['head_height']}`")
    lines.append("")
    lines.append("Key on-chain quantities (FIL):")
    lines.append("")
    lines.append(f"- Burnt funds (actor `{F_BURNT_FUNDS}`): **{_format_fil(burnt_fil)} FIL**")
    lines.append(f"- Total pledge collateral locked (Power actor `{F_POWER}`): **{_format_fil(total_pledge_fil)} FIL**")
    lines.append(f"- This-epoch pledge collateral (Power actor `{F_POWER}`): **{_format_fil(this_epoch_pledge_fil)} FIL**")
    lines.append(f"- Provider locked collateral (Market actor `{F_MARKET}`): **{_format_fil(provider_locked_fil)} FIL**")
    lines.append(f"- Client locked collateral (Market actor `{F_MARKET}`): **{_format_fil(client_locked_fil)} FIL**")
    lines.append(f"- Client storage fees (Market actor `{F_MARKET}`): **{_format_fil(client_fee_fil)} FIL**")
    lines.append("")
    lines.append("Reward context (FIL):")
    lines.append("")
    lines.append(f"- This-epoch block reward (Reward actor `{F_REWARD}`): **{_format_fil(this_epoch_reward_fil)} FIL / epoch**")
    lines.append(f"- Daily reward estimate (epoch reward × {EPOCHS_PER_DAY}/day): **{_format_fil(daily_reward_estimate_fil)} FIL / day**")
    lines.append(f"- Total storage power rewards minted (Reward actor `{F_REWARD}`): **{_format_fil(total_power_reward_fil)} FIL**")
    lines.append("")
    lines.append("Interpretation:")
    lines.append("")
    lines.append("- Filecoin has large protocol-level **locked capital** (pledge collateral) and an explicit **burn sink** (burnt funds).")
    lines.append("- These mechanics raise the cost of “farm-and-dump” behavior by constraining liquidity and adding penalties/burn pathways.")
    lines.append("")
    lines.append("## Contrast: Livepeer extraction proxies (from our evidence packs)")
    lines.append("")
    lines.append("Livepeer differs structurally: inflation rewards can become liquid and be routed off-chain quickly (see timing traces).")
    lines.append("")
    lines.append(f"- Rewards claimed (total): **{lp_rewards_claimed_lpt} LPT** (`/research/rewards-withdraw-timeseries`)")
    lines.append(f"- `WithdrawStake` amount (total; includes principal): **{lp_withdraw_lpt} LPT** (`/research/rewards-withdraw-timeseries`)")
    lines.append(f"- Tight-window traces matched to labeled exchanges: **{lp_matched_to_exchange}** (across {lp_senders} senders) (`/research/extraction-timing-traces`)")
    lines.append(f"- Top-50 proxy rewards withdrawn (sum): **{lp_top50_proxy_withdrawn_lpt} LPT** (`/research/extraction-fingerprints`)")
    lines.append("")
    lines.append("What this suggests (high level):")
    lines.append("")
    lines.append("- Filecoin’s design has strong **on-chain friction** against immediate reward sell-through (locked collateral + burn sink).")
    lines.append("- Livepeer currently has weaker on-chain friction against immediate reward cashout; this is why we propose **reward-only escrow/vesting/forfeit** primitives for Livepeer.")
    lines.append("")
    lines.append("## Notes + limitations")
    lines.append("")
    lines.append("- This report does **not** attempt to infer “selling” for FIL; exchange deposits are not labeled here.")
    lines.append("- Filecoin reward vesting specifics are protocol rules; we focus on actor-reported locked/burn balances to keep the report RPC-only.")
    lines.append("- Cross-chain comparisons are qualitative: the goal is to compare primitives (lock/burn/penalty), not to claim identical market behavior.")
    lines.append("")
    lines.append(f"Raw output: see `{args.out_json}`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

