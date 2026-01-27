#!/usr/bin/env python3
"""
Theta Network — staking liquidity primitives (docs + on-chain RPC context).

Goal
----
Theta is a Livepeer-adjacent DePIN-style network (video infra + staking/emissions).
For our "reward vesting vs liquid rewards" comparisons, the key primitives are
the *unstaking / withdrawal delays* (principal friction) and whether rewards are
locked via protocol-level linear vesting (not evidenced here).

We produce a reproducible evidence pack that captures:
- Official Theta docs statements for stake withdrawal/unstaking delays:
  - Guardian stake withdrawal: ~48 hours
  - Elite Edge Node (TFUEL staking): ~60 hours
- Minimal on-chain context from Theta's public ETH-RPC adaptor:
  - chainId, latest block, and a best-effort block-time estimate from timestamps

Notes
-----
Theta staking operations are native transaction types on Theta; they are not
trivially introspected via standard EVM calls. We therefore treat the official
documentation as the primary source for the specific unstaking delays, and add
on-chain RPC context as a reproducibility check that we are querying Theta mainnet.

Outputs
-------
- research/theta-liquidity-primitives.json
- research/theta-liquidity-primitives.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


THETA_ETH_RPC_DEFAULT = "https://eth-rpc-api.thetatoken.org/rpc"

DOC_GUARDIAN_WITHDRAW = "https://docs.thetatoken.org/docs/withdrawing-your-stake-from-the-guardian-node"
DOC_TFUEL_STAKING = "https://docs.thetatoken.org/docs/elite-edge-node-staking-process"

# Theta protocol ledger (public) — used to source ReturnLockingPeriod (block-based unbonding delay).
THETA_PROTOCOL_STAKE_GO_RAW_DEFAULT = "https://raw.githubusercontent.com/thetatoken/theta-protocol-ledger/master/core/stake.go"


class FetchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


def _fetch_text(url: str, *, timeout_s: int = 60, user_agent: str = "Mozilla/5.0") -> str:
    req = Request(url, headers={"user-agent": user_agent})
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        retry_after_s: int | None = None
        try:
            ra = e.headers.get("Retry-After")
            if isinstance(ra, str) and ra.strip().isdigit():
                retry_after_s = int(ra.strip())
        except Exception:
            retry_after_s = None
        raise FetchError(
            f"HTTP {e.code}: {e.reason} ({url})",
            status_code=int(getattr(e, "code", 0)) or None,
            retry_after_s=retry_after_s,
        ) from e
    except URLError as e:
        raise FetchError(f"URL error: {e.reason} ({url})") from e
    except Exception as e:
        raise FetchError(f"fetch error: {e} ({url})") from e


def _fetch_with_retries(url: str, *, max_tries: int = 8) -> str:
    for attempt in range(1, max_tries + 1):
        try:
            return _fetch_text(url)
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


def _theta_protocol_return_locking_period(stake_go_raw_url: str) -> dict[str, Any]:
    raw = _fetch_with_retries(stake_go_raw_url)
    m = re.search(r"ReturnLockingPeriod\s+uint64\s*=\s*(\d+)", raw)
    if not m:
        raise FetchError(f"could not locate ReturnLockingPeriod in {stake_go_raw_url}")
    blocks = int(m.group(1))
    # Best-effort: capture the full line for context (often includes a comment with the intended time).
    line = ""
    for ln in raw.splitlines():
        if "ReturnLockingPeriod" in ln:
            line = ln.strip()
            break
    return {"return_locking_period_blocks": int(blocks), "source_url": stake_go_raw_url, "source_line": line}


def _extract_ssr_props(html: str) -> dict[str, Any]:
    m = re.search(r'<script id=\"ssr-props\" type=\"application/json\">(.*?)</script>', html, re.DOTALL)
    if not m:
        raise FetchError("missing ssr-props JSON (page HTML shape changed?)")
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        raise FetchError(f"invalid ssr-props JSON: {e}") from e
    if not isinstance(data, dict):
        raise FetchError(f"unexpected ssr-props type: {type(data).__name__}")
    return data


def _strip_html(s: str) -> str:
    # Minimal; good enough for short excerpts.
    return re.sub(r"<[^>]+>", "", s or "").replace("&quot;", '"').replace("&#x27;", "'").replace("&amp;", "&")


def _extract_doc_excerpt(url: str, *, pattern: str) -> dict[str, Any]:
    html = _fetch_with_retries(url)
    props = _extract_ssr_props(html)
    body = (((props.get("rdmd") or {}).get("dehydrated") or {}).get("body") or "") if isinstance(props.get("rdmd"), dict) else ""
    body_str = str(body) if isinstance(body, str) else ""

    body_text = _strip_html(body_str)

    m = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
    excerpt = ""
    if m:
        excerpt = m.group(0).strip()

    return {
        "url": url,
        "reqUrl": props.get("reqUrl"),
        "title": (props.get("meta") or {}).get("title") if isinstance(props.get("meta"), dict) else None,
        "body_text_excerpt_pattern": pattern,
        "excerpt": excerpt,
    }


def _rpc_call(rpc_url: str, method: str, params: list, *, timeout_s: int = 60, user_agent: str = "Mozilla/5.0") -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    body = json.dumps(payload).encode("utf-8")
    req = Request(rpc_url, data=body, headers={"content-type": "application/json", "user-agent": user_agent}, method="POST")
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except HTTPError as e:
        raise FetchError(f"HTTP {e.code}: {e.reason} ({rpc_url})") from e
    except URLError as e:
        raise FetchError(f"URL error: {e.reason} ({rpc_url})") from e
    except Exception as e:
        raise FetchError(f"RPC transport error: {e} ({rpc_url})") from e

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise FetchError(f"invalid JSON-RPC response: {raw[:200]!r}") from e

    if isinstance(data, dict) and data.get("error"):
        raise FetchError(str(data["error"]))
    return data.get("result") if isinstance(data, dict) else data


def _hex_to_int(hex_str: str) -> int:
    s = (hex_str or "").strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if s == "":
        return 0
    return int(s, 16)


def _estimate_block_time_seconds(rpc_url: str, *, sample_blocks: int = 5000) -> dict[str, Any]:
    latest_hex = str(_rpc_call(rpc_url, "eth_blockNumber", []))
    latest = _hex_to_int(latest_hex)
    older = max(0, latest - int(sample_blocks))

    blk_latest = _rpc_call(rpc_url, "eth_getBlockByNumber", [hex(latest), False])
    blk_older = _rpc_call(rpc_url, "eth_getBlockByNumber", [hex(older), False])

    ts_latest = _hex_to_int(str((blk_latest or {}).get("timestamp") or "0x0")) if isinstance(blk_latest, dict) else 0
    ts_older = _hex_to_int(str((blk_older or {}).get("timestamp") or "0x0")) if isinstance(blk_older, dict) else 0

    delta_blocks = max(0, latest - older)
    delta_s = max(0, ts_latest - ts_older)
    avg = (delta_s / delta_blocks) if delta_blocks else 0.0

    return {
        "latest_block": int(latest),
        "older_block": int(older),
        "timestamp_latest": int(ts_latest),
        "timestamp_older": int(ts_older),
        "blocks_delta": int(delta_blocks),
        "seconds_delta": int(delta_s),
        "avg_block_time_seconds": float(avg),
    }


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eth-rpc", default=os.environ.get("THETA_ETH_RPC_URL") or THETA_ETH_RPC_DEFAULT)
    parser.add_argument("--protocol-stake-go-raw", default=os.environ.get("THETA_PROTOCOL_STAKE_GO_RAW_URL") or THETA_PROTOCOL_STAKE_GO_RAW_DEFAULT)
    parser.add_argument("--out-json", default="research/theta-liquidity-primitives.json")
    parser.add_argument("--out-md", default="research/theta-liquidity-primitives.md")
    args = parser.parse_args()

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    rpc = str(args.eth_rpc)

    chain_id_hex = str(_rpc_call(rpc, "eth_chainId", []))
    chain_id = _hex_to_int(chain_id_hex)
    block_time = _estimate_block_time_seconds(rpc, sample_blocks=5000)

    protocol = _theta_protocol_return_locking_period(str(args.protocol_stake_go_raw))

    guardian = _extract_doc_excerpt(
        DOC_GUARDIAN_WITHDRAW,
        pattern=r"[^.]*48\s*hours[^.]*\.",
    )
    tfuel = _extract_doc_excerpt(
        DOC_TFUEL_STAKING,
        pattern=r"[^.]*60\s*hour[^.]*\.",
    )

    out_json: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "theta": {
            "eth_rpc": rpc,
            "chain_id": int(chain_id),
            "chain_id_hex": chain_id_hex,
            "block_time_estimate": block_time,
            "protocol": protocol,
            "docs": {
                "guardian_stake_withdrawal": guardian,
                "tfuel_staking_unstake": tfuel,
            },
        },
        "notes": [
            "Unstaking delays are sourced from official Theta docs pages and extracted from the rendered HTML embedded in their SSR props.",
            "Theta staking operations are native to the Theta chain; they are not directly introspected via standard EVM methods in this report.",
        ],
    }

    _write_json(args.out_json, out_json)

    avg_block_time_s = float((block_time or {}).get("avg_block_time_seconds") or 0.0)
    return_lock_blocks = int((protocol or {}).get("return_locking_period_blocks") or 0)
    return_lock_hours_at_observed = (return_lock_blocks * avg_block_time_s) / 3600.0 if return_lock_blocks and avg_block_time_s else 0.0
    return_lock_hours_at_6s = (return_lock_blocks * 6.0) / 3600.0 if return_lock_blocks else 0.0

    lines: list[str] = []
    lines.append("---")
    lines.append('title: "Theta staking liquidity primitives (withdraw delays)"')
    lines.append('description: "Evidence pack for Theta staking withdrawal/unstaking delays (Guardian stake ~48h; TFUEL stake ~60h) with Theta ETH-RPC chain context."')
    lines.append('sidebar_label: "Theta: liquidity primitives"')
    lines.append("---")
    lines.append("")
    lines.append("# Theta staking liquidity primitives (withdraw delays)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- Theta ETH-RPC: `{rpc}`")
    lines.append(f"- `eth_chainId`: `{chain_id_hex}` ({chain_id})")
    lines.append("")
    lines.append("## On-chain context (EVM adaptor)")
    lines.append("")
    lines.append(f"- Latest block: `{block_time.get('latest_block')}`")
    lines.append(f"- Estimated block time: **{avg_block_time_s:.2f}s** (over {block_time.get('blocks_delta')} blocks)")
    lines.append("")
    lines.append("## Protocol constant (block-based return lock)")
    lines.append("")
    lines.append(f"- `ReturnLockingPeriod`: **{return_lock_blocks:,} blocks**")
    lines.append(f"- Source (Theta protocol ledger): `{protocol.get('source_url')}`")
    if protocol.get("source_line"):
        lines.append(f"- Line excerpt: `{protocol.get('source_line')}`")
    if return_lock_hours_at_6s:
        lines.append(f"- Time @ 6s/block (nominal): **~{return_lock_hours_at_6s:.1f} hours**")
    if return_lock_hours_at_observed:
        lines.append(f"- Time @ observed avg (ETH-RPC timestamps): **~{return_lock_hours_at_observed:.1f} hours**")
    lines.append("")
    lines.append("## Unstaking / withdrawal delays (official docs excerpts)")
    lines.append("")
    lines.append("Guardian stake withdrawal:")
    lines.append(f"- Source: `{DOC_GUARDIAN_WITHDRAW}`")
    if guardian.get("excerpt"):
        lines.append(f"- Excerpt: “{guardian['excerpt']}”")
    lines.append("")
    lines.append("TFUEL staking (Elite Edge Node) withdrawal:")
    lines.append(f"- Source: `{DOC_TFUEL_STAKING}`")
    if tfuel.get("excerpt"):
        lines.append(f"- Excerpt: “{tfuel['excerpt']}”")
    lines.append("")
    lines.append("Interpretation: Theta exposes **principal liquidity friction** via unstaking delays; this is not the same primitive as protocol-level linear reward vesting.")
    lines.append("")
    lines.append("Raw output: see `research/theta-liquidity-primitives.json`.")

    _write_text(args.out_md, "\n".join(lines) + "\n")

    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
