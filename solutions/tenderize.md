# Tenderize — Liquid staking for Livepeer (tLPT) — Notes

## Summary

Tenderize built a general-purpose liquid staking system ("Tender Protocol") with a Livepeer integration. The Livepeer derivative is a **rebasing** token (`tLPT`) whose balance tracks a pro‑rata claim on the pool’s underlying staked LPT.

## Mechanism (what it did)

- **Deposit**: user deposits LPT into a `Tenderizer` contract; it mints a rebasing `TenderToken` (for Livepeer this is effectively `tLPT`).
- **Stake**: the `Tenderizer` bonds pooled LPT into Livepeer (`bond(amount, node)`).
- **Accrual**: as the pool’s underlying stake increases from rewards, `tLPT` balances increase (rebasing via a share system).
- **Exit**:
  - User calls `unstake(amount)` on the tenderizer.
  - The contract **burns `tLPT`** from the user **before** unbonding in Livepeer.
  - Unbonded stake is tracked via a withdrawal-lock mechanism; user later calls `withdraw(lockId)` to receive LPT.

This is the same core idea you described (“can only mint if you stake; can’t unstake unless the derivative is burned”), except it uses a `burn()` call (not literally “send to `0x0`”).

## Livepeer-specific details

- Livepeer has **ETH fees** in addition to LPT staking rewards; Tenderize’s integration optionally:
  - calls `withdrawFees()`,
  - wraps to WETH,
  - swaps WETH→LPT on Uniswap,
  - and compounds.

## Tokenomics (extra “non-simple” parts)

Tenderize’s whitepaper specifies (initial params):
- **Governance fee**: 2.5% of staking rewards
- **Liquidity fee**: 7.5% of staking rewards (to incentivize LPs)
- **Swap fee**: 0.5% on their tenderToken/underlying pool
- Optional protocol governance token `$TENDER` (for governance + fee share)

## References

- Whitepaper: `https://github.com/Tenderize/Whitepaper/blob/main/README.md`
- Core contracts repo: `https://github.com/Tenderize/tender-core`
  - Tenderizer burn-on-unstake: `contracts/tenderizer/Tenderizer.sol`
  - Livepeer integration: `contracts/tenderizer/integrations/livepeer/Livepeer.sol`

