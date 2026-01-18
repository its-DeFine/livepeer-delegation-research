from __future__ import annotations

import json
import os
import re
import random
import time
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Iterable

import requests
from Crypto.Hash import keccak

getcontext().prec = 80


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def http_get(url: str, *, params: dict[str, Any] | None = None, timeout_s: int = 30) -> requests.Response:
    return requests.get(
        url,
        params=params,
        timeout=timeout_s,
        headers={"User-Agent": "proposal-review/1.0"},
    )


def cached_download(url: str, dest: Path, *, refresh: bool = False, timeout_s: int = 30) -> Path:
    ensure_dir(dest.parent)
    if dest.exists() and not refresh:
        return dest
    resp = http_get(url, timeout_s=timeout_s)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def cached_json(url: str, dest: Path, *, refresh: bool = False, timeout_s: int = 30) -> Any:
    ensure_dir(dest.parent)
    if dest.exists() and not refresh:
        return read_json(dest)
    resp = http_get(url, timeout_s=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    write_json(dest, data)
    return data


def env(name: str, default: str) -> str:
    val = os.getenv(name)
    return val if val else default


def keccak_selector(signature: str) -> str:
    h = keccak.new(digest_bits=256)
    h.update(signature.encode("utf-8"))
    return h.hexdigest()[:8]


def pad32(hex_str: str) -> str:
    return hex_str.rjust(64, "0")


def abi_encode_address(address: str) -> str:
    return pad32(address.lower().replace("0x", ""))


def abi_encode_uint(value: int) -> str:
    return pad32(hex(value)[2:])


def abi_encode_int(value: int, *, bits: int = 256) -> str:
    if value < 0:
        value = (1 << bits) + value
    return pad32(hex(value & ((1 << bits) - 1))[2:])


def _should_retry_rpc_error(err: Any) -> bool:
    # Heuristic: retry rate-limits / transient infra errors, but fail fast on programmer errors/reverts.
    if not isinstance(err, dict):
        return True
    code = err.get("code")
    msg = str(err.get("message", "")).lower()

    if "execution reverted" in msg or "revert" in msg:
        return False

    # JSON-RPC "hard" errors / likely non-transient.
    if code in {-32601, -32602, -32603}:
        return False

    # Common transient codes.
    if code in {-32000, -32005}:
        return True

    # Default: retry.
    return True


class TransientRpcError(RuntimeError):
    pass


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {"User-Agent": "proposal-review/1.0"}

    max_attempts = 6
    backoff_base_s = 0.5

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(rpc_url, json=payload, timeout=30, headers=headers)
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"RPC HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()

            data = resp.json()
            if "error" in data:
                err = data["error"]
                if _should_retry_rpc_error(err) and attempt < max_attempts:
                    raise TransientRpcError(err)
                raise RuntimeError(err)
            return data["result"]
        except (requests.RequestException, ValueError, TransientRpcError) as e:
            if isinstance(e, requests.HTTPError) and getattr(e, "response", None) is not None:
                status = int(e.response.status_code)
                if 400 <= status < 500 and status != 429:
                    raise
            last_err = e if isinstance(e, Exception) else RuntimeError(str(e))
            if attempt >= max_attempts:
                raise

            sleep_s = backoff_base_s * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            time.sleep(sleep_s)

    raise RuntimeError("unreachable") from last_err


def eth_block_number(rpc_url: str) -> int:
    return int(rpc_call(rpc_url, "eth_blockNumber", []), 16)


def eth_get_block_by_number(rpc_url: str, block_number: int) -> dict[str, Any]:
    # Returns the full block object with transactions omitted.
    return rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_number), False])


def eth_get_block_timestamp(rpc_url: str, block_number: int) -> int:
    blk = eth_get_block_by_number(rpc_url, block_number)
    return int(blk["timestamp"], 16)


def find_block_by_timestamp(
    rpc_url: str,
    target_ts: int,
    *,
    low_block: int | None = None,
    high_block: int | None = None,
) -> int:
    # Binary search for the first block whose timestamp >= target_ts.
    low = 0 if low_block is None else low_block
    high = eth_block_number(rpc_url) if high_block is None else high_block

    if low < 0:
        low = 0
    if high < low:
        high = low

    if eth_get_block_timestamp(rpc_url, low) >= target_ts:
        return low
    if eth_get_block_timestamp(rpc_url, high) < target_ts:
        return high

    while low + 1 < high:
        mid = (low + high) // 2
        ts = eth_get_block_timestamp(rpc_url, mid)
        if ts >= target_ts:
            high = mid
        else:
            low = mid
    return high


