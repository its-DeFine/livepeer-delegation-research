import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';

function formatPct(x) {
  if (!Number.isFinite(x)) return '';
  return `${x.toFixed(2)}%`;
}

export default function BarList({ title, subtitle, items, className }) {
  const safeItems = Array.isArray(items) ? items : [];

  return (
    <section className={clsx('lp-barlist', className)}>
      {(title || subtitle) && (
        <header className="lp-barlist__header">
          {title && <div className="lp-barlist__title">{title}</div>}
          {subtitle && <div className="lp-barlist__subtitle">{subtitle}</div>}
        </header>
      )}

      <div className="lp-barlist__rows">
        {safeItems.map((it, idx) => {
          const label = String(it?.label ?? '');
          const valuePct = Number(it?.valuePct ?? 0);
          const href = it?.href ? String(it.href) : null;
          const valueLabel = it?.valueLabel ? String(it.valueLabel) : formatPct(valuePct);

          return (
            <div className="lp-barlist__row" key={`${label}-${idx}`}>
              <div className="lp-barlist__label">
                {href ? <Link to={href}>{label}</Link> : label}
              </div>
              <div className="lp-barlist__track" aria-hidden="true">
                <div
                  className="lp-barlist__fill"
                  style={{ width: `${Math.max(0, Math.min(100, valuePct))}%` }}
                />
              </div>
              <div className="lp-barlist__value">{valueLabel}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

