import React from 'react';
import Link from '@docusaurus/Link';
import clsx from 'clsx';

export default function Card({ title, href, children, className }) {
  return (
    <Link to={href} className={clsx('lp-card', className)}>
      <div className="lp-card__title">{title}</div>
      {children ? <div className="lp-card__body">{children}</div> : null}
    </Link>
  );
}

