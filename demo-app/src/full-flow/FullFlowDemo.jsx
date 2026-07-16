import { useCallback, useEffect, useState } from 'react'
import { detectLocale, setDocumentLocale, translate } from '../i18n/index.js'
import ConfigurationStudio from './ConfigurationStudio.jsx'
import ConnectionComposer from './ConnectionComposer.jsx'
import DemoHeader from './DemoHeader.jsx'
import { DATABASES, METHODS, resolveFocusedConfig } from './model.js'
import ProcessRail from './ProcessRail.jsx'

const toggleItem = (items, value) =>
  items.includes(value)
    ? items.length === 1 ? items : items.filter(item => item !== value)
    : [...items, value]

function PlaceholderModule({ id, titleKey, emptyKey, t }) {
  return <section id={id} className="flow-module flow-placeholder">
    <h2>{t(titleKey)}</h2>
    <p>{t(emptyKey)}</p>
  </section>
}

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
  const t = useCallback((key, params) => translate(locale, key, params), [locale])

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

  void databases
  void postJson
  void api

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
    <PlaceholderModule id="run" titleKey="run.title" emptyKey="run.stagingEmpty" t={t} />
    <PlaceholderModule id="inspect" titleKey="inspect.title" emptyKey="inspect.empty" t={t} />
    <PlaceholderModule id="diagnose" titleKey="diagnose.title" emptyKey="diagnose.persistedEmpty" t={t} />
    <PlaceholderModule id="improve" titleKey="improve.title" emptyKey="improve.persistedEmpty" t={t} />
  </main>
}
