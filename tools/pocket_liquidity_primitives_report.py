#!/usr/bin/env python3
"""
Pocket Network (Shannon / poktroll) — reward + liquidity primitives (on-chain).

Goal
----
Add a Livepeer-comparable DePIN reference point where participation involves
staking/unbonding, but (as far as exposed on-chain params show) *not* protocol-
level linear reward vesting.

We capture:
- Unbonding periods (in sessions) and session sizing (blocks/session).
- A best-effort estimate of block time and therefore (rough) session + unbonding duration.
- Tokenomics mint allocation parameters (who gets minted rewards).
- Minimum stake parameters for key roles.

This is intentionally lightweight and RPC/REST-only (no API keys; best-effort public endpoints).

Outputs
-------
- research/pocket-liquidity-primitives.json
- research/pocket-liquidity-primitives.md
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

POCKET_REST_DEFAULT = "https://shannon-grove-api.mainnet.poktroll.com"

UP0KT_DECIMALS = 6
UPOKT_SCALE = Decimal(10) ** UP0KT_DECIMALS


class FetchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


def _fetch_json(url: str, *, timeout_s: int = 60, user_agent: str = "livepeer-delegation-research/pocket-liquidity-primitives") -> Any:
    req = Request(url, headers={"user-agent": user_agent})
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except HTTPError as e:
        retry_after_s: int | None = None
        try:
            ra = e.headers.get("Retry-After")
            if isinstance(ra, str) and ra.strip().isdigit():
                retry_after_s = int(ra.strip())
        except Exception:
            retry_after_s = None
        body = b""
        try:
            body = e.read()  # type: ignore[attr-defined]
        except Exception:
            body = b""
        raise FetchError(
            f"HTTP {e.code}: {e.reason} ({url}) body={body[:200]!r}",
            status_code=int(getattr(e, "code", 0)) or None,
            retry_after_s=retry_after_s,
        ) from e
    except URLError as e:
        raise FetchError(f"URL error: {e.reason} ({url})") from e
    except Exception as e:
        raise FetchError(f"fetch error: {e} ({url})") from e

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise FetchError(f"invalid JSON from {url}: {raw[:200]!r}") from e


def _fetch_with_retries(url: str, *, max_tries: int = 8) -> Any:
    for attempt in range(1, max_tries + 1):
        try:
            return _fetch_json(url)
        except FetchError as e:
            msg = str(e).lower()
            retryable_http = getattr(e, "status_code", None) in (429, 502, 503, 504)
            retryable = any(s in msg for s in ("timeout", "timed out", "too many requests", "rate limit", "bad gateway", "service unavailable"))
            if (not retryable and not retryable_http) or attempt == max_tries:
                raise

            sleep_s = min(2 ** (attempt - 1), 30.0)
            retry_after_s = getattr(e, "retry_after_s", None)
            if isinstance(retry_after_s, int) and retry_after_s > 0:
                sleep_s = max(sleep_s, float(retry_after_s))
            sleep_s = sleep_s * (1 + random.uniform(-0.15, 0.15))
            time.sleep(max(0.5, sleep_s))


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


def _as_int(x: Any) -> int:
    try:
        return int(str(x))
    except Exception:
        return 0


def _u_to_pokt(amount_u: int) -> Decimal:
    return Decimal(int(amount_u)) / UPOKT_SCALE


def _format_pokt(x: Decimal, *, places: int = 6) -> str:
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


def _poktroll_url(rest_base: str, path: str) -> str:
    base = rest_base.rstrip("/")
    p = path if path.startswith("/") else "/" + path
    return base + p


def _get_block(rest_base: str, height: str) -> dict[str, Any]:
    url = _poktroll_url(rest_base, f"/cosmos/base/tendermint/v1beta1/blocks/{height}")
    res = _fetch_with_retries(url)
    if not isinstance(res, dict):
        raise FetchError(f"unexpected block response: {res}")
    return res


def _estimate_block_time_seconds(rest_base: str, *, sample_blocks: int = 1000) -> dict[str, Any]:
    latest = _get_block(rest_base, "latest")
    hdr = ((latest.get("block") or {}).get("header") or {}) if isinstance(latest.get("block"), dict) else {}
    latest_height = _as_int(hdr.get("height"))
    latest_time = str(hdr.get("time") or "")

    target_height = max(1, latest_height - int(sample_blocks))
    older: dict[str, Any] | None = None
    older_height = target_height

    try:
        older = _get_block(rest_base, str(target_height))
    except FetchError as e:
        # Common when node is pruned: parse the "lowest height is N" hint.
        m = re.search(r"lowest height is (\\d+)", str(e))
        if m:
            older_height = int(m.group(1))
            older = _get_block(rest_base, str(older_height))
        else:
            raise

    o_hdr = ((older.get("block") or {}).get("header") or {}) if isinstance(older.get("block"), dict) else {}
    older_height = _as_int(o_hdr.get("height"))
    older_time = str(o_hdr.get("time") or "")

    lt = _parse_rfc3339_nanos(latest_time)
    ot = _parse_rfc3339_nanos(older_time)
    delta_s = (lt - ot).total_seconds()
    blocks = max(0, latest_height - older_height)
    avg = (delta_s / blocks) if blocks else 0.0

    return {
        "latest_height": int(latest_height),
        "latest_time_utc": latest_time,
        "older_height": int(older_height),
        "older_time_utc": older_time,
        "blocks_delta": int(blocks),
        "seconds_delta": float(delta_s),
        "avg_block_time_seconds": float(avg),
        "notes": [
            "Block time is estimated from on-chain block timestamps over a recent window.",
            "The REST endpoint may be pruned; if so, the sample window falls back to the lowest available block height.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rest", default=os.environ.get("POCKET_REST_URL") or POCKET_REST_DEFAULT)
    parser.add_argument("--out-json", default="research/pocket-liquidity-primitives.json")
    parser.add_argument("--out-md", default="research/pocket-liquidity-primitives.md")
    args = parser.parse_args()

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    rest = str(args.rest).rstrip("/")

    shared = _fetch_with_retries(_poktroll_url(rest, "/pokt-network/poktroll/shared/params"))
    tokenomics = _fetch_with_retries(_poktroll_url(rest, "/pokt-network/poktroll/tokenomics/params"))
    supplier = _fetch_with_retries(_poktroll_url(rest, "/pokt-network/poktroll/supplier/params"))
    application = _fetch_with_retries(_poktroll_url(rest, "/pokt-network/poktroll/application/params"))
    gateway = _fetch_with_retries(_poktroll_url(rest, "/pokt-network/poktroll/gateway/params"))

    shared_params = (shared or {}).get("params") if isinstance(shared, dict) else {}
    tok_params = (tokenomics or {}).get("params") if isinstance(tokenomics, dict) else {}
    supplier_params = (supplier or {}).get("params") if isinstance(supplier, dict) else {}
    application_params = (application or {}).get("params") if isinstance(application, dict) else {}
    gateway_params = (gateway or {}).get("params") if isinstance(gateway, dict) else {}

    num_blocks_per_session = _as_int((shared_params or {}).get("num_blocks_per_session"))
    supplier_unbonding_sessions = _as_int((shared_params or {}).get("supplier_unbonding_period_sessions"))
    application_unbonding_sessions = _as_int((shared_params or {}).get("application_unbonding_period_sessions"))
    gateway_unbonding_sessions = _as_int((shared_params or {}).get("gateway_unbonding_period_sessions"))

    # Best-effort block-time estimate.
    block_time = _estimate_block_time_seconds(rest, sample_blocks=1000)
    avg_block_time_s = float(block_time.get("avg_block_time_seconds") or 0.0)

    def session_seconds_est() -> float:
        if not num_blocks_per_session or not avg_block_time_s:
            return 0.0
        return float(num_blocks_per_session) * avg_block_time_s

    session_s = session_seconds_est()

    def unbond_seconds_est(sessions: int) -> float:
        if not sessions or not session_s:
            return 0.0
        return float(sessions) * session_s

    supplier_unbond_s = unbond_seconds_est(supplier_unbonding_sessions)
    application_unbond_s = unbond_seconds_est(application_unbonding_sessions)
    gateway_unbond_s = unbond_seconds_est(gateway_unbonding_sessions)

    def stake_u_amount(params: dict[str, Any] | None) -> int:
        if not params:
            return 0
        ms = params.get("min_stake")
        if not isinstance(ms, dict):
            return 0
        if str(ms.get("denom") or "").lower() != "upokt":
            return 0
        return _as_int(ms.get("amount"))

    supplier_min_stake_u = stake_u_amount(supplier_params)
    application_min_stake_u = stake_u_amount(application_params)
    gateway_min_stake_u = stake_u_amount(gateway_params)

    supplier_min_stake_pokt = _u_to_pokt(supplier_min_stake_u)
    application_min_stake_pokt = _u_to_pokt(application_min_stake_u)
    gateway_min_stake_pokt = _u_to_pokt(gateway_min_stake_u)

    out_json: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "pocket": {
            "network": "shannon (poktroll)",
            "rest": rest,
            "endpoints": {
                "shared_params": "/pokt-network/poktroll/shared/params",
                "tokenomics_params": "/pokt-network/poktroll/tokenomics/params",
                "supplier_params": "/pokt-network/poktroll/supplier/params",
                "application_params": "/pokt-network/poktroll/application/params",
                "gateway_params": "/pokt-network/poktroll/gateway/params",
                "block_latest": "/cosmos/base/tendermint/v1beta1/blocks/latest",
            },
            "shared_params": shared_params,
            "tokenomics_params": tok_params,
            "supplier_params": supplier_params,
            "application_params": application_params,
            "gateway_params": gateway_params,
            "derived": {
                "num_blocks_per_session": int(num_blocks_per_session),
                "supplier_unbonding_period_sessions": int(supplier_unbonding_sessions),
                "application_unbonding_period_sessions": int(application_unbonding_sessions),
                "gateway_unbonding_period_sessions": int(gateway_unbonding_sessions),
                "supplier_unbonding_period_blocks": int(supplier_unbonding_sessions * num_blocks_per_session) if supplier_unbonding_sessions and num_blocks_per_session else 0,
                "block_time_estimate": block_time,
                "session_seconds_estimate": float(session_s),
                "supplier_unbonding_seconds_estimate": float(supplier_unbond_s),
                "application_unbonding_seconds_estimate": float(application_unbond_s),
                "gateway_unbonding_seconds_estimate": float(gateway_unbond_s),
                "supplier_min_stake_upokt": int(supplier_min_stake_u),
                "application_min_stake_upokt": int(application_min_stake_u),
                "gateway_min_stake_upokt": int(gateway_min_stake_u),
                "supplier_min_stake_pokt": str(supplier_min_stake_pokt),
                "application_min_stake_pokt": str(application_min_stake_pokt),
                "gateway_min_stake_pokt": str(gateway_min_stake_pokt),
            },
        },
        "notes": [
            "This evidence pack focuses on on-chain parameters that affect reward/principal liquidity (unbonding delays) and reward distribution (mint allocation).",
            "It does not attempt to infer POKT selling; exchange address labels are chain-specific and not included here.",
        ],
    }

    _write_json(args.out_json, out_json)

    def fmt_duration(seconds: float) -> str:
        if not seconds:
            return "n/a"
        days = seconds / 86400.0
        hours = seconds / 3600.0
        if days >= 2:
            return f"~{days:.1f} days"
        return f"~{hours:.1f} hours"

    lines: list[str] = []
    lines.append("---")
    lines.append('title: "Pocket (Shannon) liquidity primitives (on-chain)"')
    lines.append('description: "On-chain snapshot of Pocket Network (poktroll) unbonding delays + mint allocation parameters, as a Livepeer-comparable DePIN reference point."')
    lines.append('sidebar_label: "Pocket: liquidity primitives"')
    lines.append("---")
    lines.append("")
    lines.append("# Pocket (Shannon) liquidity primitives (on-chain)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- REST: `{rest}`")
    lines.append("")
    lines.append("This evidence pack captures Pocket Shannon (poktroll) parameters relevant to **reward/principal liquidity** and **reward distribution**.")
    lines.append("")
    lines.append("## Unbonding + session sizing")
    lines.append("")
    lines.append(f"- `num_blocks_per_session`: **{num_blocks_per_session:,}**")
    lines.append(f"- `supplier_unbonding_period_sessions`: **{supplier_unbonding_sessions:,}** (≈ **{supplier_unbonding_sessions * num_blocks_per_session:,} blocks**)")
    lines.append(f"- `application_unbonding_period_sessions`: **{application_unbonding_sessions:,}**")
    lines.append(f"- `gateway_unbonding_period_sessions`: **{gateway_unbonding_sessions:,}**")
    lines.append("")
    lines.append("Best-effort time estimates from on-chain block timestamps:")
    lines.append("")
    lines.append(f"- Estimated block time: **{avg_block_time_s:.2f}s** (from {block_time.get('blocks_delta')} blocks)")
    lines.append(f"- Estimated session duration: **{fmt_duration(session_s)}**")
    lines.append(f"- Estimated supplier unbonding duration: **{fmt_duration(supplier_unbond_s)}**")
    lines.append("")
    lines.append("Interpretation: this is primarily **principal liquidity friction** (unstake → wait → withdraw). The exposed params do not indicate protocol-level linear reward vesting.")
    lines.append("")
    lines.append("## Mint allocation (reward distribution)")
    lines.append("")
    lines.append("- Mint allocation percentages (of inflation):")
    ma = tok_params.get("mint_allocation_percentages") if isinstance(tok_params, dict) else None
    if isinstance(ma, dict):
        for k in sorted(ma.keys()):
            lines.append(f"  - `{k}`: **{ma[k]}**")
    else:
        lines.append("  - (missing)")
    lines.append("")
    lines.append("- Mint-equals-burn claim distribution (if applicable):")
    meb = tok_params.get("mint_equals_burn_claim_distribution") if isinstance(tok_params, dict) else None
    if isinstance(meb, dict):
        for k in sorted(meb.keys()):
            lines.append(f"  - `{k}`: **{meb[k]}**")
    else:
        lines.append("  - (missing)")
    gi = tok_params.get("global_inflation_per_claim") if isinstance(tok_params, dict) else None
    if gi is not None:
        lines.append("")
        lines.append(f"- `global_inflation_per_claim`: `{gi}`")
    dao_addr = tok_params.get("dao_reward_address") if isinstance(tok_params, dict) else None
    if dao_addr:
        lines.append(f"- `dao_reward_address`: `{dao_addr}`")
    lines.append("")
    lines.append("## Minimum stake (role thresholds)")
    lines.append("")
    lines.append(f"- Supplier min stake: **{_format_pokt(supplier_min_stake_pokt)} POKT** (`{supplier_min_stake_u}` upokt)")
    lines.append(f"- Application min stake: **{_format_pokt(application_min_stake_pokt)} POKT** (`{application_min_stake_u}` upokt)")
    lines.append(f"- Gateway min stake: **{_format_pokt(gateway_min_stake_pokt)} POKT** (`{gateway_min_stake_u}` upokt)")
    lines.append("")
    lines.append("Raw output: see `research/pocket-liquidity-primitives.json`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

