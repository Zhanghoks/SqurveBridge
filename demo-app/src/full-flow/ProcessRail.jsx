export const PROCESS_STEPS = ['configure', 'compose', 'run', 'inspect', 'diagnose', 'improve']

export function resolveProcessStep(hashOrId, fallback = PROCESS_STEPS[0]) {
  const value = String(hashOrId || '').replace(/^#/, '')
  return PROCESS_STEPS.includes(value) ? value : fallback
}

export default function ProcessRail({ activeStep, onNavigate, t }) {
  return (
    <nav className="flow-process-rail flow-glass" aria-label={t('process.ariaLabel')}>
      <div className="flow-process-rail-label">{t('process.navLabel')}</div>
      <ol>
        {PROCESS_STEPS.map((step, index) => {
          const active = activeStep === step
          const label = t(`process.${step}`)
          return (
            <li key={step}>
              <button
                type="button"
                className={active ? 'active' : ''}
                aria-current={active ? 'page' : undefined}
                aria-label={t('process.goTo', {
                  name: label,
                })}
                onClick={() => onNavigate(step)}
              >
                <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <strong>{label}</strong>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
