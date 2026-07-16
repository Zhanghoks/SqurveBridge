import { useMemo, useState } from 'react'
import {
  DATABASES,
  METHODS,
  buildConnections,
  buildReadyKeys,
  configKey,
  resolveFocusedConfig,
  workflowStages,
} from './full-flow/model.js'

export { DATABASES, METHODS, configKey }
export { buildReadyKeys as runnableConfigKeys } from './full-flow/model.js'

const METHOD_META = {
  C3SQL: 'schema linking · generation',
  DINSQL: 'decomposition · refinement',
  FinSQL: 'finance-aware generation',
  RESDSQL: 'ranking · skeleton parsing',
  'E-SQL': 'execution-guided correction',
  SEDE: 'schema evidence decomposition',
  UNISAR: 'unified schema reasoning',
  'GPT Baseline': 'direct generation baseline',
}

const DATABASE_META = {
  Spider: 'cross-domain · dev',
  BIRD: 'large-scale · evidence',
  BookSQL: 'financial records',
  'BULL-EN': 'business · English',
  'BULL-CN': 'business · Chinese',
  'EHRSQL-2024': 'electronic health records',
  AmbiDB: 'ambiguity benchmark',
  Spider2: 'enterprise workflows',
}

const GENERATORS = {
  C3SQL: 'C3SQLGenerator',
  DINSQL: 'DINSQLGenerator',
  FinSQL: 'FinSQLGenerator',
  RESDSQL: 'RESDSQLGenerator',
  'E-SQL': 'ESQLGenerator',
  SEDE: 'SEDEGenerator',
  UNISAR: 'UNISARGenerator',
  'GPT Baseline': 'GPTGenerator',
}

const CATALOG_KEYS = new Set(buildConnections(METHODS, DATABASES).map(item => item.key))

const pointY = index => 54 + index * 56

function MatrixGraph({ readyKeys, selectedMethods, selectedDatabases, focusedMethod, focusedDatabase, onMethod, onDatabase }) {
  const focusedKey = configKey(focusedMethod, focusedDatabase)
  return <div className="matrix-demo-graph">
    <div className="matrix-demo-column matrix-demo-methods">
      <div className="matrix-demo-column-title"><span>Text-to-SQL methods</span><b>{METHODS.length}</b></div>
      {METHODS.map(method => <button
        key={method}
        type="button"
        aria-label={`Select method ${method}`}
        aria-pressed={selectedMethods.includes(method)}
        className={selectedMethods.includes(method) ? 'active' : ''}
        onClick={() => onMethod(method)}
      >
        <span>{method}</span><small>{METHOD_META[method]}</small><i />
      </button>)}
    </div>
    <div className="matrix-demo-connections">
      <svg viewBox="0 0 1000 500" preserveAspectRatio="none" role="img" aria-labelledby="matrix-title matrix-description">
        <title id="matrix-title">Method to database configuration matrix</title>
        <desc id="matrix-description">Connections show which Text-to-SQL method and database pairs have an explicit reproduce configuration.</desc>
        {METHODS.flatMap((method, methodIndex) => DATABASES.map((database, databaseIndex) => {
          const key = configKey(method, database)
          const ready = readyKeys.has(key)
          const methodActive = selectedMethods.includes(method)
          const selected = methodActive && selectedDatabases.includes(database)
          const focused = focusedKey === key
          return <path
            key={key}
            className={`${ready ? 'ready' : 'unavailable'}${methodActive ? ' method-active' : ''}${selected ? ' selected' : ''}${focused ? ' focused' : ''}`}
            d={`M 0 ${pointY(methodIndex)} C 330 ${pointY(methodIndex)}, 670 ${pointY(databaseIndex)}, 1000 ${pointY(databaseIndex)}`}
          />
        }))}
      </svg>
      <div className="matrix-demo-legend">
        <span><i className="ready" />Runnable config</span>
        <span><i />Unavailable</span>
      </div>
    </div>
    <div className="matrix-demo-column matrix-demo-databases">
      <div className="matrix-demo-column-title"><span>Databases</span><b>{DATABASES.length}</b></div>
      {DATABASES.map(database => {
        const ready = selectedMethods.some(method => readyKeys.has(configKey(method, database)))
        return <button
          key={database}
          type="button"
          aria-label={`Select database ${database}`}
          aria-pressed={selectedDatabases.includes(database)}
          className={`${selectedDatabases.includes(database) ? 'active' : ''}${ready ? ' ready' : ''}`}
          onClick={() => onDatabase(database)}
        >
          <i /><span>{database}</span><small>{DATABASE_META[database]}</small>
        </button>
      })}
    </div>
  </div>
}

