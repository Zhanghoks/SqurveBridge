import { useCallback, useEffect, useState } from 'react'
import { detectLocale, setDocumentLocale, translate } from '../i18n/index.js'
import ConfigurationStudio from './ConfigurationStudio.jsx'
import ConnectionComposer from './ConnectionComposer.jsx'
import DemoHeader from './DemoHeader.jsx'
import DiagnosisWorkspace from './DiagnosisWorkspace.jsx'
import ImprovementWorkspace from './ImprovementWorkspace.jsx'
import { DATABASES, METHODS, resolveFocusedConfig } from './model.js'
import ProcessRail from './ProcessRail.jsx'
import ResultWorkspace from './ResultWorkspace.jsx'
import RunWorkspace, { INITIAL_RUN_STATE } from './RunWorkspace.jsx'
import { useEvidence } from './useEvidence.js'

const toggleItem = (items, value) =>
  items.includes(value)
    ? items.length === 1 ? items : items.filter(item => item !== value)
    : [...items, value]

export default function FullFlowDemo({
  capabilities,
  databases = [],
  sqlAuth,
  postJson,
  api,
  onConfigureSql,
}) {
  const configs = capabilities?.reproduce_configs || []
  const [locale, setLocale] = useState(() => detectLocale(
    navigator.language,
    window.localStorage.getItem('squrve-demo-locale'),
  ))
  const [selectedMethods, setSelectedMethods] = useState([METHODS[0]])
  const [selectedDatabases, setSelectedDatabases] = useState([DATABASES[0]])
  const [focusedMethod, setFocusedMethod] = useState(METHODS[0])
  const [focusedDatabase, setFocusedDatabase] = useState(DATABASES[0])
  const [sampleLimit, setSampleLimit] = useState(20)
  const [sampleMode, setSampleMode] = useState('slice')
  const [sampleSeed, setSampleSeed] = useState(42)
  const [runState, setRunState] = useState(INITIAL_RUN_STATE)
  const t = useCallback((key, params) => translate(locale, key, params), [locale])
  const evidence = useEvidence(api)

  useEffect(() => {
    window.localStorage.setItem('squrve-demo-locale', locale)
    setDocumentLocale(locale)
  }, [locale])

  const focusedConfig = resolveFocusedConfig(configs, focusedMethod, focusedDatabase)

  const toggleMethod = method => {
    const next = toggleItem(selectedMethods, method)
    setSelectedMethods(next)
    if (next.includes(method)) {
      setFocusedMethod(method)
    } else if (focusedMethod === method) {
      setFocusedMethod(next[0])
    }
  }

  const toggleDatabase = database => {
    const next = toggleItem(selectedDatabases, database)
    setSelectedDatabases(next)
    if (next.includes(database)) {
      setFocusedDatabase(database)
    } else if (focusedDatabase === database) {
      setFocusedDatabase(next[0])
    }
  }

  const selection = {
    selectedMethods,
    selectedDatabases,
    focusedMethod,
    focusedDatabase,
    onToggleMethod: toggleMethod,
    onToggleDatabase: toggleDatabase,
    onFocusConnection: (method, database) => {
      setFocusedMethod(method)
      setFocusedDatabase(database)
    },
  }
  const sampling = {
    sampleLimit,
    sampleMode,
    sampleSeed,
    onSampleLimitChange: setSampleLimit,
    onSampleModeChange: setSampleMode,
    onSampleSeedChange: setSampleSeed,
  }

  return <main className="flow-demo">
    <DemoHeader
      locale={locale}
      setLocale={setLocale}
      sqlAuth={sqlAuth}
      onConfigureSql={onConfigureSql}
      t={t}
      configCount={configs.length}
    />
    <ProcessRail t={t} />
    <ConfigurationStudio
      {...selection}
      {...sampling}
      focusedConfig={focusedConfig}
      sqlAuth={sqlAuth}
      onConfigureSql={onConfigureSql}
      t={t}
    />
    <ConnectionComposer
      {...selection}
      configs={configs}
      focusedConfig={focusedConfig}
      t={t}
    />
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
    />
    <ResultWorkspace runState={runState} t={t} />
    <DiagnosisWorkspace evidence={evidence} t={t} />
    <ImprovementWorkspace evidence={evidence} t={t} />
  </main>
}
