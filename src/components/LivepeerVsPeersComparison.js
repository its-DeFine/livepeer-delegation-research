import React from 'react';
import Link from '@docusaurus/Link';

import BarList from '@site/src/components/BarList';
import ExchangeRoutingInfographic from '@site/src/components/ExchangeRoutingInfographic';

import routing30d from '@site/research/exchange-routing-metrics.json';
import routing3d from '@site/research/exchange-routing-metrics-3d.json';

import transferBond from '@site/research/livepeer-transferbond-rotation.json';
import buyPressure from '@site/research/buy-pressure-proxies.json';

import stakeDist from '@site/research/delegator-stake-distribution.json';
import outflowsByBand from '@site/research/delegator-outflows-by-size-band.json';
import rewardsWithdraw from '@site/research/rewards-withdraw-timeseries.json';

function toNum(x) {
  const n = Number.parseFloat(String(x ?? '0'));
  return Number.isFinite(n) ? n : 0;
}

function fmtPct(x) {
  return `${toNum(x).toFixed(2)}%`;
}

function fmtInt(x) {
  const n = Number(x ?? 0);
  return Number.isFinite(n) ? n.toLocaleString('en-US') : '—';
}

function fmtTok(x, places = 3) {
  const n = Number.parseFloat(String(x ?? '0'));
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-US', { maximumFractionDigits: places });
}

function metricAmountKey(metric) {
  const tok = String(metric?.token ?? '');
  if (tok === 'LPT') return 'amount_lpt';
  if (tok === 'GRT') return 'amount_grt';
  return 'amount';
}

function denomAmount(metric) {
  const k = metricAmountKey(metric);
  return metric?.denominator?.[k] ?? '0';
}

function numerAmount(metric) {
  const k = metricAmountKey(metric);
  return metric?.numerator?.[k] ?? '0';
}

function metricEvents(metric) {
  const e = metric?.denominator?.events;
  return typeof e === 'number' ? e : null;
}

function roleBarItems(metric) {
  const shares = metric?.post_exit_roles?.role_exit_share_percent ?? null;
  if (!shares) return [];

  const labelByKey = {
    exchange_strict: 'Exchange (strict)',
    dex_router_interaction: 'DEX router interaction',
    bridge_deposit: 'Bridge deposit',
    hold_no_first_hop: 'Hold / no first hop',
    unknown_eoa: 'Unknown EOA',
    unknown_contract: 'Unknown contract'
  };

  const order = [
    'exchange_strict',
    'dex_router_interaction',
    'bridge_deposit',
    'hold_no_first_hop',
    'unknown_eoa',
    'unknown_contract'
  ];

  return order
    .filter((k) => shares[k] !== undefined)
    .map((k) => ({
      label: labelByKey[k] ?? k,
      valuePct: toNum(shares[k]),
      valueLabel: fmtPct(shares[k])
    }));
}

function graphFirstHopItems(metric) {
  const shares = metric?.first_hop_destinations?.category_withdrawn_share_percent ?? null;
  if (!shares) return [];
  const labelByKey = {
    unknown_eoa: 'Unknown EOA',
    unknown_contract: 'Unknown contract',
    no_first_hop_meeting_threshold: 'No first hop meeting threshold'
  };
  const order = ['unknown_eoa', 'unknown_contract', 'no_first_hop_meeting_threshold'];
  return order
    .filter((k) => shares[k] !== undefined)
    .map((k) => ({
      label: labelByKey[k] ?? k,
      valuePct: toNum(shares[k]),
      valueLabel: fmtPct(shares[k])
    }));
}

function livepeerSecondHopItems(metric) {
  if (!metric) return [];
  return [
    {
      label: 'Exchange endpoints (strict; labeled)',
      valuePct: toNum(metric.share_to_exchanges_lower_bound_percent),
      valueLabel: fmtPct(metric.share_to_exchanges_lower_bound_percent)
    },
    {
      label: 'Unknown EOAs (non-exchange)',
      valuePct: toNum(metric.share_to_unknown_eoas_percent),
      valueLabel: fmtPct(metric.share_to_unknown_eoas_percent)
    }
  ];
}

