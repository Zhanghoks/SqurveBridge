import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { detectLocale, setDocumentLocale, translate } from '../i18n/index.js'
import BoardWorkspace from './BoardWorkspace.jsx'
import ConfigurationStudio from './ConfigurationStudio.jsx'
import ConnectionComposer from './ConnectionComposer.jsx'
import EvidenceHub from './EvidenceHub.jsx'
import {
  DATABASES,
  METHODS,
  ensureConnection,
  resolveFocusedConfig,
  selectedDatabasesFromConnections,
  selectedMethodsFromConnections,
  toggleConnection,
  toggleDatabaseConnections,
  toggleMethodConnections,
  withConnectionKeys,
} from './model.js'
import { PROCESS_STEPS, resolveProcessStep } from './ProcessRail.jsx'
import { INITIAL_RUN_STATE } from './RunWorkspace.jsx'
import { FlowStatus } from './flowUi.jsx'
import './full-flow.css'
import './agent-shell.css'

const AgentHarness = lazy(() => import('../AgentHarness.jsx'))
const SPLIT_STORAGE_KEY = 'squrve-demo-shell-layout'

function loadShellLayout() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(SPLIT_STORAGE_KEY) || '{}')
    return {
      dashboardWidth: Math.min(75, Math.max(35, Number(saved.dashboardWidth) || 62)),
      dashboardCollapsed: Boolean(saved.dashboardCollapsed),
      agentCollapsed: Boolean(saved.agentCollapsed),
    }
  } catch {
    return { dashboardWidth: 62, dashboardCollapsed: false, agentCollapsed: false }
  }
}

