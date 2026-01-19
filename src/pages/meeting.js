import React, { useEffect, useMemo, useState } from 'react';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './meeting.module.css';

const BAND_ORDER = [
  '<1 LPT',
  '1–10 LPT',
  '10–100 LPT',
  '100–1k LPT',
  '1k–10k LPT',
  '10k+ LPT',
];

const BAND_COLORS = [
  '#00e7ab',
  '#36f2c1',
  '#77f7d8',
  '#77a6ff',
  '#b98bff',
  '#ff7ad9',
];

function formatInt(x) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(
    Math.round(x)
  );
}

function formatPct01(x, digits = 1) {
  if (typeof x !== 'number' || !Number.isFinite(x)) return '—';
  return `${(x * 100).toFixed(digits)}%`;
}

function formatLptShort(x) {
  const n = typeof x === 'number' ? x : Number.parseFloat(x);
  if (!Number.isFinite(n)) return '—';
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(2)}k`;
  return formatInt(n);
}

function safeNumber(x) {
  if (typeof x === 'number') return x;
  if (typeof x === 'string') return Number.parseFloat(x);
  return NaN;
}

function DonutChart({ title, centerLabel, segments }) {
  const total = useMemo(() => segments.reduce((acc, s) => acc + s.value, 0), [
    segments,
  ]);

  const normalized = useMemo(() => {
    if (!Number.isFinite(total) || total <= 0) return [];
    let cumulative = 0;
    return segments.map((s) => {
      const pct = (s.value / total) * 100;
      const dashArray = `${pct} ${100 - pct}`;
      const dashOffset = 25 - cumulative;
      cumulative += pct;
      return { ...s, pct, dashArray, dashOffset };
    });
  }, [segments, total]);

  return (
    <div className={styles.donutCard}>
      <div className={styles.cardTitle}>{title}</div>
      <div className={styles.donutRow}>
        <div className={styles.donutSvgWrap}>
          <svg viewBox="0 0 42 42" className={styles.donutSvg}>
            <circle
              cx="21"
              cy="21"
              r="15.91549430918954"
              fill="transparent"
              stroke="rgba(255,255,255,0.10)"
              strokeWidth="5.5"
            />
            {normalized.map((s) => (
              <circle
                key={s.label}
                cx="21"
                cy="21"
                r="15.91549430918954"
                fill="transparent"
                stroke={s.color}
                strokeWidth="5.5"
                strokeDasharray={s.dashArray}
                strokeDashoffset={s.dashOffset}
                strokeLinecap="butt"
              />
            ))}
          </svg>
          <div className={styles.donutCenter}>
            <div className={styles.donutCenterLabel}>{centerLabel}</div>
            <div className={styles.donutCenterSub}>total</div>
          </div>
        </div>

        <div className={styles.legend}>
          {segments.map((s) => (
            <div key={s.label} className={styles.legendRow}>
              <span
                className={styles.legendSwatch}
                style={{ background: s.color }}
              />
              <span className={styles.legendLabel}>{s.label}</span>
              <span className={styles.legendValue}>
                {formatPct01(total ? s.value / total : NaN, 1)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Sparkline({ values, stroke = 'var(--ifm-color-primary)' }) {
  const width = 260;
  const height = 64;

  const path = useMemo(() => {
    const xs = values.filter((v) => typeof v === 'number' && Number.isFinite(v));
    if (xs.length < 2) return '';

    const min = Math.min(...xs);
    const max = Math.max(...xs);
    const range = max - min || 1;

    const points = values.map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return [x, y];
    });

    return points
      .map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`)
      .join(' ');
  }, [values]);

  return (
    <svg
      className={styles.sparkline}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
      {sub ? <div className={styles.statSub}>{sub}</div> : null}
    </div>
  );
}