export default function LivepeerVsPeersComparison() {
  const labelCount = routing30d?.labels?.exchange_label_count ?? null;
  const generated30d = routing30d?.generated_at_utc ?? null;
  const generated3d = routing3d?.generated_at_utc ?? null;

  const metrics30d = routing30d?.metrics ?? {};
  const metrics3d = routing3d?.metrics ?? {};

  const exchangeRoutingRows = [
    {
      id: 'lp-l1-2hop',
      label: 'Livepeer (LPT) — L1 second-hop follow-up',
      metric: metrics30d?.livepeer_l1_second_hop,
      metric3d: null,
      hopsLabel: '1 hop',
      windowLabel: (() => {
        const rng = metrics30d?.livepeer_l1_second_hop?.selection?.block_range;
        const from = rng?.from_block;
        const to = rng?.to_block;
        return from && to ? `blocks ${fmtInt(from)}→${fmtInt(to)}` : 'block range (see pack)';
      })(),
      href: '/research/l1-bridge-recipient-second-hop'
    },
    {
      id: 'lp-timing',
      label: 'Livepeer (LPT) — L2→L1 timing traces',
      metric: metrics30d?.livepeer_extraction_timing_traces,
      metric3d: null,
      hopsLabel: '≤2 hops',
      windowLabel: '≤72h windows (see pack)',
      href: '/research/extraction-timing-traces'
    },
    {
      id: 'graph',
      label: 'The Graph (GRT) — delegation withdrawals',
      metric: metrics30d?.thegraph_delegation_withdrawal_routing,
      metric3d: metrics3d?.thegraph_delegation_withdrawal_routing,
      hopsLabel: '≤3 hops',
      windowLabel: `${fmtInt(metrics30d?.thegraph_delegation_withdrawal_routing?.selection?.window_days ?? 0)}d window`,
      href: '/research/thegraph-delegation-withdrawal-routing'
    },
    {
      id: 'curve',
      label: 'Curve (CRV) — veCRV withdraws',
      metric: metrics30d?.curve_vecrv_exit_routing,
      metric3d: metrics3d?.curve_vecrv_exit_routing,
      hopsLabel: '≤3 hops',
      windowLabel: `${fmtInt(metrics30d?.curve_vecrv_exit_routing?.selection?.window_days ?? 0)}d window`,
      href: '/research/curve-vecrv-exit-routing'
    },
    {
      id: 'frax',
      label: 'Frax (FXS) — veFXS withdraws',
      metric: metrics30d?.frax_vefxs_exit_routing,
      metric3d: metrics3d?.frax_vefxs_exit_routing,
      hopsLabel: '≤3 hops',
      windowLabel: `${fmtInt(metrics30d?.frax_vefxs_exit_routing?.selection?.window_days ?? 0)}d window`,
      href: '/research/frax-vefxs-exit-routing'
    },
    {
      id: 'aave',
      label: 'Aave (AAVE) — stkAAVE redeem',
      metric: metrics30d?.aave_stkaave_redeem_exit_routing,
      metric3d: metrics3d?.aave_stkaave_redeem_exit_routing,
      hopsLabel: '≤3 hops',
      windowLabel: `${fmtInt(metrics30d?.aave_stkaave_redeem_exit_routing?.selection?.window_days ?? 0)}d window`,
      href: '/research/aave-stkaave-redeem-exit-routing'
    }
  ].filter((r) => r.metric);

  const exitFriction = routing30d?.context?.exit_friction_snapshot?.protocols ?? {};

  const stake10k = stakeDist?.bands?.['10k+ LPT'] ?? null;
  const out10k = outflowsByBand?.bands?.['10k+ LPT'] ?? null;

  const rewardsTotals = rewardsWithdraw?.totals ?? {};
  const transferTotals = transferBond?.totals ?? {};
  const transferValidation = transferBond?.receipt_validation ?? {};
  const buyTotals = buyPressure?.selection_totals ?? {};
  const buyScan = buyPressure?.scan_totals ?? {};

  return (
    <>
      <p>This page is a side-by-side comparison built from the evidence packs in this repo.</p>
      <p>
        Important constraints:
        <br />- “Exchange routing” is a <strong>lower bound</strong> (label set + hop/window limits miss paths).
        <br />- “DEX router interaction” is <strong>heuristic</strong> (it does not prove trading; it’s a tx-level proxy).
      </p>
      <ul>
        <li>
          Exchange label set size: <strong>{labelCount ?? '—'}</strong> (<code>data/labels.json</code>)
        </li>
        <li>
          Generated: <code>{generated30d ?? '—'}</code> (30d packs), <code>{generated3d ?? '—'}</code> (3d sensitivity packs)
        </li>
      </ul>

      <h2>Exchange routing (lower bound)</h2>
      <ExchangeRoutingInfographic />

      <div className="lp-compare-table">
        <table>
          <thead>
            <tr>
              <th>Protocol / flow</th>
              <th>Window</th>
              <th>Hops</th>
              <th>Matched to exchanges (lower bound)</th>
              <th>Basis amount</th>
              <th>Events</th>
              <th>3d share</th>
            </tr>
          </thead>
          <tbody>
            {exchangeRoutingRows.map((r) => {
              const token = String(r.metric?.token ?? '');
              const share30 = toNum(r.metric?.share_to_exchanges_lower_bound_percent);
              const share3 = r.metric3d ? toNum(r.metric3d?.share_to_exchanges_lower_bound_percent) : null;
              const events = metricEvents(r.metric);
              const denom = denomAmount(r.metric);
              const numer = numerAmount(r.metric);

              const delta = share3 !== null ? share3 - share30 : null;
              const deltaLabel =
                delta === null ? '—' : delta === 0 ? '0.00pp' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}pp`;

              return (
                <tr key={r.id}>
                  <td>
                    <Link to={r.href}>{r.label}</Link>
                    <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
                      {String(r.metric?.denominator?.basis ?? r.metric?.flow ?? '')}
                    </div>
                  </td>
                  <td>{r.windowLabel}</td>
                  <td>{r.hopsLabel}</td>
                  <td>
                    <div>
                      <strong>
                        {fmtTok(numer)} {token}
                      </strong>{' '}
                      ({fmtPct(share30)})
                    </div>
                  </td>
                  <td>
                    {fmtTok(denom)} {token}
                  </td>
                  <td>{events !== null ? fmtInt(events) : '—'}</td>
                  <td>{share3 !== null ? `${fmtPct(share3)} (${deltaLabel})` : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h2>Post-exit behavior (DEX vs hold vs exchange)</h2>
      <p>These are “what happens next” heuristics for exit recipients (top recipients / top delegators depending on the pack).</p>

      <details>
        <summary>Curve (veCRV): post-exit roles (heuristic)</summary>
        <BarList
          title="Curve (veCRV) — post-exit roles"
          subtitle="Share of exited amount by role (top recipients; best-effort)."
          items={roleBarItems(metrics30d?.curve_vecrv_exit_routing)}
        />
        <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          Source: <Link to="/research/curve-vecrv-exit-routing">curve-vecrv-exit-routing</Link>
        </div>
      </details>

      <details>
        <summary>Frax (veFXS): post-exit roles (heuristic)</summary>
        <BarList
          title="Frax (veFXS) — post-exit roles"
          subtitle="Share of exited amount by role (top recipients; best-effort)."
          items={roleBarItems(metrics30d?.frax_vefxs_exit_routing)}
        />
        <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          Source: <Link to="/research/frax-vefxs-exit-routing">frax-vefxs-exit-routing</Link>
        </div>
      </details>

      <details>
        <summary>Aave (stkAAVE redeem): post-exit roles (heuristic)</summary>
        <BarList
          title="Aave (stkAAVE) — post-exit roles"
          subtitle="Share of exited amount by role (top recipients; best-effort)."
          items={roleBarItems(metrics30d?.aave_stkaave_redeem_exit_routing)}
        />
        <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          Source: <Link to="/research/aave-stkaave-redeem-exit-routing">aave-stkaave-redeem-exit-routing</Link>
        </div>
      </details>

      <details>
        <summary>The Graph: first hop destinations after withdrawal (not a DEX classifier)</summary>
        <BarList
          title="The Graph (GRT) — first hop destinations"
          subtitle="First meaningful outgoing GRT transfer after withdrawal (thresholded); category is label + (optional) EOA/contract."
          items={graphFirstHopItems(metrics30d?.thegraph_delegation_withdrawal_routing)}
        />
        <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          Source: <Link to="/research/thegraph-delegation-withdrawal-routing">thegraph-delegation-withdrawal-routing</Link>
        </div>
      </details>

      <details>
        <summary>Livepeer: L1 second-hop breakdown (exchange vs unknown EOAs)</summary>
        <BarList
          title="Livepeer (LPT) — L1 second hop"
          subtitle="For selected L1 EOAs: where their outgoing LPT goes on the next hop (best-effort)."
          items={livepeerSecondHopItems(metrics30d?.livepeer_l1_second_hop)}
        />
        <div style={{ opacity: 0.8, fontSize: '0.9rem' }}>
          Source: <Link to="/research/l1-bridge-recipient-second-hop">l1-bridge-recipient-second-hop</Link>
        </div>
      </details>

      <h2>Exit friction (principal unlock delay; what we have)</h2>
      <p>This is the “how long until principal can move” delay (not reward vesting).</p>

      <div className="lp-compare-table">
        <table>
          <thead>
            <tr>
              <th>Protocol</th>
              <th>Primitive</th>
              <th>Delay (estimate)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Livepeer</td>
              <td>
                <code>unbondingPeriod()</code>
              </td>
              <td>
                {exitFriction?.livepeer?.unbonding_period_rounds
                  ? `${fmtInt(exitFriction.livepeer.unbonding_period_rounds)} rounds`
                  : '—'}
              </td>
            </tr>
            <tr>
              <td>The Graph</td>
              <td>
                <code>thawingPeriod()</code>
              </td>
              <td>
                {exitFriction?.thegraph?.thawing_period_days_estimate
                  ? `${exitFriction.thegraph.thawing_period_days_estimate} days`
                  : '—'}
              </td>
            </tr>
            <tr>
              <td>Pocket</td>
              <td>supplier unbonding</td>
              <td>
                {exitFriction?.pocket?.supplier_unbonding_days_estimate
                  ? `${Number(exitFriction.pocket.supplier_unbonding_days_estimate).toFixed(2)} days`
                  : '—'}
              </td>
            </tr>
            <tr>
              <td>Akash</td>
              <td>
                <code>unbonding_time</code>
              </td>
              <td>{exitFriction?.akash?.unbonding_days_estimate ? `${exitFriction.akash.unbonding_days_estimate} days` : '—'}</td>
            </tr>
            <tr>
              <td>Theta</td>
              <td>
                <code>ReturnLockingPeriod</code>
              </td>
              <td>
                {exitFriction?.theta?.return_locking_period_days_observed
                  ? `${Number(exitFriction.theta.return_locking_period_days_observed).toFixed(2)} days (observed)`
                  : '—'}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Livepeer-only signals we have (in this repo)</h2>

      <h3>Concentration + exits by size band</h3>
      <ul>
        <li>
          Active bonded LPT total (snapshot): <strong>{stakeDist?.totals?.total_active_bonded_lpt ? fmtTok(stakeDist.totals.total_active_bonded_lpt) : '—'} LPT</strong>
        </li>
        <li>
          <code>10k+</code> bonded share:{' '}
          <strong>{stake10k?.share_of_active_bonded_lpt ? fmtPct(stake10k.share_of_active_bonded_lpt * 100) : '—'}</strong>{' '}
          (wallets: {stake10k?.active_delegators ? fmtInt(stake10k.active_delegators) : '—'})
        </li>
        <li>
          <code>10k+</code> withdraw share:{' '}
          <strong>{out10k?.share_of_withdraw_lpt ? fmtPct(out10k.share_of_withdraw_lpt * 100) : '—'}</strong>{' '}
          (withdrawers: {out10k?.withdrawers ? fmtInt(out10k.withdrawers) : '—'})
        </li>
      </ul>
      <p>
        Details: <Link to="/research/delegator-stake-distribution">delegator-stake-distribution</Link>,{' '}
        <Link to="/research/delegator-outflows-by-size-band">delegator-outflows-by-size-band</Link>.
      </p>

      <h3>Rewards claimed vs stake withdrawn (time series totals)</h3>
      <ul>
        <li>
          Rewards claimed: <strong>{rewardsTotals?.rewards_lpt ? fmtTok(rewardsTotals.rewards_lpt) : '—'} LPT</strong> (
          {rewardsTotals?.claim_events ? fmtInt(rewardsTotals.claim_events) : '—'} events)
        </li>
        <li>
          Stake withdrawn: <strong>{rewardsTotals?.withdraw_lpt ? fmtTok(rewardsTotals.withdraw_lpt) : '—'} LPT</strong> (
          {rewardsTotals?.withdraw_events ? fmtInt(rewardsTotals.withdraw_events) : '—'} events)
        </li>
      </ul>
      <p>
        Details: <Link to="/research/rewards-withdraw-timeseries">rewards-withdraw-timeseries</Link>.
      </p>

      <h3>Stake rotation / wallet rotation (TransferBond)</h3>
      <ul>
        <li>
          TransferBond events (last ~365d): <strong>{transferTotals?.transferbond_events ? fmtInt(transferTotals.transferbond_events) : '—'}</strong>
        </li>
        <li>
          Total transferred: <strong>{transferTotals?.total_transferred_lpt ? fmtTok(transferTotals.total_transferred_lpt) : '—'} LPT</strong>
        </li>
        <li>
          Receipt validation:{' '}
          <strong>
            {transferValidation?.validated_events ? fmtInt(transferValidation.validated_events) : '—'} /{' '}
            {transferTotals?.transferbond_events ? fmtInt(transferTotals.transferbond_events) : '—'}
          </strong>{' '}
          events matched Unbond+Rebond
        </li>
      </ul>
      <p>
        Details: <Link to="/research/livepeer-transferbond-rotation">livepeer-transferbond-rotation</Link>.
      </p>

      <h3>Buy-side proxy (labeled exchange outflows → bonders)</h3>
      <p>
        This is a proxy for “demand that results in new bonding”: exchange outflows on L1, then whether recipients appear in the Arbitrum delegator set and bond soon after the first inflow.
      </p>
      <ul>
        <li>
          Labeled exchange wallets scanned: <strong>{buyPressure?.exchange_wallets_scanned ? fmtInt(buyPressure.exchange_wallets_scanned) : '—'}</strong>
        </li>
        <li>
          Unique unlabeled recipients (any size): <strong>{buyScan?.unique_unlabeled_recipients ? fmtInt(buyScan.unique_unlabeled_recipients) : '—'}</strong>
        </li>
        <li>
          Total unlabeled recipient inbound: <strong>{buyScan?.total_unlabeled_recipient_inbound_lpt ? fmtTok(buyScan.total_unlabeled_recipient_inbound_lpt) : '—'} LPT</strong>
        </li>
        <li>
          Selected recipients (≥ {buyPressure?.parameters?.min_inbound_lpt ?? '—'} LPT):{' '}
          <strong>{buyTotals?.selected_recipients ? fmtInt(buyTotals.selected_recipients) : '—'}</strong>
        </li>
        <li>
          Selected recipients in Arbitrum delegator set: <strong>{buyTotals?.selected_delegators ? fmtInt(buyTotals.selected_delegators) : '—'}</strong>
        </li>
        <li>
          Bonded within {buyPressure?.parameters?.bond_window_days ?? '—'}d:{' '}
          <strong>{buyTotals?.bonded_within_window ? fmtInt(buyTotals.bonded_within_window) : '—'}</strong>
        </li>
      </ul>
      <p>
        Details: <Link to="/research/buy-pressure-proxies">buy-pressure-proxies</Link>.
      </p>
    </>
  );
}

