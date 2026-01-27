import React from 'react';

import BarList from '@site/src/components/BarList';
import routing from '@site/research/exchange-routing-metrics.json';

function toPct(x) {
  const n = Number.parseFloat(String(x));
  return Number.isFinite(n) ? n : 0;
}

function toPctHeuristic(m) {
  if (!m) return 0;
  const v =
    m.share_to_exchanges_or_bridges_heuristic_percent ??
    m.share_to_exchanges_lower_bound_percent;
  return toPct(v);
}

export default function ExchangeRoutingInfographic() {
  const metrics = routing?.metrics ?? {};

  const lp2 = metrics?.livepeer_l1_second_hop ?? {};
  const lpt = metrics?.livepeer_extraction_timing_traces ?? {};
  const tg = metrics?.thegraph_delegation_withdrawal_routing ?? {};
  const cv = metrics?.curve_vecrv_exit_routing ?? {};
  const fx = metrics?.frax_vefxs_exit_routing ?? {};
  const av = metrics?.aave_stkaave_redeem_exit_routing ?? {};

  const items = [
    {
      label: 'Livepeer (LPT) - L1 2nd hop follow-up',
      valuePct: toPct(lp2.share_to_exchanges_lower_bound_percent),
      href: '/research/l1-bridge-recipient-second-hop'
    },
    {
      label: 'Livepeer (LPT) - traced bridge-outs -> exchange',
      valuePct: toPct(lpt.share_to_exchanges_lower_bound_percent),
      href: '/research/extraction-timing-traces'
    },
    {
      label: 'The Graph (GRT) - withdrawals -> exchange',
      valuePct: toPct(tg.share_to_exchanges_lower_bound_percent),
      href: '/research/thegraph-delegation-withdrawal-routing'
    },
    {
      label: 'Curve (CRV) - veCRV withdraws -> exchange',
      valuePct: toPct(cv.share_to_exchanges_lower_bound_percent),
      href: '/research/curve-vecrv-exit-routing'
    },
    {
      label: 'Frax (FXS) - veFXS withdraws -> exchange',
      valuePct: toPct(fx.share_to_exchanges_lower_bound_percent),
      href: '/research/frax-vefxs-exit-routing'
    },
    {
      label: 'Aave (AAVE) - stkAAVE redeem -> exchange',
      valuePct: toPct(av.share_to_exchanges_lower_bound_percent),
      href: '/research/aave-stkaave-redeem-exit-routing'
    }
  ];

  const heuristicItems = [
    {
      label: 'Livepeer (LPT) - L1 2nd hop follow-up',
      valuePct: toPctHeuristic(lp2),
      href: '/research/l1-bridge-recipient-second-hop'
    },
    {
      label: 'Livepeer (LPT) - traced bridge-outs -> exchange',
      valuePct: toPctHeuristic(lpt),
      href: '/research/extraction-timing-traces'
    },
    {
      label: 'The Graph (GRT) - withdrawals -> exchange',
      valuePct: toPctHeuristic(tg),
      href: '/research/thegraph-delegation-withdrawal-routing'
    },
    {
      label: 'Curve (CRV) - veCRV withdraws -> exchange/bridge',
      valuePct: toPctHeuristic(cv),
      href: '/research/curve-vecrv-exit-routing'
    },
    {
      label: 'Frax (FXS) - veFXS withdraws -> exchange/bridge',
      valuePct: toPctHeuristic(fx),
      href: '/research/frax-vefxs-exit-routing'
    },
    {
      label: 'Aave (AAVE) - stkAAVE redeem -> exchange/bridge',
      valuePct: toPctHeuristic(av),
      href: '/research/aave-stkaave-redeem-exit-routing'
    }
  ];

  const arbItems = [
    {
      label: 'Curve (CRV) - bridged to Arbitrum -> exchange',
      valuePct: toPct(cv?.arbitrum_followup?.matched_exit_share_of_total_exited_percent),
      href: '/research/curve-vecrv-exit-routing',
      enabled: Boolean(cv?.arbitrum_followup?.enabled)
    },
    {
      label: 'Frax (FXS) - bridged to Arbitrum -> exchange',
      valuePct: toPct(fx?.arbitrum_followup?.matched_exit_share_of_total_exited_percent),
      href: '/research/frax-vefxs-exit-routing',
      enabled: Boolean(fx?.arbitrum_followup?.enabled)
    },
    {
      label: 'Aave (AAVE) - bridged to Arbitrum -> exchange',
      valuePct: toPct(av?.arbitrum_followup?.matched_exit_share_of_total_exited_percent),
      href: '/research/aave-stkaave-redeem-exit-routing',
      enabled: Boolean(av?.arbitrum_followup?.enabled)
    }
  ].filter((x) => x.enabled);

  const labelCount = routing?.labels?.exchange_label_count ?? null;
  const generatedAt = routing?.generated_at_utc ?? null;

  return (
    <div className="lp-infographic">
      <BarList
        title="Exchange routing (lower bound)"
        subtitle={
          labelCount && generatedAt
            ? `Label set size: ${labelCount} exchange endpoints; generated: ${generatedAt}`
            : labelCount
              ? `Label set size: ${labelCount} exchange endpoints`
              : generatedAt
                ? `Generated: ${generatedAt}`
                : null
        }
        items={items}
      />
      <BarList
        title="Exchange or bridge (heuristic)"
        subtitle="Strict exchange routing + (non-exchange) bridge deposits when detectable; still a lower bound."
        items={heuristicItems}
      />
      {arbItems.length > 0 ? (
        <BarList
          title="Arbitrum follow-up (lower bound)"
          subtitle="After exit: detect canonical Arbitrum bridge deposits on L1, then check Arbitrum transfers into labeled exchanges."
          items={arbItems}
        />
      ) : null}
      <div className="lp-infographic__note">
        Lower bound: label set is intentionally incomplete; hop/window constraints miss some paths.
      </div>
    </div>
  );
}
