import React from 'react';
import clsx from 'clsx';

export default function CardGroup({ cols = 2, children, className }) {
  const safeCols = Number.isFinite(cols) ? Math.max(1, Math.min(4, cols)) : 2;

  return (
    <div
      className={clsx(
        'lp-card-group',
        `lp-card-group--cols-${safeCols}`,
        className
      )}
    >
      {children}
    </div>
  );
}

