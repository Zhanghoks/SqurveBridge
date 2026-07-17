import { useCallback, useEffect, useState } from 'react'
import { detectLocale, setDocumentLocale, translate } from '../i18n/index.js'
import ConfigurationStudio from './ConfigurationStudio.jsx'
import ConnectionComposer from './ConnectionComposer.jsx'
import DemoHeader from './DemoHeader.jsx'
import DiagnosisWorkspace from './DiagnosisWorkspace.jsx'
import ImprovementWorkspace from './ImprovementWorkspace.jsx'
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
import ProcessRail, { PROCESS_STEPS, resolveProcessStep } from './ProcessRail.jsx'
import ResultWorkspace from './ResultWorkspace.jsx'
import RunWorkspace, { INITIAL_RUN_STATE } from './RunWorkspace.jsx'
import { useEvidence } from './useEvidence.js'
import './full-flow.css'

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
  const t = useCallback((key, params) => translate(locale, key, params), [locale])
  const focusedConfig = resolveFocusedConfig(configs, focusedMethod, focusedDatabase)
  const selectedMethods = selectedMethodsFromConnections(selectedConnections)
  const selectedDatabases = selectedDatabasesFromConnections(selectedConnections)
  const connections = withConnectionKeys(selectedConnections)
  const evidence = useEvidence(api, {
    method: focusedConfig?.method,
    dataset: focusedConfig?.dataset,
    split: focusedConfig?.split,
    sampleMode,
    sampleLimit,
    sampleSeed,
  })
  const activeIndex = PROCESS_STEPS.indexOf(activeStep)

  useEffect(() => {
    window.localStorage.setItem('squrve-demo-locale', locale)
    setDocumentLocale(locale)
  }, [locale])

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
        {...selection}
        {...sampling}
        focusedConfig={focusedConfig}
        configs={configs}
        databases={databases}
        sqlAuth={sqlAuth}
        api={api}
        postJson={postJson}
        hostedReadOnly={credentialMode !== 'local'}
        onConfigureSql={onConfigureSql}
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
    run: (
      <RunWorkspace
        focusedConfig={focusedConfig}
        focusedMethod={focusedMethod}
        focusedDatabase={focusedDatabase}
        databases={databases}
        sampleLimit={sampleLimit}
        sampleMode={sampleMode}
        sampleSeed={sampleSeed}
        sqlAuth={sqlAuth}
        postJson={postJson}
        onConfigureSql={onConfigureSql}
        onRunStateChange={setRunState}
        t={t}
        credentialMode={credentialMode}
      />
    ),
    inspect: <ResultWorkspace runState={runState} t={t} />,
    diagnose: <DiagnosisWorkspace evidence={evidence} t={t} />,
    improve: <ImprovementWorkspace evidence={evidence} t={t} />,
  }

  return <main className="flow-demo">
    <div className="matrix-live-notice">
      {t(credentialMode === 'local' ? 'local.notice' : 'hosted.notice')}
    </div>
    <DemoHeader
      locale={locale}
      setLocale={setLocale}
      sqlAuth={sqlAuth}
      onConfigureSql={onConfigureSql}
      t={t}
      configCount={configs.length}
      credentialMode={credentialMode}
    />
    <div className="flow-demo-body">
      <ProcessRail
        activeStep={activeStep}
        onNavigate={navigateToStep}
        t={t}
      />
      <div className="flow-stage" data-testid="flow-stage" data-active-step={activeStep}>
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
        <footer className="flow-stage-nav">
          <button
            type="button"
            disabled={activeIndex <= 0}
            onClick={() => navigateToStep(PROCESS_STEPS[activeIndex - 1])}
          >
            {t('process.previous')}
          </button>
          <span>
            {t('process.pageIndex', {
              current: activeIndex + 1,
              total: PROCESS_STEPS.length,
            })}
          </span>
          <button
            type="button"
            disabled={activeIndex >= PROCESS_STEPS.length - 1}
            onClick={() => navigateToStep(PROCESS_STEPS[activeIndex + 1])}
          >
            {t('process.next')}
          </button>
        </footer>
      </div>
    </div>
  </main>
}
