import './studio-status.css'

const RUNNING_PHASES = new Set([
  'loadingData',
  'buildingWorkflow',
  'generatingSql',
  'executingSql',
  'evaluating',
])

export function runPhaseStatusKey(phase) {
  if (!phase || phase === 'ready') return 'status.ready'
  if (phase === 'completed') return 'status.completed'
  if (phase === 'failed') return 'status.failed'
  if (RUNNING_PHASES.has(phase)) return 'status.running'
  return 'status.ready'
}

// Personal-workspace status strip for the Studio page. Reads only local
// session state already held by the shell; never renders credentials.
export default function StudioStatusBar({
  connectionCount = 0,
  focusedMethod = '',
  focusedDatabase = '',
  credentialConfigured = false,
  credentialLabel = '',
  runPhase = 'ready',
  onNavigate,
  t,
}) {
  const runStatusKey = runPhaseStatusKey(runPhase)
  const focusLabel = focusedMethod && focusedDatabase
    ? `${focusedMethod} × ${focusedDatabase}`
    : t('studioStatus.focusEmpty')

  const items = [
    {
      id: 'connections',
      label: t('studioStatus.connections'),
      value: t('studioStatus.connectionsValue', { count: connectionCount }),
      target: 'compose',
      targetLabel: t('process.compose'),
    },
    {
      id: 'focus',
      label: t('studioStatus.focus'),
      value: focusLabel,
      target: 'query',
      targetLabel: t('process.query'),
    },
    {
      id: 'credential',
      label: t('studioStatus.credential'),
      value: credentialConfigured
        ? (credentialLabel || t('studioStatus.credentialConfigured'))
        : t('studioStatus.credentialMissing'),
      tone: credentialConfigured ? 'ok' : 'warn',
      target: 'query',
      targetLabel: t('process.query'),
    },
    {
      id: 'run',
      label: t('studioStatus.run'),
      value: t(runStatusKey),
      tone: runStatusKey === 'status.failed'
        ? 'warn'
        : runStatusKey === 'status.running' || runStatusKey === 'status.completed'
          ? 'ok'
          : undefined,
      target: 'board',
      targetLabel: t('process.board'),
    },
  ]

  return (
    <aside
      className="studio-status-bar flow-glass"
      data-testid="studio-status-bar"
      aria-label={t('studioStatus.title')}
    >
      <div className="studio-status-heading">
        <strong>{t('studioStatus.title')}</strong>
        <span>{t('studioStatus.localNote')}</span>
      </div>
      <ul className="studio-status-items">
        {items.map(item => (
          <li key={item.id}>
            <button
              type="button"
              className="studio-status-item"
              data-testid={`studio-status-${item.id}`}
              aria-label={`${item.label} · ${t('studioStatus.goto', { tab: item.targetLabel })}`}
              onClick={() => onNavigate?.(item.target)}
            >
              <span className="studio-status-label">{item.label}</span>
              <b
                className="studio-status-value"
                data-tone={item.tone || 'neutral'}
              >
                {item.value}
              </b>
              <span className="studio-status-hint" aria-hidden="true">
                {t('studioStatus.goto', { tab: item.targetLabel })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