function ResultTable({ result }) {
  if (!result?.columns?.length) return null
  return <div className="matrix-demo-table"><table><thead><tr>{result.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{(result.rows || []).map((row, index) => <tr key={index}>{row.map((value, cell) => <td key={cell}>{value == null ? 'NULL' : String(value)}</td>)}</tr>)}</tbody></table></div>
}

export default function MatrixStudio({ capabilities, databases = [], sqlAuth, postJson, onConfigureSql }) {
  const configs = capabilities?.reproduce_configs || []
  const readyKeys = useMemo(() => new Set([...buildReadyKeys(configs)].filter(key => CATALOG_KEYS.has(key))), [configs])
  const [selectedMethods, setSelectedMethods] = useState([METHODS[0]])
  const [selectedDatabases, setSelectedDatabases] = useState([DATABASES[0]])
  const [focusedMethod, setFocusedMethod] = useState(METHODS[0])
  const [focusedDatabase, setFocusedDatabase] = useState(DATABASES[0])
  const [sampleLimit, setSampleLimit] = useState(20)
  const [sampleMode, setSampleMode] = useState('slice')
  const [question, setQuestion] = useState('')
  const [phase, setPhase] = useState('Ready')
  const [sql, setSql] = useState('')
  const [trace, setTrace] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const selectedConnections = useMemo(
    () => buildConnections(selectedMethods, selectedDatabases),
    [selectedMethods, selectedDatabases],
  )
  const selectedKey = configKey(focusedMethod, focusedDatabase)
  const selectedConfig = resolveFocusedConfig(configs, focusedMethod, focusedDatabase)
  const runnable = readyKeys.has(selectedKey)
  const runnableSelected = selectedConnections.filter(item => readyKeys.has(item.key))
  const registeredDatabase = databases.find(item => configKey('', item.id) === configKey('', focusedDatabase))
  const databaseId = registeredDatabase?.id || focusedDatabase
  const stageNames = workflowStages(selectedConfig).map(stage => stage.actor).filter(Boolean)

  const toggleMethod = method => {
    const removing = selectedMethods.includes(method)
    if (removing && selectedMethods.length === 1) return
    const next = removing ? selectedMethods.filter(item => item !== method) : [...selectedMethods, method]
    setSelectedMethods(next)
    setFocusedMethod(removing && focusedMethod === method ? next[0] : method)
  }

  const toggleDatabase = database => {
    const removing = selectedDatabases.includes(database)
    if (removing && selectedDatabases.length === 1) return
    const next = removing ? selectedDatabases.filter(item => item !== database) : [...selectedDatabases, database]
    setSelectedDatabases(next)
    setFocusedDatabase(removing && focusedDatabase === database ? next[0] : database)
  }

  const run = async () => {
    setBusy(true)
    setError('')
    setSql('')
    setTrace([])
    setResult(null)
    setPhase('Generating SQL')
    try {
      const generated = await postJson('/api/query', {
        question: question.trim(),
        db_id: databaseId,
        mode: stageNames.length ? 'workflow' : 'direct',
        actors: stageNames,
        generator: GENERATORS[focusedMethod],
        provider: sqlAuth?.provider,
        model: sqlAuth?.model,
      })
      setSql(generated.sql || '')
      setTrace(generated.trace || [])
      setPhase('Executing read-only SQL')
      const execution = await postJson('/api/execute', { db_id: databaseId, sql: generated.sql })
      setResult(execution)
      setPhase(`Completed · ${execution.row_count ?? 0} rows · ${execution.elapsed_ms ?? 0} ms`)
    } catch (err) {
      setError(err.message)
      setPhase('Run failed')
    } finally {
      setBusy(false)
    }
  }

  return <main className="matrix-demo">
    <header className="matrix-demo-header">
      <div className="matrix-demo-brand"><span>S</span><div><strong>SqurveBridge</strong><small>Reproducible Text-to-SQL workspace</small></div></div>
      <div className="matrix-demo-count"><strong>{readyKeys.size}</strong><span>of 64 runnable configurations</span></div>
      <div className="matrix-demo-session">
        <span className={sqlAuth?.configured ? 'connected' : ''}><i />{sqlAuth?.configured ? `${sqlAuth.provider} · ${sqlAuth.model}` : 'Model not connected'}</span>
        <button type="button" onClick={onConfigureSql}>Configure SQL API</button>
      </div>
    </header>

    <section className="matrix-demo-intro">
      <div><span>Evaluation workspace</span><h1>Connect a method to any integrated database.</h1><p>Every runnable edge maps to an explicit reproduce configuration. Choose a pair to inspect its workflow and run it with your model.</p></div>
      <div className="matrix-demo-health"><i /><span>Runtime ready</span><small>Database assets cache on demand</small></div>
    </section>

    <section className="matrix-demo-surface">
      <div className="matrix-demo-surface-head"><div><span>Method × Database</span><small>Select a method to trace its available configurations</small></div><b>{readyKeys.size} verified edges</b></div>
      <MatrixGraph
        readyKeys={readyKeys}
        selectedMethods={selectedMethods}
        selectedDatabases={selectedDatabases}
        focusedMethod={focusedMethod}
        focusedDatabase={focusedDatabase}
        onMethod={toggleMethod}
        onDatabase={toggleDatabase}
      />
    </section>

    <section className="matrix-demo-drawer">
      <div className="matrix-demo-pair" data-testid="selected-pair">
        <span>Focused connection</span>
        <div><strong>{focusedMethod}</strong><i>→</i><strong>{focusedDatabase}</strong></div>
        <small data-testid="configuration-status" className={runnable ? 'ready' : 'unavailable'}>{runnable ? `Runnable configuration · ${stageNames.length || 1} stages` : 'Configuration unavailable'}</small>
      </div>
      <div className="matrix-demo-selected-connections" data-testid="selected-connections">
        <span>{selectedConnections.length} connections · {runnableSelected.length} runnable</span>
        <div>{selectedConnections.map(item => <button
          type="button"
          key={item.key}
          aria-label={`Focus connection ${item.method} to ${item.database}`}
          className={`${readyKeys.has(item.key) ? 'ready' : 'unavailable'}${selectedKey === item.key ? ' active' : ''}`}
          onClick={() => { setFocusedMethod(item.method); setFocusedDatabase(item.database) }}
        ><b>{item.method}</b><i>→</i><b>{item.database}</b></button>)}</div>
      </div>
      <div className="matrix-demo-workflow">
        <span>Actor workflow</span>
        <div>{stageNames.length ? stageNames.map((stage, index) => <b key={`${stage}-${index}`}><i>{index + 1}</i>{stage}</b>) : <small>No verified workflow for this pair.</small>}</div>
      </div>
      <div className="matrix-demo-sampling">
        <span>Sample</span>
        <div>{[20, 50, 100].map(limit => <button type="button" key={limit} className={sampleLimit === limit ? 'active' : ''} onClick={() => setSampleLimit(limit)}>{limit}</button>)}</div>
        <div><button type="button" className={sampleMode === 'slice' ? 'active' : ''} onClick={() => setSampleMode('slice')}>Dev slice</button><button type="button" className={sampleMode === 'random' ? 'active' : ''} onClick={() => setSampleMode('random')}>Random</button></div>
      </div>
      <label className="matrix-demo-question"><span>Natural-language question</span><textarea aria-label="Natural-language question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a question about the selected database…" /></label>
      <div className="matrix-demo-run">
        <span className={`matrix-demo-run-status ${error ? 'error' : result ? 'success' : ''}`}><i />{phase}</span>
        {!sqlAuth?.configured && <button type="button" className="secondary" onClick={onConfigureSql}>Connect model first</button>}
        <button type="button" className="primary" disabled={busy || !runnable || !question.trim() || !sqlAuth?.configured} onClick={run}>{busy ? 'Running…' : 'Run reproduce'}</button>
      </div>
      {error && <p className="matrix-demo-error">{error}</p>}
    </section>

    {(sql || result) && <section className="matrix-demo-results">
      <div><span>Generated SQL</span><code>{sql}</code></div>
      <div><span>Execution trace</span><p>{trace.map(item => item.actor_name || item.actor || item.stage).filter(Boolean).join(' → ') || stageNames.join(' → ') || 'Direct generation'}</p></div>
      <ResultTable result={result} />
    </section>}
  </main>
}
