---
title: Tenderize (tLPT)
description: Historical Livepeer liquid staking on Arbitrum—mechanics, adoption evidence, and failure modes.
---

# Tenderize — tLPT (Liquid Staking for Livepeer on Arbitrum)

Tenderize built a general-purpose liquid staking system ("Tender Protocol") with a Livepeer integration. The Livepeer derivative is a **rebasing** token (`tLPT`) whose balance tracks a pro‑rata claim on the pool’s underlying staked LPT.

This dossier focuses on: **did Tenderize increase unique small delegators / participants?** (and what we can prove from on-chain logs).

## On-chain deployment (Arbitrum One)

Source of addresses: Tenderize app config + tender-core deployments.

- Tenderizer (pool / delegator contract): `0x339efC059C6D4Aa50a41F8246a017B57Aa477b60`
- TenderToken (tLPT): `0xfaC38532829fDD744373fdcd4708Ab90fA0c4078`
- LPT (Arbitrum): `0x289ba1701C2F088cf0faf8B3705246331cB8A839`
- TenderSwap (tLPT/LPT): `0x2429fC7082eb517C14946b392b195B181D0b9781`
- LP token: `0x6cAbc6e78c1D632b6210EaB71c19889b92376931`
- TenderFarm: `0x3FE01e8b62a8E17F296Eb3832504C3D3A49f2209`

Deployment tx (tenderizer proxy): `0x5c38f744c68e188751e275b0a599d0eec3745829a226641430965117295aadea` (2022‑05‑09 UTC)

## Mechanism (what it did)

- **Deposit**: user deposits LPT into a `Tenderizer` contract.
- **Stake**: the `Tenderizer` bonds pooled LPT into Livepeer (`bond(amount, node)`).
- **Accrual**: as the pool’s underlying stake increases from rewards, `tLPT` balances increase (rebasing via a share system).
- **Exit**:
  - User calls `unstake(amount)` on the tenderizer.
  - The contract **burns `tLPT`** from the user **before** unbonding in Livepeer.
  - Unbonded stake is tracked via a withdrawal-lock mechanism; user later calls `withdraw(lockId)` to receive LPT.

This is the same core idea you described (“can only mint if you stake; can’t unstake unless the derivative is burned”), except it’s implemented as a `burn()` call (not literally “send to `0x0`”).

Important nuance: `TenderToken` does **not** emit ERC20 `Transfer(from=0x0, ...)` or `Transfer(..., to=0x0)` events on mint/burn (it mints/burns *shares* without emitting `Transfer`). So “unique tokenholders” can’t be inferred from ERC20 transfer logs alone.

## Livepeer-specific details

- Livepeer has **ETH fees** in addition to LPT staking rewards; Tenderize’s integration optionally:
  - calls `withdrawFees()`,
  - wraps to WETH,
  - swaps WETH→LPT on Uniswap,
  - and compounds.

## Did it increase “unique delegators”?

**Protocol-level**: No (not in the “more delegator addresses in BondingManager” sense).

- In Livepeer, the **Tenderizer contract** is the delegator (it’s the address that calls `bond/unbond/withdrawStake`).
- Users who deposit into Tenderize do **not** become delegators in Livepeer’s BondingManager; they become pool participants holding `tLPT` shares.

So Tenderize can increase the number of **unique participants with stake exposure**, but it doesn’t directly increase the number of **on-chain delegator accounts**.

## Adoption / “unique participants” (hard evidence)

We scanned the Tenderizer’s on-chain logs on Arbitrum via `eth_getLogs` and computed unique depositors, deposit sizes, and exit behavior.

- Analysis script: `tools/tenderize_livepeer_adopters.py`
- Output snapshot (committed): `solutions/tenderize/livepeer-adopters-summary.json`

Key results (from `solutions/tenderize/livepeer-adopters-summary.json`):

- Deposits: **2,786** `Deposit` events from **2,518** unique depositors; **~92,191.46 LPT** deposited (2022‑05‑09 → 2024‑03‑09).
- Deposit size distribution (by depositor’s *total deposited*, LPT):
  - `<= 1`: **1,219**
  - `1 - 10`: **1,201**
  - `10 - 100`: **68**
  - `100 - 1000`: **20**
  - `1000 - 10000`: **6**
  - `> 10000`: **4**
  - Percentiles: p50 **~1.02**, p90 **~3.18**, p95 **~7.00**, p99 **~155.98**
- Exits:
  - `Unstake`: **556** events from **502** unique unstakers; **~111,536.42 LPT** unstaked
  - `Withdraw`: **346** events from **311** unique withdrawers; **~110,026.25 LPT** withdrawn (first withdraw 2023‑02‑08; last withdraw 2025‑05‑30)
  - Deposit → exit linkage: of 2,518 depositors, **305** eventually had a `Withdraw` event (so most depositors did not fully exit *through this contract* as of the scan).

Interpretation:
- Tenderize appears to have attracted a large number of **very small** depositors (most total deposits are under 10 LPT).
- It did not create “2518 new delegators” on Livepeer; it created “2518 pool depositors”.

## Tokenomics (extra “non-simple” parts)

Tenderize’s whitepaper specifies (initial params):
- **Governance fee**: 2.5% of staking rewards
- **Liquidity fee**: 7.5% of staking rewards (to incentivize LPs)
- **Swap fee**: 0.5% on their tenderToken/underlying pool
- Optional protocol governance token `$TENDER` (for governance + fee share)

## Risks / failure modes

- **Upgradeable proxy risk**: the Livepeer Tenderizer is a proxy (`ProxyImplementationUpdated` events exist). A Dedaub report alleges a Tenderize V2 proxy-upgrade backdoor drain (Ethereum), which is a reminder that admin key/upgrade governance is a primary LST risk.
- **Operational risk**: public repo issues suggest parts of the product broke over time and the org may no longer be maintaining deployments.

## Reproduce the analysis

Generate/refresh the snapshot JSON:

```bash
python3 tools/tenderize_livepeer_adopters.py \
  --out-json solutions/tenderize/livepeer-adopters-summary.json
```

Optional (heavier): count unique addresses in tLPT transfer logs:

```bash
python3 tools/tenderize_livepeer_adopters.py \
  --include-transfer-holders
```

## References

- Whitepaper: `https://github.com/Tenderize/Whitepaper/blob/main/README.md`
- Core contracts repo: `https://github.com/Tenderize/tender-core`
  - Tenderizer burn-on-unstake: `contracts/tenderizer/Tenderizer.sol`
  - Livepeer integration: `contracts/tenderizer/integrations/livepeer/Livepeer.sol`
- Tenderize app config (addresses + chain selection): `https://github.com/Tenderize/tender-app`
