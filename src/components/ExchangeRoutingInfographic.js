import React from 'react';

import BarList from '@site/src/components/BarList';
import routing from '@site/research/exchange-routing-metrics.json';

function toPct(x) {
  const n = Number.parseFloat(String(x));
  return Number.isFinite(n) ? n : 0;
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
      <div className="lp-infographic__note">
        Lower bound: label set is intentionally incomplete; hop/window constraints miss some paths.
      </div>
    </div>
  );
}

