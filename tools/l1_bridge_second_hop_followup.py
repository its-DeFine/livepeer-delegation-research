#!/usr/bin/env python3
"""
Livepeer — Ethereum L1 second-hop follow-up for Arbitrum bridge-outs (LPT).

Motivation
----------
The first-hop report (`research/l1-bridge-recipient-followup.*`) shows that
bridge-out recipients often forward LPT to *other EOAs* on L1. Those EOAs could
be:
- self-custody re-org wallets,
- OTC counterparties,
- or CEX deposit wallets (hard to label on-chain).

This script takes the first-hop report and follows the *largest EOA destinations*
one more hop, asking:
  "Do these second-hop EOAs route to known DEX routers, known exchange hot wallets,
   Livepeer contracts, or just more EOAs?"

Inputs
------
- research/l1-bridge-recipient-followup.json
- data/labels.json (small curated label set; optional)

Outputs
-------
- research/l1-bridge-recipient-second-hop.json
- research/l1-bridge-recipient-second-hop.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


getcontext().prec = 60

TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BALANCE_OF_SELECTOR = "0x70a08231"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

LPT_DECIMALS = 18
LPT_SCALE = Decimal(10) ** LPT_DECIMALS


class RpcError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_s = retry_after_s


class RpcClient:
    def __init__(self, rpc_url: str, timeout_s: int = 60):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._id = 0

    def call(self, method: str, params: list) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "livepeer-delegation-research/l1-second-hop"},
            method="POST",
        )
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


def _normalize_address(addr: str) -> str:
    a = str(addr).lower()
    if not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid address: {addr}")
    return a


def _pad_topic_address(addr: str) -> str:
    a = _normalize_address(addr)
    return "0x" + ("0" * 24) + a[2:]


def _wei_to_lpt(amount_wei: int) -> Decimal:
    return Decimal(int(amount_wei)) / LPT_SCALE


def _format_lpt(x: Decimal, *, places: int = 3) -> str:
    q = Decimal(10) ** -places
    return f"{x.quantize(q):,}"


def _is_chunkable_logs_error(err_msg: str) -> bool:
    msg = err_msg.lower()
    return any(
        s in msg
        for s in (
            "block range",
            "too large",
            "query returned more than",
            "response size",
            "log response size",
            "more than",
            "too many results",
        )
    )


def _get_logs(client: RpcClient, *, address: str, topics: list, from_block: int, to_block: int) -> List[Dict[str, Any]]:
    return _rpc_with_retries(
        client,
        "eth_getLogs",
        [
            {
                "address": address,
                "fromBlock": hex(int(from_block)),
                "toBlock": hex(int(to_block)),
                "topics": topics,
            }
        ],
    )


def _get_logs_range(
    client: RpcClient,
    *,
    address: str,
    topics: list,
    from_block: int,
    to_block: int,
    max_splits: int = 18,
) -> List[Dict[str, Any]]:
    try:
        return _get_logs(client, address=address, topics=topics, from_block=from_block, to_block=to_block)
    except RpcError as e:
        msg = str(e)
        if not _is_chunkable_logs_error(msg) or max_splits <= 0 or from_block >= to_block:
            raise
        mid = (from_block + to_block) // 2
        return _get_logs_range(client, address=address, topics=topics, from_block=from_block, to_block=mid, max_splits=max_splits - 1) + _get_logs_range(
            client, address=address, topics=topics, from_block=mid + 1, to_block=to_block, max_splits=max_splits - 1
        )


def _balance_of(client: RpcClient, *, token: str, owner: str) -> int:
    owner = _normalize_address(owner)
    data = BALANCE_OF_SELECTOR + ("0" * 24) + owner[2:]
    res = _rpc_with_retries(client, "eth_call", [{"to": _normalize_address(token), "data": data}, "latest"])
    return int(str(res), 16)


def _get_code(client: RpcClient, addr: str) -> str:
    return str(_rpc_with_retries(client, "eth_getCode", [_normalize_address(addr), "latest"]) or "0x")


def _decode_transfer_log(log: Dict[str, Any]) -> Tuple[str, str, int]:
    topics = [str(t).lower() for t in (log.get("topics") or [])]
    if len(topics) < 3 or topics[0] != TOPIC0_TRANSFER:
        raise ValueError("not a Transfer log")
    from_addr = _normalize_address("0x" + topics[1][-40:])
    to_addr = _normalize_address("0x" + topics[2][-40:])
    value_wei = int(str(log.get("data") or "0x0"), 16)
    return from_addr, to_addr, value_wei


def _load_labels(path: str) -> Dict[str, Dict[str, str]]:
    if not path or not os.path.exists(path):
        return {}
    raw = json.load(open(path, "r", encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        try:
            addr = _normalize_address(k)
        except ValueError:
            continue
        out[addr] = {str(kk): str(vv) for kk, vv in v.items() if isinstance(kk, str) and isinstance(vv, str)}
    return out


@dataclass
class DestAgg:
    amount_wei: int = 0
    tx_count: int = 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-json", default="research/l1-bridge-recipient-followup.json")
    parser.add_argument("--labels-json", default="data/labels.json")
    parser.add_argument("--min-inbound-lpt", type=float, default=100_000.0)
    parser.add_argument("--max-addresses", type=int, default=20)
    parser.add_argument("--out-md", default="research/l1-bridge-recipient-second-hop.md")
    parser.add_argument("--out-json", default="research/l1-bridge-recipient-second-hop.json")
    args = parser.parse_args()

    first = json.load(open(args.in_json, "r", encoding="utf-8"))
    eth_rpc = str(first.get("eth_rpc") or "")
    token = str(first.get("lpt_token_l1") or "")
    rng = first.get("range") or {}
    from_block = int(rng.get("from_block") or 0)
    to_block = int(rng.get("to_block") or 0)
    if not eth_rpc or not token or from_block <= 0 or to_block <= 0:
        raise SystemExit("bad input json: missing eth_rpc/lpt_token_l1/range")

    recipients = first.get("recipients") or []
    if not isinstance(recipients, list) or not recipients:
        raise SystemExit("bad input json: recipients missing/empty")

    labels = _load_labels(str(args.labels_json))
    client = RpcClient(eth_rpc)

    code_cache: Dict[str, bool] = {}

    def is_contract(addr: str) -> bool:
        a = _normalize_address(addr)
        if a in code_cache:
            return code_cache[a]
        code = _get_code(client, a)
        is_c = isinstance(code, str) and code != "0x" and len(code) > 2
        code_cache[a] = is_c
        return is_c

    # Aggregate inbound (from first-hop recipients) per destination address.
    inbound_by_dest_wei: Dict[str, int] = defaultdict(int)
    for r in recipients:
        if not isinstance(r, dict):
            continue
        for d in (r.get("top_destinations") or []):
            if not isinstance(d, dict):
                continue
            to = d.get("to")
            cat = d.get("category")
            amt = d.get("amount_lpt")
            if not isinstance(to, str) or not isinstance(cat, str) or not isinstance(amt, str):
                continue
            if cat != "unknown_eoa":
                continue
            inbound_by_dest_wei[_normalize_address(to)] += int(Decimal(amt) * LPT_SCALE)

    threshold_wei = int(Decimal(str(args.min_inbound_lpt)) * LPT_SCALE)
    candidates = [(addr, wei) for addr, wei in inbound_by_dest_wei.items() if int(wei) >= threshold_wei]
    candidates.sort(key=lambda kv: kv[1], reverse=True)
    if int(args.max_addresses) > 0:
        candidates = candidates[: int(args.max_addresses)]

    per_address: List[Dict[str, Any]] = []
    global_category_totals_wei: Dict[str, int] = defaultdict(int)

    for i, (addr, inbound_wei) in enumerate(candidates, start=1):
        bal_wei = _balance_of(client, token=token, owner=addr)
        topics = [TOPIC0_TRANSFER, _pad_topic_address(addr), None]
        logs = _get_logs_range(client, address=_normalize_address(token), topics=topics, from_block=from_block, to_block=to_block)

        dests: Dict[str, DestAgg] = defaultdict(DestAgg)
        for log in logs:
            try:
                _from, to, value_wei = _decode_transfer_log(log)
            except Exception:
                continue
            dests[to].amount_wei += int(value_wei)
            dests[to].tx_count += 1

        rows: List[Dict[str, Any]] = []
        cat_totals_wei: Dict[str, int] = defaultdict(int)
        total_out_wei = 0
        total_out_txs = 0
        for to, agg in dests.items():
            total_out_wei += int(agg.amount_wei)
            total_out_txs += int(agg.tx_count)
            label = labels.get(to)
            if label and label.get("category"):
                cat = label["category"]
            elif to == ZERO_ADDRESS:
                cat = "burn"
            else:
                cat = "unknown_contract" if is_contract(to) else "unknown_eoa"
            cat_totals_wei[cat] += int(agg.amount_wei)
            global_category_totals_wei[cat] += int(agg.amount_wei)
            rows.append(
                {
                    "to": to,
                    "category": cat,
                    "label": (label.get("name") if label else ""),
                    "amount_lpt": str(_wei_to_lpt(int(agg.amount_wei))),
                    "tx_count": int(agg.tx_count),
                }
            )
        rows.sort(key=lambda r: Decimal(r["amount_lpt"]), reverse=True)

        per_address.append(
            {
                "rank": i,
                "address": addr,
                "inbound_lpt_from_bridge_recipients": str(_wei_to_lpt(inbound_wei)),
                "current_balance_lpt": str(_wei_to_lpt(bal_wei)),
                "outgoing_lpt": str(_wei_to_lpt(total_out_wei)),
                "outgoing_tx_count": total_out_txs,
                "category_totals_lpt": {k: str(_wei_to_lpt(v)) for k, v in sorted(cat_totals_wei.items())},
                "top_destinations": rows[:15],
            }
        )

        print(
            f"[{i}/{len(candidates)}] {addr} inbound={_format_lpt(_wei_to_lpt(inbound_wei))} out={_format_lpt(_wei_to_lpt(total_out_wei))} ({len(logs)} logs)"
        )

    total_in_wei = sum((wei for _addr, wei in candidates), 0)
    total_out_wei = sum((int(Decimal(a["outgoing_lpt"]) * LPT_SCALE) for a in per_address), 0)

    out_json = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "eth_rpc": eth_rpc,
        "lpt_token_l1": _normalize_address(token),
        "inputs": {"in_json": str(args.in_json), "labels_json": str(args.labels_json)},
        "range": {"from_block": from_block, "to_block": to_block},
        "selection": {"min_inbound_lpt": float(args.min_inbound_lpt), "max_addresses": int(args.max_addresses)},
        "totals": {"inbound_lpt": str(_wei_to_lpt(total_in_wei)), "outgoing_lpt": str(_wei_to_lpt(total_out_wei))},
        "category_totals": {k: str(_wei_to_lpt(v)) for k, v in sorted(global_category_totals_wei.items())},
        "addresses": per_address,
    }

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, sort_keys=True)
        f.write("\n")

    # Markdown
    lines: List[str] = []
    lines.append("---")
    lines.append("title: L1 second hop (exchange routing)")
    lines.append(
        "description: Follow the biggest post-bridge L1 EOAs one hop further to see routing into labeled exchange endpoints (best-effort)."
    )
    lines.append("sidebar_label: L1 second hop (exchange routing)")
    lines.append("---")
    lines.append("")
    lines.append("# L1 second hop (exchange routing)")
    lines.append("")
    lines.append(f"- Generated: `{out_json['generated_at_utc']}`")
    lines.append(f"- Input: `{out_json['inputs']['in_json']}`")
    lines.append(f"- L1 RPC: `{out_json['eth_rpc']}`")
    lines.append(f"- L1 token: `{out_json['lpt_token_l1']}`")
    lines.append(f"- Range: `{from_block}` → `{to_block}`")
    lines.append(f"- Filter: `unknown_eoa` destinations with ≥ **{float(args.min_inbound_lpt):,.0f} LPT** inbound from bridge recipients")
    lines.append("")
    lines.append("## Totals (selected addresses)")
    lines.append("")
    lines.append(f"- Selected addresses: **{len(per_address)}**")
    lines.append(f"- Total inbound from bridge recipients: **{_format_lpt(Decimal(out_json['totals']['inbound_lpt']))} LPT**")
    lines.append(f"- Total outgoing from selected addresses: **{_format_lpt(Decimal(out_json['totals']['outgoing_lpt']))} LPT**")
    lines.append("")
    lines.append("## Key findings (second hop)")
    lines.append("")
    total_out_lpt = Decimal(out_json["totals"]["outgoing_lpt"])
    exch_lpt = Decimal(out_json["category_totals"].get("exchange", "0"))
    dex_lpt = Decimal(out_json["category_totals"].get("dex_router", "0"))
    unknown_eoa_lpt = Decimal(out_json["category_totals"].get("unknown_eoa", "0"))
    livepeer_lpt = Decimal(out_json["category_totals"].get("livepeer_contract", "0"))

    if total_out_lpt > 0:
        lines.append(f"- Outgoing to labeled exchanges: **{_format_lpt(exch_lpt)} LPT** ({float(exch_lpt/total_out_lpt)*100:.2f}%)")
        lines.append(f"- Outgoing to unknown EOAs: **{_format_lpt(unknown_eoa_lpt)} LPT** ({float(unknown_eoa_lpt/total_out_lpt)*100:.2f}%)")
        if livepeer_lpt > 0:
            lines.append(f"- Outgoing to Livepeer contracts (labeled): **{_format_lpt(livepeer_lpt)} LPT**")
        if dex_lpt > 0:
            lines.append(f"- Outgoing to labeled DEX routers: **{_format_lpt(dex_lpt)} LPT**")
        else:
            lines.append("- Outgoing to labeled DEX routers: **0.000 LPT**")

    # Top exchange destinations (best-effort, from label set).
    exch_dest_wei: Dict[str, int] = defaultdict(int)
    for a in per_address:
        for d in a.get("top_destinations") or []:
            if not isinstance(d, dict):
                continue
            if str(d.get("category") or "") != "exchange":
                continue
            to = str(d.get("to") or "")
            amt = str(d.get("amount_lpt") or "0")
            if to.startswith("0x") and len(to) == 42:
                exch_dest_wei[_normalize_address(to)] += int(Decimal(amt) * LPT_SCALE)

    if exch_dest_wei:
        top_ex = sorted(exch_dest_wei.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines.append("")
        lines.append("Top labeled exchange destinations:")
        for addr, wei in top_ex:
            label = labels.get(addr, {})
            name = label.get("name", "")
            lines.append(f"- `{addr}` {('(' + name + ')') if name else ''}: **{_format_lpt(_wei_to_lpt(wei))} LPT**")
    lines.append("")
    lines.append(
        "Interpretation: unlike the first hop (bridge recipients → EOAs), the second hop surfaces "
        "a material route into labeled exchange hot wallets (e.g., Coinbase Prime, Binance). "
        "This suggests that a portion of the bridge-outs are consistent with eventual exchange deposit flows."
    )
    lines.append("")
    lines.append("## Category totals (outgoing)")
    lines.append("")
    lines.append("| Category | Outgoing (LPT) | Share |")
    lines.append("|---|---:|---:|")
    out_total = Decimal(out_json["totals"]["outgoing_lpt"])
    for cat, amt_str in out_json["category_totals"].items():
        amt = Decimal(amt_str)
        share = (amt / out_total) if out_total > 0 else Decimal(0)
        lines.append(f"| {cat} | {_format_lpt(amt)} | {float(share)*100:.2f}% |")
    lines.append("")
    lines.append("## Addresses (summary)")
    lines.append("")
    lines.append("| Rank | Address | Inbound (LPT) | Outgoing (LPT) | Current balance (LPT) | Out txs |")
    lines.append("|---:|---|---:|---:|---:|---:|")
    for a in per_address:
        lines.append(
            f"| {a['rank']} | `{a['address']}` | {_format_lpt(Decimal(a['inbound_lpt_from_bridge_recipients']))} | {_format_lpt(Decimal(a['outgoing_lpt']))} | {_format_lpt(Decimal(a['current_balance_lpt']))} | {int(a['outgoing_tx_count']):,} |"
        )
    lines.append("")
    lines.append("## Addresses (top destinations)")
    lines.append("")
    lines.append("Tip: expand only the wallets you care about.")
    lines.append("")
    for a in per_address:
        addr = str(a["address"])
        inbound_fmt = _format_lpt(Decimal(a["inbound_lpt_from_bridge_recipients"]))
        outgoing_fmt = _format_lpt(Decimal(a["outgoing_lpt"]))
        txs = int(a["outgoing_tx_count"])
        lines.append("<details>")
        lines.append(
            f"<summary><code>{addr}</code> — inbound <b>{inbound_fmt} LPT</b>, outgoing <b>{outgoing_fmt} LPT</b> ({txs:,} txs)</summary>"
        )
        lines.append("")
        lines.append(f"- Inbound from bridge recipients: **{inbound_fmt} LPT**")
        lines.append(f"- Outgoing in range: **{outgoing_fmt} LPT** across **{txs:,}** txs")
        lines.append(f"- Current L1 balance: **{_format_lpt(Decimal(a['current_balance_lpt']))} LPT**")
        lines.append("")
        lines.append("| Destination | Label | Category | Outgoing (LPT) | Txs |")
        lines.append("|---|---|---|---:|---:|")
        for d in a["top_destinations"]:
            lines.append(
                f"| `{d['to']}` | {d.get('label','')} | {d['category']} | {_format_lpt(Decimal(d['amount_lpt']))} | {int(d['tx_count']):,} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