export default function Meeting() {
  const dataUrl = useBaseUrl('/data/meeting-dashboard.json');
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(dataUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (alive) setPayload(d);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [dataUrl]);

  const { latest, series } = payload || {};

  const derived = useMemo(() => {
    if (!latest || !series || !Array.isArray(series) || series.length === 0)
      return null;

    const baseline =
      series.find((s) => s.label === '2023-09-end') || series[0] || null;

    const latestBonded = safeNumber(latest.total_bonded_lpt);
    const latestDelegators = latest.active_delegators;
    const latestDelegates = latest.concentration?.delegates?.active_delegates;

    const delegatesTop10 = latest.concentration?.delegates?.top_share?.['10'];
    const delegatorsTop10 = latest.concentration?.delegators?.top_share?.['10'];

    const nak33 = latest.concentration?.delegates?.nakamoto?.['33%'];
    const nak50 = latest.concentration?.delegates?.nakamoto?.['50%'];

    const delegatesGe100k = latest.concentration?.delegates?.delegates_ge_100k;
    const delegatesGe1m = latest.concentration?.delegates?.delegates_ge_1m;

    const bandKeys = BAND_ORDER.filter((k) => latest.bands && latest.bands[k]);
    const walletSegments = bandKeys.map((label, i) => ({
      label,
      value: safeNumber(latest.bands[label].active_delegators),
      color: BAND_COLORS[i] || '#999',
    }));
    const stakeSegments = bandKeys.map((label, i) => ({
      label,
      value: safeNumber(latest.bands[label].bonded_lpt),
      color: BAND_COLORS[i] || '#999',
    }));

    const seriesDelegatesTop10 = series
      .map((s) => safeNumber(s.delegates_top10_share))
      .filter((v) => Number.isFinite(v));
    const seriesActiveDelegators = series
      .map((s) => safeNumber(s.active_delegators))
      .filter((v) => Number.isFinite(v));

    const baselineTop10 = safeNumber(baseline?.delegates_top10_share);
    const baselineNak33 = safeNumber(baseline?.nakamoto_33);

    const keyBullets = [
      `Bonded stake: ${formatLptShort(latestBonded)} LPT across ${formatInt(
        latestDelegators
      )} active delegator wallets.`,
      `Delegate concentration: top10 delegates control ${formatPct01(
        delegatesTop10
      )} of bonded stake; Nakamoto(33%) = ${nak33}, Nakamoto(50%) = ${nak50}.`,
      `Delegator concentration: top10 wallets hold ${formatPct01(
        delegatorsTop10
      )} (Gini ${latest.concentration?.delegators?.gini?.toFixed?.(3) ?? '—'}).`,
      `Active delegates: ${formatInt(
        latestDelegates
      )} total; ${formatInt(delegatesGe100k)} delegates ≥100k, ${formatInt(
        delegatesGe1m
      )} delegates ≥1m.`,
      baseline
        ? `Since ${baseline.label}: top10 delegate share moved ${formatPct01(
            baselineTop10
          )} → ${formatPct01(
            delegatesTop10
          )}; Nakamoto(33%) moved ${baselineNak33} → ${nak33}.`
        : null,
    ].filter(Boolean);

    const topDelegates =
      latest.concentration?.delegates?.top_delegates?.slice?.(0, 10) || [];

    return {
      latestBonded,
      latestDelegators,
      latestDelegates,
      delegatesTop10,
      delegatorsTop10,
      nak33,
      nak50,
      walletSegments,
      stakeSegments,
      seriesDelegatesTop10,
      seriesActiveDelegators,
      keyBullets,
      topDelegates,
    };
  }, [latest, series]);

  return (
    <Layout title="Meeting Dashboard" description="Livepeer delegation findings (meeting view)">
      <main className={styles.page}>
        <div className={styles.wrap}>
          <div className={styles.hero}>
            <div>
              <div className={styles.kicker}>Meeting view</div>
              <h1 className={styles.title}>Livepeer Delegation — Key Findings</h1>
              <div className={styles.subtitle}>
                Arbitrum One · Snapshot:{' '}
                <span className={styles.mono}>
                  {latest?.snapshot_iso || 'loading…'}
                </span>
              </div>
            </div>
            <div className={styles.heroMeta}>
              <div className={styles.metaPill}>
                Data: <span className={styles.mono}>eth_getLogs</span>
              </div>
              <div className={styles.metaPill}>
                Source:{' '}
                <span className={styles.mono}>research/delegator-band-timeseries</span>
              </div>
            </div>
          </div>

          {error ? (
            <div className={styles.errorBox}>
              Failed to load dashboard data: <span className={styles.mono}>{error}</span>
            </div>
          ) : null}

          {!derived ? (
            <div className={styles.loading}>Loading…</div>
          ) : (
            <>
              <div className={styles.statsGrid}>
                <StatCard
                  label="Total bonded stake"
                  value={`${formatLptShort(derived.latestBonded)} LPT`}
                  sub={`(${formatInt(derived.latestBonded)} LPT)`}
                />
                <StatCard
                  label="Active delegator wallets"
                  value={formatInt(derived.latestDelegators)}
                  sub="bonded stake > 0"
                />
                <StatCard
                  label="Active delegates"
                  value={formatInt(derived.latestDelegates)}
                  sub="delegate addresses with stake"
                />
                <StatCard
                  label="Top10 delegate share"
                  value={formatPct01(derived.delegatesTop10, 1)}
                  sub={`Nakamoto(33%)=${derived.nak33} · (50%)=${derived.nak50}`}
                />
              </div>

              <div className={styles.twoCol}>
                <DonutChart
                  title="Wallet distribution by stake band"
                  centerLabel={formatInt(derived.latestDelegators)}
                  segments={derived.walletSegments}
                />
                <DonutChart
                  title="Stake distribution by stake band"
                  centerLabel={`${formatLptShort(derived.latestBonded)} LPT`}
                  segments={derived.stakeSegments}
                />
              </div>

              <div className={styles.twoCol}>
                <div className={styles.bulletsCard}>
                  <div className={styles.cardTitle}>Key takeaways</div>
                  <ul className={styles.bullets}>
                    {derived.keyBullets.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>

                <div className={styles.trendsCard}>
                  <div className={styles.cardTitle}>Trends (monthly)</div>
                  <div className={styles.trendRow}>
                    <div className={styles.trendText}>
                      <div className={styles.trendLabel}>Active delegators</div>
                      <div className={styles.trendValue}>
                        {formatInt(derived.latestDelegators)}
                      </div>
                    </div>
                    <Sparkline values={derived.seriesActiveDelegators} />
                  </div>
                  <div className={styles.trendRow}>
                    <div className={styles.trendText}>
                      <div className={styles.trendLabel}>Top10 delegate share</div>
                      <div className={styles.trendValue}>
                        {formatPct01(derived.delegatesTop10)}
                      </div>
                    </div>
                    <Sparkline values={derived.seriesDelegatesTop10} />
                  </div>
                </div>
              </div>

              <div className={styles.tableCard}>
                <div className={styles.cardTitle}>Top delegates (latest)</div>
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Delegate</th>
                        <th>Bonded LPT</th>
                        <th>Share</th>
                      </tr>
                    </thead>
                    <tbody>
                      {derived.topDelegates.map((d, i) => (
                        <tr key={d.delegate}>
                          <td>{i + 1}</td>
                          <td className={styles.mono}>{d.delegate}</td>
                          <td>{formatInt(safeNumber(d.bonded_lpt))}</td>
                          <td>{formatPct01(safeNumber(d.share_of_bonded_lpt))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className={styles.footerHint}>
                Tip: run <span className={styles.mono}>npm run meeting</span> then open{' '}
                <span className={styles.mono}>/meeting</span>.
              </div>
            </>
          )}
        </div>
      </main>
    </Layout>
  );
}