export default function FullFlowDemo({
  capabilities,
  databases = [],
  sqlAuth,
  postJson,
  api,
  onConfigureSql,
  credentialMode = 'session',
}) {
  const configs = capabilities?.reproduce_configs || []
  const [locale, setLocale] = useState(() => detectLocale(
    navigator.language,
    window.localStorage.getItem('squrve-demo-locale'),
  ))
  const [activeStep, setActiveStep] = useState(() => resolveProcessStep(window.location.hash))
  const [selectedConnections, setSelectedConnections] = useState([
    { method: METHODS[0], database: DATABASES[0] },
  ])
  const [focusedMethod, setFocusedMethod] = useState(METHODS[0])
  const [focusedDatabase, setFocusedDatabase] = useState(DATABASES[0])
  const [sampleLimit, setSampleLimit] = useState(20)
  const [sampleMode, setSampleMode] = useState('slice')
  const [sampleSeed, setSampleSeed] = useState(42)
  const [runState, setRunState] = useState(INITIAL_RUN_STATE)
  const [archiveFocusRunId, setArchiveFocusRunId] = useState('')
  const [chatKey, setChatKey] = useState(0)
  const [harnessTask, setHarnessTask] = useState(null)
  const [shellLayout, setShellLayout] = useState(loadShellLayout)
  const [mobilePane, setMobilePane] = useState('dashboard')
  const splitRef = useRef(null)
  const t = useCallback((key, params) => translate(locale, key, params), [locale])
  const focusedConfig = resolveFocusedConfig(configs, focusedMethod, focusedDatabase)
  const selectedMethods = selectedMethodsFromConnections(selectedConnections)
  const selectedDatabases = selectedDatabasesFromConnections(selectedConnections)
  const connections = withConnectionKeys(selectedConnections)

  useEffect(() => {
    window.localStorage.setItem('squrve-demo-locale', locale)
    setDocumentLocale(locale)
  }, [locale])

  useEffect(() => {
    window.localStorage.setItem(SPLIT_STORAGE_KEY, JSON.stringify(shellLayout))
  }, [shellLayout])

  useEffect(() => {
    const syncFromHash = () => setActiveStep(resolveProcessStep(window.location.hash))
    window.addEventListener('hashchange', syncFromHash)
    return () => window.removeEventListener('hashchange', syncFromHash)
  }, [])

  const navigateToStep = useCallback(step => {
    const next = resolveProcessStep(step)
    setActiveStep(next)
    if (window.location.hash !== `#${next}`) {
      window.history.replaceState(null, '', `#${next}`)
    }
  }, [])

  const applyFocus = (method, database) => {
    setFocusedMethod(method)
    setFocusedDatabase(database)
  }

  const syncFocus = (next, preferredMethod = focusedMethod, preferredDatabase = focusedDatabase) => {
    const preferred = next.find(item =>
      item.method === preferredMethod && item.database === preferredDatabase,
    )
    const byMethod = next.find(item => item.method === preferredMethod)
    const byDatabase = next.find(item => item.database === preferredDatabase)
    const target = preferred || byMethod || byDatabase || next[0]
    applyFocus(target.method, target.database)
  }

  const toggleMethod = method => {
    const next = toggleMethodConnections(selectedConnections, method)
    setSelectedConnections(next)
    syncFocus(next, method, focusedDatabase)
  }

  const toggleDatabase = database => {
    const next = toggleDatabaseConnections(selectedConnections, database)
    setSelectedConnections(next)
    syncFocus(next, focusedMethod, database)
  }

  const onToggleConnection = (method, database) => {
    const next = toggleConnection(selectedConnections, method, database)
    setSelectedConnections(next)
    if (next.some(item => item.method === method && item.database === database)) {
      applyFocus(method, database)
      return
    }
    syncFocus(next)
  }

  const onFocusConnection = (method, database) => {
    const next = ensureConnection(selectedConnections, method, database)
    setSelectedConnections(next)
    applyFocus(method, database)
  }

  const openArchiveInVisualize = runId => {
    setArchiveFocusRunId(runId)
    navigateToStep('visualize')
  }

  const selection = {
    selectedMethods,
    selectedDatabases,
    selectedConnections: connections,
    focusedMethod,
    focusedDatabase,
    onToggleMethod: toggleMethod,
    onToggleDatabase: toggleDatabase,
    onToggleConnection,
    onFocusConnection,
  }
  const sampling = {
    sampleLimit,
    sampleMode,
    sampleSeed,
    onSampleLimitChange: setSampleLimit,
    onSampleModeChange: setSampleMode,
    onSampleSeedChange: setSampleSeed,
  }

  const pages = {
    configure: (
      <ConfigurationStudio
        hostedReadOnly={credentialMode !== 'local'}
        t={t}
      />
    ),
    compose: (
      <ConnectionComposer
        {...selection}
        configs={configs}
        focusedConfig={focusedConfig}
        t={t}
      />
    ),
    board: (
      <BoardWorkspace
        selectedConnections={connections}
        configs={configs}
        focusedMethod={focusedMethod}
        focusedDatabase={focusedDatabase}
        onFocusConnection={onFocusConnection}
        databases={databases}
        sampleLimit={sampleLimit}
        sampleMode={sampleMode}
        sampleSeed={sampleSeed}
        onSampleLimitChange={setSampleLimit}
        onSampleModeChange={setSampleMode}
        onSampleSeedChange={setSampleSeed}
        postJson={postJson}
        api={api}
        onRunStateChange={setRunState}
        liveEvaluation={Boolean(capabilities?.deployment?.features?.live_evaluation)}
        t={t}
      />
    ),
    visualize: (
      <EvidenceHub
        pageId="visualize"
        initialTab="visualize"
        capabilities={capabilities}
        api={api}
        postJson={postJson}
        liveEvaluation={Boolean(capabilities?.deployment?.features?.live_evaluation)}
        focusedConfig={focusedConfig}
        selectedMethods={selectedMethods}
        sampleLimit={sampleLimit}
        sampleMode={sampleMode}
        sampleSeed={sampleSeed}
        archiveFocusRunId={archiveFocusRunId}
        onClearArchiveFocus={() => setArchiveFocusRunId('')}
        onNavigate={navigateToStep}
        t={t}
      />
    ),
    archive: (
      <EvidenceHub
        pageId="archive"
        initialTab="archive"
        capabilities={capabilities}
        api={api}
        postJson={postJson}
        focusedConfig={focusedConfig}
        selectedMethods={selectedMethods}
        sampleLimit={sampleLimit}
        sampleMode={sampleMode}
        sampleSeed={sampleSeed}
        t={t}
        onNavigate={navigateToStep}
        onOpenInVisualize={openArchiveInVisualize}
      />
    ),
  }

  const nextLocale = locale === 'zh-CN' ? 'en-US' : 'zh-CN'
  const languageLabel = locale === 'zh-CN'
    ? t('language.switchToEnglish')
    : t('language.switchToChinese')
  const projectLabel = focusedConfig
    ? `${focusedConfig.method} · ${focusedConfig.dataset}`
    : t('shell.workspace')
  const dashboardCollapsed = shellLayout.dashboardCollapsed && !shellLayout.agentCollapsed
  const agentCollapsed = shellLayout.agentCollapsed && !shellLayout.dashboardCollapsed
  const shellStyle = {
    '--dashboard-width': `${shellLayout.dashboardWidth}%`,
  }

  const setCollapsed = pane => {
    setShellLayout(current => pane === 'dashboard'
      ? { ...current, dashboardCollapsed: !current.dashboardCollapsed, agentCollapsed: false }
      : { ...current, agentCollapsed: !current.agentCollapsed, dashboardCollapsed: false })
  }

  const startResize = event => {
    if (dashboardCollapsed || agentCollapsed || window.matchMedia('(max-width: 899px)').matches) return
    event.preventDefault()
    const root = splitRef.current
    if (!root) return
    const bounds = root.getBoundingClientRect()
    const onMove = moveEvent => {
      const next = ((moveEvent.clientX - bounds.left) / bounds.width) * 100
      setShellLayout(current => ({
        ...current,
        dashboardWidth: Math.min(75, Math.max(35, next)),
      }))
    }
    const stop = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', stop)
      document.body.classList.remove('agent-shell-resizing')
    }
    document.body.classList.add('agent-shell-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', stop, { once: true })
  }

  return (
    <main
      className={[
        'flow-demo agent-shell',
        dashboardCollapsed ? 'dashboard-collapsed' : '',
        agentCollapsed ? 'agent-collapsed' : '',
        `mobile-pane-${mobilePane}`,
      ].filter(Boolean).join(' ')}
      data-testid="agent-shell"
      style={shellStyle}
    >
      <div className="agent-shell-notice">
        {t(credentialMode === 'local' ? 'local.notice' : 'hosted.notice')}
      </div>

      <div className="agent-mobile-switcher" role="tablist" aria-label={t('shell.workspace')}>
        <button type="button" role="tab" aria-selected={mobilePane === 'dashboard'} onClick={() => setMobilePane('dashboard')}>
          {t('shell.liveWorkspace')}
        </button>
        <button type="button" role="tab" aria-selected={mobilePane === 'agent'} onClick={() => setMobilePane('agent')}>
          {t('shell.piBackend')}
        </button>
      </div>

      <div className="agent-shell-panes" ref={splitRef}>
        <section className="agent-dashboard-pane" aria-label={t('shell.liveWorkspace')}>
          <div className="agent-dashboard-surface">
            <header className="agent-dashboard-header">
              <div className="agent-dashboard-identity">
                <span className="agent-dashboard-kicker">SqurveBridge</span>
                <h1>{t(`process.${activeStep}`)}</h1>
                <span className="agent-chat-project">
                  <b>{projectLabel}</b>
                  <span>{t('header.configCount', { count: configs.length })}</span>
                </span>
              </div>
              <div className="agent-dashboard-actions">
                <button type="button" onClick={onConfigureSql}>
                  {t(credentialMode === 'local' ? 'header.configureLocalApi' : 'header.configureApi')}
                </button>
                <button type="button" aria-label={languageLabel} onClick={() => setLocale(nextLocale)}>
                  {languageLabel}
                </button>
                <button
                  type="button"
                  className="agent-pane-toggle"
                  aria-label={t('shell.collapseDashboard')}
                  onClick={() => setCollapsed('dashboard')}
                >
                  ‹
                </button>
              </div>
            </header>
            <nav className="agent-stage-tabs" aria-label={t('shell.stageTabs')}>
              {PROCESS_STEPS.map(step => (
                <button
                  key={step}
                  type="button"
                  className={activeStep === step ? 'active' : ''}
                  aria-current={activeStep === step ? 'page' : undefined}
                  onClick={() => navigateToStep(step)}
                >
                  {t(`process.${step}`)}
                </button>
              ))}
            </nav>
          <div className="agent-live-workspace-head">
            <h2>
              <span className="agent-live-dot" aria-hidden="true" />
              {t('shell.liveWorkspace')}
            </h2>
            <div className="agent-live-workspace-actions">
              <button type="button" aria-label={t('process.previous')} onClick={() => {
                const index = PROCESS_STEPS.indexOf(activeStep)
                if (index > 0) navigateToStep(PROCESS_STEPS[index - 1])
              }}>
                ‹
              </button>
              <button type="button" aria-label={t('process.next')} onClick={() => {
                const index = PROCESS_STEPS.indexOf(activeStep)
                if (index < PROCESS_STEPS.length - 1) navigateToStep(PROCESS_STEPS[index + 1])
              }}>
                ›
              </button>
            </div>
          </div>
          <div
            className="agent-live-workspace-body"
            data-testid="flow-stage"
            data-active-step={activeStep}
          >
            {PROCESS_STEPS.map(step => (
              <div
                key={step}
                className="flow-stage-page"
                data-testid={`flow-stage-${step}`}
                hidden={activeStep !== step}
              >
                {pages[step]}
              </div>
            ))}
          </div>
          <footer className="agent-live-workspace-foot">
            <span>{t('shell.workspaceFoot')}</span>
            <span>
              {runState?.phase && runState.phase !== 'ready'
                ? <b>{runState.phase}</b>
                : t('status.ready')}
            </span>
          </footer>
          </div>
        </section>

        <button
          className="agent-dashboard-restore"
          type="button"
          aria-label={t('shell.expandDashboard')}
          onClick={() => setCollapsed('dashboard')}
        >
          <span>SB</span>
          <b>{t('shell.liveWorkspace')}</b>
        </button>

        <div
          className="agent-shell-divider"
          role="separator"
          aria-orientation="vertical"
          aria-valuemin="35"
          aria-valuemax="75"
          aria-valuenow={Math.round(shellLayout.dashboardWidth)}
          onPointerDown={startResize}
        >
          <span />
        </div>

        <section className="agent-chat-column" aria-label={t('shell.chatColumn')}>
          <header className="agent-chat-header">
            <div className="agent-chat-header-left">
              <span className="agent-chat-pi-orb" aria-hidden="true">π</span>
              <div>
                <h2>{t('shell.piBackend')}</h2>
                <span>{t('shell.piBackendDetail')}</span>
              </div>
              <span className="agent-chat-pi-badge" data-testid="pi-backend-badge">
                Pi · {credentialMode === 'local' ? 'Local' : 'Read only'}
              </span>
            </div>
            <div className="agent-chat-header-right">
              <button
                type="button"
                className="agent-pane-toggle"
                aria-label={t('shell.collapseAgent')}
                onClick={() => setCollapsed('agent')}
              >
                ›
              </button>
            </div>
          </header>

          <div className="agent-chat-body">
            {api && postJson ? (
              <Suspense fallback={<div className="flow-agent-loading">{t('configure.agentLoading')}</div>}>
                <AgentHarness
                  key={chatKey}
                  api={api}
                  postJson={postJson}
                  Status={FlowStatus}
                  shell
                  t={t}
                  queuedCommand={harnessTask}
                  onQueuedCommandSent={() => setHarnessTask(null)}
                  onRequestNewChat={() => setChatKey(key => key + 1)}
                />
              </Suspense>
            ) : (
              <div className="pi-chat-empty">
                <b>{t('agent.unavailable')}</b>
              </div>
            )}
          </div>
        </section>

        <button
          className="agent-chat-restore"
          type="button"
          aria-label={t('shell.expandAgent')}
          onClick={() => setCollapsed('agent')}
        >
          <span>π</span>
          <b>{t('shell.piBackend')}</b>
        </button>
      </div>
    </main>
  )
}
