#!/usr/bin/env python3
"""
DePIN reward liquidity primitives — on-chain snapshot (multi-protocol).

Goal
----
Back the "reward vesting vs liquid rewards" discussion with direct, reproducible
on-chain parameter snapshots across representative networks:

- Livepeer (Arbitrum): unbonding period in rounds (liquidity friction, but no reward vesting table).
- The Graph (Ethereum): thawing period in blocks (principal liquidity friction).
- Akash (Cosmos): unbonding_time staking param (principal liquidity friction).
- Pocket (Shannon / poktroll): supplier unbonding period in sessions (principal liquidity friction).
- Filecoin: burn sink + pledge collateral + a miner's vesting schedule head (reward vesting primitive).

This is intentionally lightweight and RPC-only (no API keys; best-effort public endpoints).

Outputs
-------
- research/depin-liquidity-primitives-snapshot.json
- research/depin-liquidity-primitives-snapshot.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 80

# Ethereum-ish RPC defaults (public, best-effort).
ETH_RPC_DEFAULT = "https://ethereum.publicnode.com"
ARBITRUM_RPC_DEFAULT = "https://arb1.arbitrum.io/rpc"

# Cosmos REST defaults (Cosmos Directory).
AKASH_REST_DEFAULT = "https://rest.cosmos.directory/akash/cosmos/staking/v1beta1/params"

# Pocket (poktroll) REST defaults.
POCKET_REST_DEFAULT = "https://shannon-grove-api.mainnet.poktroll.com"

# Filecoin RPC default (Glif).
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

# Contracts
LIVEPEER_BONDING_MANAGER_ARB = "0x35Bcf3c30594191d53231E4FF333E8A770453e40"
THEGRAPH_STAKING_MAINNET = "0xF55041E37E12cD407ad00CE2910B8269B01263b9"

# Minimal ABI selectors (first 4 bytes of keccak256(signature)).
SEL_LIVEPEER_UNBONDING_PERIOD = "0x6cf6d675"  # unbondingPeriod()
SEL_THEGRAPH_THAWING_PERIOD = "0xcdc747dd"  # thawingPeriod()


class RpcError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class JsonRpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/depin-liquidity-primitives"):
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


def _rpc_with_retries(client: JsonRpcClient, method: str, params: list, *, max_tries: int = 8) -> Any:
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


def _hex_to_int(hex_str: str) -> int:
    s = (hex_str or "").strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if s == "":
        return 0
    return int(s, 16)


def _eth_block_number(client: JsonRpcClient) -> int:
    return _hex_to_int(str(_rpc_with_retries(client, "eth_blockNumber", [])))


def _eth_call_int(client: JsonRpcClient, *, to_addr: str, data: str, block_tag: str = "latest") -> int:
    res = _rpc_with_retries(client, "eth_call", [{"to": to_addr, "data": data}, block_tag])
    return _hex_to_int(str(res))


def _atto_to_fil(atto: int) -> Decimal:
    return Decimal(int(atto)) / FIL_SCALE


def _format_fil(x: Decimal, *, places: int = 6) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _fetch_json(url: str, *, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/depin-liquidity-primitives") -> Any:
    req = Request(url, headers={"user-agent": user_agent})
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except Exception as e:
        raise RuntimeError(f"failed to fetch {url}: {e}") from e
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"invalid JSON from {url}: {raw[:200]!r}") from e


def _filecoin_get_actor_balance_atto(client: JsonRpcClient, actor: str) -> int:
    res = _rpc_with_retries(client, "Filecoin.StateGetActor", [actor, None])
    if not isinstance(res, dict) or "Balance" not in res:
        raise RpcError(f"unexpected StateGetActor response for {actor}: {res}")
    return int(str(res["Balance"]))


def _filecoin_read_state(client: JsonRpcClient, actor: str) -> Dict[str, Any]:
    res = _rpc_with_retries(client, "Filecoin.StateReadState", [actor, None])
    if not isinstance(res, dict) or "State" not in res or not isinstance(res["State"], dict):
        raise RpcError(f"unexpected StateReadState response for {actor}: {res}")
    return dict(res["State"])


def _parse_akash_unbonding_time_seconds(x: str) -> int:
    # Cosmos REST typically encodes Duration as "<seconds>s"
    s = (x or "").strip()
    if s.endswith("s") and s[:-1].isdigit():
        return int(s[:-1])
    if s.isdigit():
        return int(s)
    raise ValueError(f"unexpected unbonding_time format: {x!r}")


def _parse_rfc3339_nanos(s: str) -> datetime:
    x = (s or "").strip()
    if x.endswith("Z"):
        x = x[:-1]
    if "." in x:
        base, frac = x.split(".", 1)
        frac = frac[:6]  # microseconds
        x = f"{base}.{frac}"
    dt = datetime.fromisoformat(x)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _pocket_url(rest_base: str, path: str) -> str:
    base = rest_base.rstrip("/")
    p = path if path.startswith("/") else "/" + path
    return base + p


def _pocket_get_block(rest_base: str, height: str) -> dict[str, Any]:
    url = _pocket_url(rest_base, f"/cosmos/base/tendermint/v1beta1/blocks/{height}")
    res = _fetch_json(url, user_agent="livepeer-delegation-research/depin-liquidity-primitives-pocket")
    if not isinstance(res, dict):
        raise RuntimeError(f"unexpected pocket block response: {res}")
    if "code" in res and int(res.get("code") or 0) != 0:
        raise RuntimeError(str(res.get("message") or res))
    return res


def _pocket_estimate_block_time_seconds(rest_base: str, *, sample_blocks: int = 1000) -> dict[str, Any]:
    latest = _pocket_get_block(rest_base, "latest")
    hdr = ((latest.get("block") or {}).get("header") or {}) if isinstance(latest.get("block"), dict) else {}
    latest_h = int(str(hdr.get("height") or "0"))
    latest_t = str(hdr.get("time") or "")

    older_h = max(1, latest_h - int(sample_blocks))
    try:
        older = _pocket_get_block(rest_base, str(older_h))
    except Exception as e:
        m = re.search(r"lowest height is (\\d+)", str(e))
        if not m:
            raise
        older_h = int(m.group(1))
        older = _pocket_get_block(rest_base, str(older_h))

    o_hdr = ((older.get("block") or {}).get("header") or {}) if isinstance(older.get("block"), dict) else {}
    older_t = str(o_hdr.get("time") or "")

    lt = _parse_rfc3339_nanos(latest_t)
    ot = _parse_rfc3339_nanos(older_t)
    delta_s = (lt - ot).total_seconds()
    blocks = max(0, latest_h - older_h)
    avg = (delta_s / blocks) if blocks else 0.0

    return {
        "latest_height": int(latest_h),
        "older_height": int(older_h),
        "blocks_delta": int(blocks),
        "seconds_delta": float(delta_s),
        "avg_block_time_seconds": float(avg),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eth-rpc", default=os.environ.get("ETH_RPC_URL") or ETH_RPC_DEFAULT)
    parser.add_argument("--arb-rpc", default=os.environ.get("ARBITRUM_RPC_URL") or ARBITRUM_RPC_DEFAULT)
    parser.add_argument("--akash-rest", default=os.environ.get("AKASH_REST_URL") or AKASH_REST_DEFAULT)
    parser.add_argument("--pocket-rest", default=os.environ.get("POCKET_REST_URL") or POCKET_REST_DEFAULT)
    parser.add_argument("--fil-rpc", default=os.environ.get("FILECOIN_RPC_URL") or FILECOIN_RPC_DEFAULT)
    parser.add_argument("--fil-miner", default=os.environ.get("FILECOIN_SAMPLE_MINER") or "f01729333")
    parser.add_argument("--out-json", default="research/depin-liquidity-primitives-snapshot.json")
    parser.add_argument("--out-md", default="research/depin-liquidity-primitives-snapshot.md")
    args = parser.parse_args()

    generated_at = datetime.now(tz=timezone.utc).isoformat()

    # Livepeer (Arbitrum) — unbonding period in rounds.
    arb = JsonRpcClient(str(args.arb_rpc), user_agent="livepeer-delegation-research/depin-liquidity-primitives-arb")
    livepeer_unbonding_rounds = _eth_call_int(arb, to_addr=LIVEPEER_BONDING_MANAGER_ARB, data=SEL_LIVEPEER_UNBONDING_PERIOD)

    # The Graph (Ethereum) — thawing period in blocks.
    eth = JsonRpcClient(str(args.eth_rpc), user_agent="livepeer-delegation-research/depin-liquidity-primitives-eth")
    eth_block = _eth_block_number(eth)
    thegraph_thawing_blocks = _eth_call_int(eth, to_addr=THEGRAPH_STAKING_MAINNET, data=SEL_THEGRAPH_THAWING_PERIOD)
    # Approx only; depends on chain conditions.
    eth_block_time_s_est = 12.0
    thegraph_thawing_days_est = (thegraph_thawing_blocks * eth_block_time_s_est) / 86400.0 if thegraph_thawing_blocks else 0.0

    # Akash (Cosmos) — unbonding_time param.
    ak = _fetch_json(str(args.akash_rest))
    ak_params = (ak or {}).get("params") if isinstance(ak, dict) else {}
    ak_unbonding_time = str((ak_params or {}).get("unbonding_time") or "")
    ak_unbonding_s = _parse_akash_unbonding_time_seconds(ak_unbonding_time)

    # Pocket (Shannon / poktroll) — unbonding periods in sessions + session sizing.
    pocket_rest = str(args.pocket_rest)
    pocket_shared = _fetch_json(
        _pocket_url(pocket_rest, "/pokt-network/poktroll/shared/params"),
        user_agent="livepeer-delegation-research/depin-liquidity-primitives-pocket",
    )
    pocket_shared_params = (pocket_shared or {}).get("params") if isinstance(pocket_shared, dict) else {}
    pocket_num_blocks_per_session = int(str((pocket_shared_params or {}).get("num_blocks_per_session") or "0") or 0)
    pocket_supplier_unbonding_sessions = int(str((pocket_shared_params or {}).get("supplier_unbonding_period_sessions") or "0") or 0)
    pocket_block_time = _pocket_estimate_block_time_seconds(pocket_rest, sample_blocks=1000)
    pocket_avg_block_time_s = float((pocket_block_time or {}).get("avg_block_time_seconds") or 0.0)
    pocket_session_s = pocket_avg_block_time_s * pocket_num_blocks_per_session if pocket_avg_block_time_s and pocket_num_blocks_per_session else 0.0
    pocket_supplier_unbond_s = pocket_session_s * pocket_supplier_unbonding_sessions if pocket_session_s and pocket_supplier_unbonding_sessions else 0.0

    # Filecoin — burn sink + pledge collateral + miner vesting schedule head.
    fil = JsonRpcClient(str(args.fil_rpc), user_agent="livepeer-delegation-research/depin-liquidity-primitives-fil")
    head = _rpc_with_retries(fil, "Filecoin.ChainHead", [])
    fil_height = int(head.get("Height") or 0) if isinstance(head, dict) else 0

    burnt_atto = _filecoin_get_actor_balance_atto(fil, F_BURNT_FUNDS)
    reward_state = _filecoin_read_state(fil, F_REWARD)
    power_state = _filecoin_read_state(fil, F_POWER)
    market_state = _filecoin_read_state(fil, F_MARKET)
    miner_state = _filecoin_read_state(fil, str(args.fil_miner))

    this_epoch_reward_atto = int(str(reward_state.get("ThisEpochReward") or "0"))
    total_power_reward_atto = int(str(reward_state.get("TotalStoragePowerReward") or "0"))
    total_pledge_atto = int(str(power_state.get("TotalPledgeCollateral") or "0"))

    provider_locked_atto = int(str(market_state.get("TotalProviderLockedCollateral") or "0"))

    miner_locked_atto = int(str(miner_state.get("LockedFunds") or "0"))
    miner_initial_pledge_atto = int(str(miner_state.get("InitialPledge") or "0"))
    miner_vesting = miner_state.get("VestingFunds") or {}
    vest_head = (miner_vesting or {}).get("Head") if isinstance(miner_vesting, dict) else None
    vest_tail = (miner_vesting or {}).get("Tail") if isinstance(miner_vesting, dict) else None

    vest_head_epoch = int((vest_head or {}).get("Epoch") or 0) if isinstance(vest_head, dict) else 0
    vest_head_amount_atto = int(str((vest_head or {}).get("Amount") or "0")) if isinstance(vest_head, dict) else 0
    vest_tail_cid = str((vest_tail or {}).get("/") or "") if isinstance(vest_tail, dict) else ""

    burnt_fil = _atto_to_fil(burnt_atto)
    total_pledge_fil = _atto_to_fil(total_pledge_atto)
    provider_locked_fil = _atto_to_fil(provider_locked_atto)
    this_epoch_reward_fil = _atto_to_fil(this_epoch_reward_atto)
    total_power_reward_fil = _atto_to_fil(total_power_reward_atto)
    daily_reward_estimate_fil = this_epoch_reward_fil * Decimal(EPOCHS_PER_DAY)

    miner_locked_fil = _atto_to_fil(miner_locked_atto)
    miner_initial_pledge_fil = _atto_to_fil(miner_initial_pledge_atto)
    vest_head_amount_fil = _atto_to_fil(vest_head_amount_atto)

    out_json: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "livepeer": {
            "chain": "arbitrum",
            "rpc": str(args.arb_rpc),
            "bonding_manager": LIVEPEER_BONDING_MANAGER_ARB,
            "unbonding_period_rounds": int(livepeer_unbonding_rounds),
        },
        "thegraph": {
            "chain": "ethereum",
            "rpc": str(args.eth_rpc),
            "block_number": int(eth_block),
            "staking_contract": THEGRAPH_STAKING_MAINNET,
            "thawing_period_blocks": int(thegraph_thawing_blocks),
            "block_time_seconds_estimate": eth_block_time_s_est,
            "thawing_period_days_estimate": thegraph_thawing_days_est,
        },
        "akash": {
            "rest": str(args.akash_rest),
            "unbonding_time": ak_unbonding_time,
            "unbonding_time_seconds": int(ak_unbonding_s),
            "bond_denom": (ak_params or {}).get("bond_denom"),
            "max_validators": (ak_params or {}).get("max_validators"),
            "max_entries": (ak_params or {}).get("max_entries"),
            "historical_entries": (ak_params or {}).get("historical_entries"),
            "min_commission_rate": (ak_params or {}).get("min_commission_rate"),
        },
        "pocket": {
            "rest": pocket_rest,
            "shared_params_endpoint": "/pokt-network/poktroll/shared/params",
            "block_latest_endpoint": "/cosmos/base/tendermint/v1beta1/blocks/latest",
            "num_blocks_per_session": int(pocket_num_blocks_per_session),
            "supplier_unbonding_period_sessions": int(pocket_supplier_unbonding_sessions),
            "supplier_unbonding_period_blocks": int(pocket_supplier_unbonding_sessions * pocket_num_blocks_per_session)
            if pocket_supplier_unbonding_sessions and pocket_num_blocks_per_session
            else 0,
            "block_time_estimate": pocket_block_time,
            "session_seconds_estimate": float(pocket_session_s),
            "supplier_unbonding_seconds_estimate": float(pocket_supplier_unbond_s),
        },
        "filecoin": {
            "rpc": str(args.fil_rpc),
            "head_height": int(fil_height),
            "actors": {"reward": F_REWARD, "power": F_POWER, "market": F_MARKET, "burnt_funds": F_BURNT_FUNDS},
            "burnt_funds_fil": str(burnt_fil),
            "power_total_pledge_collateral_fil": str(total_pledge_fil),
            "market_total_provider_locked_collateral_fil": str(provider_locked_fil),
            "reward_this_epoch_reward_fil": str(this_epoch_reward_fil),
            "reward_total_storage_power_reward_fil": str(total_power_reward_fil),
            "daily_reward_estimate_fil": str(daily_reward_estimate_fil),
            "sample_miner": str(args.fil_miner),
            "sample_miner_locked_funds_fil": str(miner_locked_fil),
            "sample_miner_initial_pledge_fil": str(miner_initial_pledge_fil),
            "sample_miner_vesting_head": {"epoch": int(vest_head_epoch), "amount_fil": str(vest_head_amount_fil)},
            "sample_miner_vesting_tail_cid": vest_tail_cid,
        },
        "notes": [
            "This snapshot focuses on simple on-chain primitives (unbond/thaw parameters, locked-funds actors, miner vesting table head).",
            "Estimates (e.g., days from blocks) use approximate block times; treat them as directional.",
            "Presence of an unbond/thaw period is not the same as protocol-level linear reward vesting; they act on different buckets (principal vs rewards).",
        ],
    }

    _write_json(args.out_json, out_json)

    lines: list[str] = []
    lines.append("---")
    lines.append('title: "DePIN liquidity primitives snapshot (on-chain)"')
    lines.append('description: "On-chain snapshot of reward/principal liquidity primitives across Livepeer, The Graph, Akash, Pocket, and Filecoin."')
    lines.append("---")
    lines.append("")
    lines.append("# DePIN liquidity primitives snapshot (on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append("")
    lines.append("This is an evidence pack used to ground the DePIN tokenomics comparison around **time-gated liquidity** (unbonding/thawing) and **reward vesting** primitives.")
    lines.append("")
    lines.append("## Livepeer (Arbitrum): unbonding period (rounds)")
    lines.append("")
    lines.append(f"- RPC: `{args.arb_rpc}`")
    lines.append(f"- BondingManager (proxy): `{LIVEPEER_BONDING_MANAGER_ARB}`")
    lines.append(f"- `unbondingPeriod()`: **{livepeer_unbonding_rounds} rounds**")
    lines.append("")
    lines.append("Interpretation: this is **principal liquidity friction** (exit delay). It does not, by itself, enforce linear reward vesting.")
    lines.append("")
    lines.append("## The Graph (Ethereum): thawing period (blocks)")
    lines.append("")
    lines.append(f"- RPC: `{args.eth_rpc}`")
    lines.append(f"- Block number: `{eth_block}`")
    lines.append(f"- Staking contract: `{THEGRAPH_STAKING_MAINNET}`")
    lines.append(f"- `thawingPeriod()`: **{thegraph_thawing_blocks:,} blocks** (~{thegraph_thawing_days_est:.1f} days @ {eth_block_time_s_est:.0f}s/block)")
    lines.append("")
    lines.append("Interpretation: this is also **principal liquidity friction** (unstake → wait → withdraw).")
    lines.append("")
    lines.append("## Akash (Cosmos): staking params (`unbonding_time`)")
    lines.append("")
    lines.append(f"- REST: `{args.akash_rest}`")
    lines.append(f"- `unbonding_time`: **{ak_unbonding_time}** (~{ak_unbonding_s/86400.0:.1f} days)")
    lines.append(f"- `bond_denom`: `{(ak_params or {}).get('bond_denom')}`")
    lines.append(f"- `max_validators`: `{(ak_params or {}).get('max_validators')}`")
    lines.append("")
    lines.append("Interpretation: Cosmos-style staking typically enforces principal unbonding delays, but does not default to months-long linear reward vesting.")
    lines.append("")
    lines.append("## Pocket (Shannon / poktroll): supplier unbonding period (sessions)")
    lines.append("")
    lines.append(f"- REST: `{pocket_rest}`")
    lines.append("- Shared params: `/pokt-network/poktroll/shared/params`")
    lines.append(f"- `num_blocks_per_session`: **{pocket_num_blocks_per_session:,}**")
    lines.append(f"- `supplier_unbonding_period_sessions`: **{pocket_supplier_unbonding_sessions:,}**")
    if pocket_num_blocks_per_session and pocket_supplier_unbonding_sessions:
        lines.append(f"- Supplier unbonding (blocks): **{pocket_supplier_unbonding_sessions * pocket_num_blocks_per_session:,}**")
    if pocket_avg_block_time_s:
        lines.append(f"- Estimated block time: **{pocket_avg_block_time_s:.2f}s** (over {pocket_block_time.get('blocks_delta')} blocks)")
    if pocket_session_s:
        lines.append(f"- Estimated session duration: **~{pocket_session_s/3600.0:.2f} hours**")
    if pocket_supplier_unbond_s:
        lines.append(f"- Estimated supplier unbonding duration: **~{pocket_supplier_unbond_s/86400.0:.1f} days**")
    lines.append("")
    lines.append("Interpretation: Pocket’s unbonding sessions act as **principal liquidity friction** (unstake → wait → withdraw), similar in class to Cosmos-style unbonding.")
    lines.append("")
    lines.append("## Filecoin: burn sink + locked pledge + miner vesting schedule head")
    lines.append("")
    lines.append(f"- RPC: `{args.fil_rpc}`")
    lines.append(f"- Head height: `{fil_height}`")
    lines.append("")
    lines.append("Network-level lock/burn quantities (FIL):")
    lines.append("")
    lines.append(f"- Burnt funds (actor `{F_BURNT_FUNDS}`): **{_format_fil(burnt_fil)} FIL**")
    lines.append(f"- Total pledge collateral locked (Power actor `{F_POWER}`): **{_format_fil(total_pledge_fil)} FIL**")
    lines.append(f"- Provider locked collateral (Market actor `{F_MARKET}`): **{_format_fil(provider_locked_fil)} FIL**")
    lines.append("")
    lines.append("Sample miner vesting state (FIL):")
    lines.append("")
    lines.append(f"- Miner actor: `{args.fil_miner}`")
    lines.append(f"- `LockedFunds`: **{_format_fil(miner_locked_fil)} FIL**")
    lines.append(f"- `InitialPledge`: **{_format_fil(miner_initial_pledge_fil)} FIL**")
    lines.append(f"- `VestingFunds.Head`: epoch `{vest_head_epoch}` amount **{_format_fil(vest_head_amount_fil)} FIL**")
    if vest_tail_cid:
        lines.append(f"- `VestingFunds.Tail` CID: `{vest_tail_cid}` (indicates additional vesting entries beyond the head)")
    lines.append("")
    lines.append("Interpretation: Filecoin exposes explicit **locked funds** + a **vesting schedule** component at the miner actor level, which is closer to a true “reward vesting” primitive than an unbonding/thaw delay alone.")
    lines.append("")
    lines.append(f"Raw output: see `{args.out_json}`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