def eth_call(rpc_url: str, to: str, data: str) -> str:
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data}, "latest"])


def decode_uint256(hex_str: str) -> int:
    return int(hex_str, 16)


def decode_int256(hex_str: str) -> int:
    value = int(hex_str, 16)
    if value >= 2**255:
        value -= 2**256
    return value


def decode_address_word(word_hex: str) -> str:
    return "0x" + word_hex[-40:]


def erc20_decimals(rpc_url: str, token: str) -> int:
    sel = "0x" + keccak_selector("decimals()")
    res = eth_call(rpc_url, token, sel)
    return int(res, 16)


def coingecko_simple_price(
    ids: Iterable[str],
    vs_currency: str,
    *,
    cache_path: Path | None = None,
    refresh: bool = False,
) -> dict[str, dict[str, float]]:
    cache_path = cache_path or (DATA_DIR / f"coingecko-simple-price-{vs_currency}.json")
    if cache_path.exists() and not refresh:
        cached = read_json(cache_path)
        if isinstance(cached, dict) and all(k in cached for k in ids):
            return cached

    url = "https://api.coingecko.com/api/v3/simple/price"
    resp = http_get(url, params={"ids": ",".join(ids), "vs_currencies": vs_currency})
    resp.raise_for_status()
    data = resp.json()
    # Be a good citizen: avoid spamming the endpoint in rapid loops.
    time.sleep(0.25)
    write_json(cache_path, data)
    return data


def coingecko_market_chart_daily(
    coin_id: str,
    *,
    vs_currency: str = "usd",
    days: int = 365,
    cache_path: Path | None = None,
    refresh: bool = False,
) -> list[list[float]]:
    cache_path = cache_path or (DATA_DIR / f"coingecko-market-chart-{coin_id}-{vs_currency}-{days}d.json")
    if cache_path.exists() and not refresh:
        return read_json(cache_path)["prices"]

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    resp = http_get(url, params={"vs_currency": vs_currency, "days": str(days), "interval": "daily"})
    resp.raise_for_status()
    data = resp.json()
    time.sleep(0.25)
    write_json(cache_path, data)
    return data["prices"]


@dataclass(frozen=True)
class UniswapV3PoolState:
    sqrt_price_x96: int
    tick: int
    liquidity: int
    fee: int
    tick_spacing: int


def read_univ3_pool_state(rpc_url: str, pool: str) -> UniswapV3PoolState:
    slot0_sel = "0x" + keccak_selector("slot0()")
    liquidity_sel = "0x" + keccak_selector("liquidity()")
    fee_sel = "0x" + keccak_selector("fee()")
    spacing_sel = "0x" + keccak_selector("tickSpacing()")

    slot0 = eth_call(rpc_url, pool, slot0_sel)
    words = [slot0[2 + i : 2 + i + 64] for i in range(0, 64 * 7, 64)]
    sqrt_price_x96 = int(words[0], 16)
    tick = decode_int256(words[1])

    liquidity = decode_uint256(eth_call(rpc_url, pool, liquidity_sel))
    fee = decode_uint256(eth_call(rpc_url, pool, fee_sel))
    tick_spacing = decode_uint256(eth_call(rpc_url, pool, spacing_sel))

    return UniswapV3PoolState(
        sqrt_price_x96=sqrt_price_x96,
        tick=tick,
        liquidity=liquidity,
        fee=fee,
        tick_spacing=tick_spacing,
    )


def sqrt_price_from_tick(tick: int) -> Decimal:
    # sqrt(1.0001^tick) = 1.0001^(tick/2)
    return Decimal("1.0001") ** (Decimal(tick) / Decimal(2))


def discourse_topic_json_url(topic_url: str) -> str:
    # Accepts:
    # - https://forum.../t/slug/3151
    # - https://forum.../t/slug/3151/10
    m = re.search(r"^(https?://[^/]+)/t/([^/]+)/(\d+)", topic_url)
    if not m:
        raise ValueError(f"Unrecognized Discourse topic URL: {topic_url}")
    host, slug, topic_id = m.group(1), m.group(2), m.group(3)
    return f"{host}/t/{slug}/{topic_id}.json"
