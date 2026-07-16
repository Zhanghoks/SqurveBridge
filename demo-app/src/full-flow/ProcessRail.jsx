const PROCESS_STEPS = ['configure', 'compose', 'run', 'inspect', 'diagnose', 'improve']

export default function ProcessRail({ t }) {
  return <nav className="flow-process-rail flow-glass" aria-label={t('process.ariaLabel')}>
    <ol>
      {PROCESS_STEPS.map((step, index) => <li key={step}>
        <a href={`#${step}`}>
          <span>{String(index + 1).padStart(2, '0')}</span>
          {t(`process.${step}`)}
        </a>
      </li>)}
    </ol>
  </nav>
}
