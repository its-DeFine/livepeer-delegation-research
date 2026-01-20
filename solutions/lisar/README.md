# Livepeer — Lisar SPE Delegation Analysis

This repo contains a reproducible, evidence-based analysis of the Lisar SPE delegation onboarding program on **Arbitrum One**:
- On-chain: Livepeer **BondingManager** logs (`eth_getLogs`) + current state (`eth_call`)
- Off-chain: Lisar public dashboard API (summary + transactions)

## Run / Reproduce

Generate the cohort report:
```bash
python3 tools/lisar_program_delegation_report.py --out-dir artifacts/livepeer-lisar-spe-delegation
```

Outputs:
- `artifacts/livepeer-lisar-spe-delegation/report.md`
- `artifacts/livepeer-lisar-spe-delegation/report.json`

## Notes

- The main write-up lives at `livepeer-lisar-spe-delegation-analysis.md`.
- Proposal/ROI context lives at `livepeer-lisar-spe-treasury-roi.md`.
- Snapshot dashboard payloads + report outputs are checked in under `artifacts/livepeer-lisar-spe-delegation/` for auditability.
