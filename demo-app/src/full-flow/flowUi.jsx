export function FlowStatus({ tone = 'neutral', children }) {
  return <span className={`flow-status flow-status-${tone}`}><i aria-hidden="true" /><span>{children}</span></span>
}

export function FlowEmpty({ title, detail }) {
  return <div className="flow-empty">
    <strong>{title}</strong>
    {detail ? <span>{detail}</span> : null}
  </div>
}

export function FlowPageHeading({ eyebrow, title, status }) {
  return <header className="flow-page-heading">
    <div>
      {eyebrow ? <span>{eyebrow}</span> : null}
      <h2>{title}</h2>
    </div>
    {status || null}
  </header>
}
