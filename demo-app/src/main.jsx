import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import ExperimentBoard from './ExperimentBoard.jsx'
import Archive from './Archive.jsx'
import { deploymentTarget, featureEnabled, studioSurface } from './runtimeMode.js'

const AgentHarness = lazy(() => import('./AgentHarness.jsx'))

const api = async (path, options = {}) => {
  const response = await fetch(path, options)
  const data = await response.json().catch(() => ({ message: response.statusText }))
  if (!response.ok) throw new Error(data.message || 'Request failed')
  return data
}

const postJson = (path, body) => api(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const percent = value => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
const jobTone = status => status === 'completed' ? 'success' : status === 'failed' ? 'danger' : status === 'cancelled' ? 'neutral' : 'running'

function Status({ tone = 'neutral', children }) {
  return <span className={`status status-${tone}`}><i />{children}</span>
}

function Empty({ title, detail, action }) {
  return <div className="empty"><strong>{title}</strong>{detail && <span>{detail}</span>}{action}</div>
}

function ShellNav({ page, setPage }) {
  const items = [
    ['studio', '01', 'SQL Studio'],
    ['board', '02', 'Experiment Board'],
    ['archive', '03', 'Archive'],
  ]
  return <aside className="sidebar">
    <div className="brand">
      <span>S</span><div>SqurveBridge</div>
    </div>
    <nav aria-label="Platform modules">
      {items.map(([id, index, label]) => (
        <button key={id} className={page === id ? 'active' : ''} aria-current={page === id ? 'page' : undefined} onClick={() => setPage(id)}>
          <i>{index}</i><span>{label}</span>
        </button>
      ))}
    </nav>
    <div className="module-chain"><i className="chain-integration" /><span>Candidate Reader</span><i className="chain-evaluation" /><span>Integration Pipeline</span><i className="chain-adapt" /><span>Reproduce Run</span></div>
  </aside>
}

function Topbar({ health, capabilities, refresh, busy, hosted = false, showProviderConfig = true }) {
  const provider = health?.provider
  const tone = !health ? 'neutral' : provider?.message && !provider?.ready ? 'danger' : provider?.verified ? 'success' : 'warning'
  const label = !health ? 'Connecting' : provider?.verified ? `${provider.provider} credential verified` : provider?.configured ? `${provider.provider} · ${provider.model || 'model'}` : 'Provider setup required'
  return <header className="topbar"><div><strong>Squrve-native runtime</strong><span>{hosted ? 'Hugging Face Space' : 'Local demo session'}</span></div><div className="runtime-state"><Status tone={tone}>{label}</Status>{showProviderConfig && <ProviderConfig health={health} capabilities={capabilities} refresh={refresh} />}<button className="icon-button" onClick={refresh} disabled={busy} title="Refresh runtime" aria-label="Refresh runtime">↻</button></div></header>
}

function ProviderConfig({ health, capabilities, refresh }) {
  const providers = capabilities?.llm_providers || []
  const [open, setOpen] = useState(false)
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [persist, setPersist] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const panelRef = useRef(null)
  const selected = providers.find(item => item.id === provider)

  useEffect(() => {
    const current = health?.provider?.provider
    const next = providers.find(item => item.id === current)?.id || providers.find(item => item.configured)?.id || providers[0]?.id || ''
    if (next) setProvider(next)
  }, [health?.provider?.provider, providers.map(item => item.id).join('|')])

  useEffect(() => {
    if (!selected) return
    const preferred = health?.provider?.provider === selected.id ? health?.provider?.model : null
    setModel(selected.models.includes(preferred) ? preferred : selected.default_model)
  }, [provider, selected?.models?.join('|'), health?.provider?.model])

  useEffect(() => {
    if (!open) return
    const onPointer = event => {
      if (!panelRef.current?.contains(event.target)) setOpen(false)
    }
    const onKey = event => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const save = async () => {
    setBusy(true); setError(''); setMessage('')
    try {
      const payload = { provider, model, persist }
      if (apiKey.trim()) payload.api_key = apiKey.trim()
      const data = await postJson('/api/provider', payload)
      setApiKey('')
      setMessage(data.provider?.configured ? `Saved ${data.provider.provider}/${data.provider.model}` : 'Saved')
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <div className="provider-config" ref={panelRef}>
    <button className="button compact secondary" type="button" aria-expanded={open} onClick={() => setOpen(current => !current)}>Configure LLM</button>
    {open && <div className="provider-config-panel" role="dialog" aria-label="LLM provider configuration">
      <div className="panel-title"><div><span>LLM credentials</span><small>Keys stay on localhost · never returned by API</small></div></div>
      <label className="field"><span>Provider</span><select value={provider} onChange={event => setProvider(event.target.value)}>{providers.map(item => <option key={item.id} value={item.id}>{item.id}{item.configured ? ' · configured' : ' · needs key'}</option>)}</select></label>
      <label className="field"><span>Model</span><select value={model} onChange={event => setModel(event.target.value)}>{(selected?.models || []).map(item => <option key={item} value={item}>{item}</option>)}</select></label>
      <label className="field"><span>API key{selected?.env_var ? ` · ${selected.env_var}` : ''}</span><input type="password" autoComplete="off" spellCheck="false" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={selected?.configured ? 'Leave blank to keep current key' : 'Paste API key'} /></label>
      <label className="persist-toggle"><input type="checkbox" checked={persist} onChange={event => setPersist(event.target.checked)} /><span>Write to repo-root .env</span></label>
      <div className="provider-config-actions"><button className="button primary compact" disabled={busy || !provider || !model} onClick={save}>{busy ? 'Saving…' : 'Save'}</button><button className="button compact" type="button" onClick={() => setOpen(false)}>Close</button></div>
      {message && <p className="provider-config-note">{message}</p>}
      {error && <p className="error-banner">{error}</p>}
    </div>}
  </div>
}

function PageHeading({ eyebrow, title, status }) {
  return <div className="page-heading"><div><span>{eyebrow}</span><h1>{title}</h1></div>{status}</div>
}

function DatabaseSelector({ databases, value, onChange }) {
  const current = databases.find(item => item.id === value)
  return <div className="database-selector"><label className="field"><span>Database</span><select value={value} onChange={event => onChange(event.target.value)}><option value="">Select database</option>{databases.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label>{current && <div className="inline-facts"><span>{current.tables.length} tables</span><span>{Math.max(1, Math.round(current.size_bytes / 1024))} KB</span></div>}</div>
}

function ActorComposer({ capabilities, workflowIndex, setWorkflowIndex, actorSelections, setActorSelections }) {
  const actors = capabilities?.actors || {}
  const workflows = capabilities?.workflows || []
  const workflow = workflows[workflowIndex] || []
  return <div className="pipeline-config"><label className="field"><span>Workflow skeleton</span><select value={workflowIndex} onChange={event => setWorkflowIndex(Number(event.target.value))}>{workflows.map((item, index) => <option value={index} key={item.join('-')}>{item.join(' → ')}</option>)}</select></label><div className="actor-flow">{workflow.map((type, index) => <div key={`${type}-${index}`}><i>{index + 1}</i><label className="field"><span>{type}</span><select value={actorSelections[type] || ''} onChange={event => setActorSelections(current => ({ ...current, [type]: event.target.value }))}>{(actors[type] || []).map(item => <option key={item}>{item}</option>)}</select></label></div>)}</div></div>
}

function ResultTable({ result }) {
  if (!result) return <Empty title="No execution result" detail="Run the assembled config to execute generated SQL." />
  return <div className="table-wrap"><table><thead><tr>{result.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>{row.map((value, cell) => <td key={cell}>{value == null ? <em>NULL</em> : String(value)}</td>)}</tr>)}</tbody></table></div>
}

function Studio({ health, capabilities, databases, selectedDb, setSelectedDb, showAgentHarness = true }) {
  const [workflowIndex, setWorkflowIndex] = useState(1)
  const [actorSelections, setActorSelections] = useState({})
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [question, setQuestion] = useState('')
  const [sql, setSql] = useState('')
  const [trace, setTrace] = useState([])
  const [result, setResult] = useState(null)
  const [phase, setPhase] = useState('Ready')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const currentDb = databases.find(item => item.id === selectedDb)
  const workflow = capabilities?.workflows?.[workflowIndex] || []
  const providers = capabilities?.llm_providers || []
  const providerConfig = providers.find(item => item.id === provider)
  const selectedActors = workflow.map(type => actorSelections[type]).filter(Boolean)

  useEffect(() => {
    const actorTypes = capabilities?.actors || {}
    const defaults = Object.fromEntries(Object.entries(actorTypes).map(([type, items]) => [type, items[0] || '']))
    setActorSelections(current => ({ ...defaults, ...current }))
  }, [capabilities])

  useEffect(() => {
    if (!providers.some(item => item.id === provider)) {
      setProvider(providers.find(item => item.id === health?.provider?.provider)?.id || providers.find(item => item.configured)?.id || providers[0]?.id || '')
    }
  }, [providers.map(item => item.id).join('|'), provider, health?.provider?.provider])
  useEffect(() => {
    if (providerConfig && !providerConfig.models.includes(model)) setModel(providerConfig.default_model)
  }, [provider, providerConfig?.models?.join('|'), model])

  const configPreview = useMemo(() => ({
    database: selectedDb || null,
    llm: { provider: provider || null, model: model || null },
    workflow: workflow.map((type, index) => ({ order: index + 1, type, actor: actorSelections[type] || null })),
  }), [selectedDb, provider, model, workflow.join('|'), selectedActors.join('|')])

  const runConfig = async () => {
    setBusy(true); setError(''); setResult(null); setSql(''); setTrace([]); setPhase('Running config')
    try {
      const data = await postJson('/api/query', { question, db_id: selectedDb, mode: 'workflow', actors: selectedActors, provider, model })
      setSql(data.sql || ''); setTrace(data.trace || [])
      const execution = await postJson('/api/execute', { db_id: selectedDb, sql: data.sql })
      setResult(execution); setPhase(`Completed · ${execution.row_count} rows · ${execution.elapsed_ms} ms`)
    } catch (err) { setError(err.message); setPhase('Run failed') }
    finally { setBusy(false) }
  }

  return <div className="workspace studio-workspace"><PageHeading eyebrow="Squrve run configuration" title="SQL Studio" status={<Status tone={error ? 'danger' : result ? 'success' : busy ? 'running' : 'neutral'}>{phase}</Status>} />
    <div className="config-builder-grid"><section className="tool-panel config-block"><div className="config-step"><i>01</i><div><span>Database</span><small>Execution target</small></div></div><DatabaseSelector databases={databases} value={selectedDb} onChange={setSelectedDb} />{currentDb ? <ul className="schema-chips">{currentDb.tables.slice(0, 8).map(table => <li key={table}>{table}</li>)}</ul> : <Empty title="Select an integrated database" />}</section>
      <section className="tool-panel config-block"><div className="config-step"><i>02</i><div><span>LLM Provider</span><small>Credential stays in local .env</small></div></div><label className="field"><span>Provider</span><select value={provider} onChange={event => setProvider(event.target.value)}>{providers.map(item => <option key={item.id} value={item.id}>{item.id}{item.configured ? ' · configured' : ' · setup required'}</option>)}</select></label><label className="field"><span>Model</span><select value={model} onChange={event => setModel(event.target.value)}>{(providerConfig?.models || []).map(item => <option key={item}>{item}</option>)}</select></label><Status tone={providerConfig?.configured ? 'success' : 'danger'}>{providerConfig?.configured ? 'credential available' : 'credential required'}</Status></section>
      <section className="tool-panel config-block actor-config-block"><div className="config-step"><i>03</i><div><span>Actor Workflow</span><small>{workflow.join(' → ')}</small></div></div><ActorComposer {...{ capabilities, workflowIndex, setWorkflowIndex, actorSelections, setActorSelections }} /></section></div>
    <div className="run-config-grid"><section className="tool-panel config-preview"><div className="config-step"><i>04</i><div><span>Run Config</span><small>Database + LLM + Actor pipeline</small></div></div><pre>{JSON.stringify(configPreview, null, 2)}</pre></section><section className="tool-panel run-input"><label className="field"><span>Natural-language input</span><textarea value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a question for this configured workflow." /></label><button className="button primary" disabled={busy || !selectedDb || !question.trim() || !providerConfig?.configured || selectedActors.length !== workflow.length} onClick={runConfig}>{busy ? 'Running Squrve config…' : 'Run config'}</button>{error && <p className="error-banner">{error}</p>}</section></div>
    {(sql || result) && <section className="tool-panel studio-result"><div className="result-summary"><div><span>Generated SQL</span><code>{sql}</code></div><div><span>Actor path</span><b>{trace.map(item => item.actor_name).join(' → ') || selectedActors.join(' → ')}</b></div></div><div className="result-meta"><span>Read-only database execution</span>{result && <b>{result.row_count} rows · {result.elapsed_ms} ms</b>}</div><ResultTable result={result} /></section>}
    {showAgentHarness && <Suspense fallback={<section className="tool-panel agent-harness-loading"><Empty title="Loading Pi Agent chat" /></section>}><AgentHarness {...{ api, postJson, Status }} /></Suspense>}
  </div>
}

const HARNESS_SKILLS = [
  ['01', '/candidate-reader', '读取 GitHub 候选仓库，识别算法、数据和依赖，生成 integration manifest。'],
  ['02', '/integration-pipeline', '按 manifest 调度 adapters，把候选方法重构为 Squrve-native Actor workflow。'],
  ['03', '/config-adapter', '汇聚 Actor、数据和评估合同，生成可复现 reproduce config。'],
  ['04', '/run', '调试 config 直到整条 pipeline 跑通，并生成当前 session 的 score bundle。'],
  ['05', '/meta-evo', '可选：依据新评估结果诊断弱点，在人工 review gate 前搜索改进。'],
]

function WorkspaceStudio({ capabilities, databases, showAgentHarness = true, liveEvaluation = true }) {
  const capabilityConfigs = capabilities?.reproduce_configs || []
  const [configs, setConfigs] = useState([])
  const [candidateUrl, setCandidateUrl] = useState('')
  const [candidateError, setCandidateError] = useState('')
  const [candidatePhase, setCandidatePhase] = useState('idle')
  const candidateInputRef = useRef(null)
  const [selected, setSelected] = useState([])
  const [configRequests, setConfigRequests] = useState([])
  const [harnessTask, setHarnessTask] = useState(null)
  const [jobs, setJobs] = useState([])
  const [comparisonId, setComparisonId] = useState('')
  const [selectedJob, setSelectedJob] = useState('')
  const [log, setLog] = useState('')
  const [error, setError] = useState('')
  const [sampleLimit, setSampleLimit] = useState(100)
  const [sampleMode, setSampleMode] = useState('random')
  const [sampleSeed, setSampleSeed] = useState(42)
  const keyOf = item => `${item.dataset}/${item.method}`
  const methods = useMemo(() => [...new Set(configs.map(item => item.method))].sort().map(method => {
    const records = configs.filter(item => item.method === method)
    return { method, datasets: records.map(item => item.dataset), stages: Math.max(...records.map(item => item.stages.length), 0) }
  }), [configs])
  const benchmarks = useMemo(() => {
    const registered = capabilities?.benchmarks || []
    if (registered.length) return [...registered].sort((a, b) => a.id.localeCompare(b.id)).map(item => ({ dataset: item.id, splits: item.splits, defaultSplit: item.default_split }))
    return [...new Set(configs.map(item => item.dataset))].sort().map(dataset => ({ dataset, splits: [...new Set(configs.filter(item => item.dataset === dataset).map(item => item.split))], defaultSplit: configs.find(item => item.dataset === dataset)?.split || '' }))
  }, [capabilities, configs])
  const githubReady = /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+\/?$/.test(candidateUrl.trim().replace(/\.git\/?$/, ''))
  const normalizedCandidateUrl = candidateUrl.trim().replace(/\.git\/?$/, '').replace(/\/$/, '')
  const comparisonJobs = jobs.filter(job => job.comparison_id === comparisonId)
  const running = comparisonJobs.some(job => job.status === 'running')
  const missingSelected = showAgentHarness ? selected.filter(key => !configs.some(item => keyOf(item) === key)) : []

  useEffect(() => { setConfigs(capabilityConfigs) }, [capabilities])

  const configCommand = ({ method, dataset, split }) => `/config-adapter method=${method} target_dataset=${dataset}${split ? ` target_split=${split}` : ''}. The method and dataset are already integrated in Squrve. Reuse their existing Actor workflow, benchmark registration, adapter artifacts, and reproduce configs. Create the reproduce spec draft and stop at SPEC_REVIEW. After user approval, generate reproduce/configs/${dataset}/${method}.json with stage eval, dataset_save_path, workflow trace fields, and no secrets; validate the reproduce contract and then explain how to run /run ${dataset} ${method}.`

  const queueConfigGeneration = showAgentHarness ? pair => {
    const request = { ...pair, split: pair.split || benchmarks.find(item => item.dataset === pair.dataset)?.defaultSplit || '' }
    const key = keyOf(request)
    const id = `${key}-${Date.now()}`
    setConfigRequests(current => [...current.filter(item => item.key !== key), { ...request, key, id, status: 'queued' }])
    setHarnessTask({ id, command: configCommand(request) })
  } : null

  const startCandidateReader = () => {
    if (!githubReady) {
      setCandidateError('Enter a valid public GitHub repository URL first.')
      candidateInputRef.current?.focus()
      return
    }
    const id = `candidate-${Date.now()}`
    setCandidatePhase('starting')
    setHarnessTask({ id, command: `/candidate-reader ${normalizedCandidateUrl}` })
  }

  const refreshConfigs = async () => {
    const data = await api('/api/capabilities')
    setConfigs(data.reproduce_configs || [])
  }

  useEffect(() => {
    if (!configRequests.some(request => !configs.some(item => keyOf(item) === request.key))) return
    const timer = setInterval(() => refreshConfigs().catch(err => setError(err.message)), 3000)
    return () => clearInterval(timer)
  }, [configRequests.map(item => item.key).join('|'), configs.map(keyOf).join('|')])

  const refreshSession = async () => {
    const data = await api('/api/session')
    setJobs(data.jobs || [])
  }

  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const data = await api('/api/session')
        if (active) {
          setJobs(data.jobs || [])
          setError('')
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }
    refresh()
    const timer = setInterval(refresh, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!comparisonId) {
      const latest = jobs.find(job => job.comparison_id)?.comparison_id
      if (latest) setComparisonId(latest)
    }
  }, [jobs, comparisonId])

  useEffect(() => {
    if (comparisonJobs.length && !comparisonJobs.some(job => job.job_id === selectedJob)) {
      setSelectedJob(comparisonJobs[0].job_id)
    }
  }, [comparisonJobs.map(job => job.job_id).join('|'), selectedJob])

  useEffect(() => {
    if (!selectedJob) { setLog(''); return }
    let active = true
    const load = async () => {
      try {
        const detail = await api(`/api/evaluations/${selectedJob}`)
        if (active) {
          setLog(detail.log || '')
          setError('')
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }
    load()
    const timer = setInterval(load, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [selectedJob])

  const start = async () => {
    setError('')
    try {
      const pairs = configs.filter(item => selected.includes(keyOf(item))).map(({ dataset, method }) => ({ dataset, method }))
      const data = await postJson('/api/comparisons', { pairs, sample_limit: sampleLimit, sample_mode: sampleMode, sample_seed: sampleSeed })
      setComparisonId(data.comparison_id)
      setSelectedJob(data.jobs[0]?.job_id || '')
      await refreshSession()
    } catch (err) { setError(err.message) }
  }

  const cancel = async jobId => {
    try {
      await postJson(`/api/evaluations/${jobId}/cancel`, {})
      await refreshSession()
    } catch (err) { setError(err.message) }
  }

  return <div className="workspace registry-workspace"><PageHeading eyebrow="Squrve evaluation workspace" title="SQL Studio" status={<Status tone={running ? 'running' : comparisonJobs.length ? 'success' : 'neutral'}>{running ? 'evaluation running' : `${methods.length} methods · ${benchmarks.length} datasets`}</Status>} />
    <section className="tool-panel experiment-builder relation-studio"><div className="panel-title"><div><span>Method × dataset evaluation graph</span><small>Select any method, then connect any integrated dataset</small></div><Status tone={missingSelected.length ? 'warning' : selected.length >= 2 ? 'success' : 'neutral'}>{selected.length} connected</Status></div><EvaluationGraph configs={configs} methods={methods.map(item => item.method)} datasets={benchmarks.map(item => item.dataset)} selected={selected} setSelected={setSelected} onMissingConfig={queueConfigGeneration} />{missingSelected.length > 0 && <div className="config-generation-panel"><div><span>Config generation queue</span><small>The selected agent uses config-adapter and pauses at SPEC_REVIEW before delivery.</small></div><div className="config-generation-list">{missingSelected.map(key => { const request = configRequests.find(item => item.key === key); const [dataset, method] = key.split('/'); return <div key={key}><span><b>{method}</b><i>→</i><b>{dataset}</b></span><Status tone={request?.status === 'sent' ? 'running' : 'warning'}>{request?.status === 'sent' ? 'awaiting review' : 'queued'}</Status><button className="button compact" onClick={() => queueConfigGeneration({ method, dataset })}>Send again</button></div> })}</div><ol><li>Review the reproduce spec in the Agent Harness below.</li><li>Approve SPEC_REVIEW in the same agent conversation.</li><li>Run the suggested command; this edge becomes runnable when the config appears.</li></ol><button className="button secondary compact" onClick={() => refreshConfigs().catch(err => setError(err.message))}>Refresh configs</button></div>}{liveEvaluation ? <div className="evaluation-command"><div className="sampling-controls"><div className="scope-control"><span>Sample size</span><div>{[[20, '20'], [50, '50'], [100, '100'], [200, '200']].map(([value, label]) => <button key={label} className={sampleLimit === value ? 'active' : ''} onClick={() => setSampleLimit(value)}>{label}</button>)}</div></div><div className="sample-mode"><span>Sampling</span><div className="segmented"><button className={sampleMode === 'slice' ? 'active' : ''} onClick={() => setSampleMode('slice')}>Dev slice</button><button className={sampleMode === 'random' ? 'active' : ''} onClick={() => setSampleMode('random')}>Random</button></div>{sampleMode === 'random' && <label><span>Seed</span><input type="number" value={sampleSeed} onChange={event => setSampleSeed(Number(event.target.value))} /></label>}</div></div><button className="button primary" disabled={selected.length < 2 || missingSelected.length > 0 || running} onClick={start}>{running ? 'Evaluation in progress' : missingSelected.length ? `Generate ${missingSelected.length} missing config${missingSelected.length > 1 ? 's' : ''} before running` : `Run ${selected.length} connected evaluations · ${sampleMode === 'slice' ? 'dev slice' : 'random'} ${sampleLimit}${sampleMode === 'random' ? ` · seed ${sampleSeed}` : ''}`}</button></div> : <div className="hosted-readonly-note">Live evaluation launch is available from a local SqurveBridge checkout.</div>}{error && <p className="error-banner">{error}</p>}</section>
    <div className="run-monitor-layout"><section className="tool-panel live-runs"><div className="panel-title"><div><span>Live run control</span><small>{comparisonId || 'Current browser session'}</small></div></div>{comparisonJobs.length ? comparisonJobs.map(job => <button key={job.job_id} className={selectedJob === job.job_id ? 'active' : ''} onClick={() => setSelectedJob(job.job_id)}><span><b>{job.method}</b><small>{job.dataset} · {job.config?.scope}</small></span><Status tone={jobTone(job.status)}>{job.status}</Status>{liveEvaluation && job.status === 'running' && <i role="button" aria-label={`Cancel ${job.method} on ${job.dataset}`} onClick={event => { event.stopPropagation(); cancel(job.job_id) }}>×</i>}</button>) : <Empty title="No evaluations started" detail="Connect at least two method-dataset pairs to compare them." />}</section><section className="tool-panel evaluation-log"><div className="panel-title"><div><span>Selected run log</span><small>{selectedJob || 'No run selected'}</small></div></div><pre>{log || 'Run logs will appear here during evaluation.'}</pre></section></div>
    {showAgentHarness && <>
      <div className="harness-section-head"><div><span>Agent Harness</span><small>GitHub candidate → native integration → reproducible run</small></div><Status tone={candidatePhase === 'running' ? 'running' : githubReady ? 'success' : 'neutral'}>{candidatePhase === 'running' ? 'candidate reader running' : candidatePhase === 'starting' ? 'starting agent' : githubReady ? 'repository ready' : 'GitHub URL required'}</Status></div>
      <section className="tool-panel github-intake"><label className="field"><span>Candidate GitHub repository</span><input ref={candidateInputRef} type="url" value={candidateUrl} onChange={event => { setCandidateUrl(event.target.value); setCandidateError(''); setCandidatePhase('idle') }} aria-invalid={Boolean(candidateError)} placeholder="https://github.com/owner/repository" />{candidateError && <small className="field-error">{candidateError}</small>}</label><div><code>{githubReady ? `/candidate-reader ${normalizedCandidateUrl}` : '/candidate-reader <github-repository-url>'}</code></div><button className="button primary" disabled={!githubReady || candidatePhase === 'starting'} onClick={startCandidateReader}>{candidatePhase === 'starting' ? 'Starting…' : 'Start candidate reader'}</button></section>
      <div className="skill-route">{HARNESS_SKILLS.map(([index, skill, purpose]) => <div key={skill}><i>{index}</i><span><b>{skill}</b><small>{purpose}</small></span></div>)}</div>
      <Suspense fallback={<section className="tool-panel agent-harness-loading"><Empty title="Loading Pi Agent chat" /></section>}><AgentHarness candidateUrl={githubReady ? normalizedCandidateUrl : ''} onCandidateReaderStart={startCandidateReader} onCandidateUrlRequired={() => { setCandidateError('Enter a valid public GitHub repository URL first.'); candidateInputRef.current?.focus(); candidateInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }} queuedCommand={harnessTask} onQueuedCommandSent={id => { if (id.startsWith('candidate-')) setCandidatePhase('running'); setConfigRequests(current => current.map(item => item.id === id ? { ...item, status: 'sent' } : item)) }} {...{ api, postJson, Status }} /></Suspense>
    </>}
  </div>
}

function DatabaseManager({ databases, selectedDb, setSelectedDb, refreshDatabases, showDatabaseUpload = true }) {
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const upload = async () => {
    if (!files.length) return
    setUploading(true); setError('')
    try { const body = new FormData(); Array.from(files).forEach(file => body.append('files', file)); const data = await api('/api/databases/upload', { method: 'POST', body }); await refreshDatabases(data.database?.id); setFiles([]) } catch (err) { setError(err.message) } finally { setUploading(false) }
  }
  return <div className="adapter-grid"><section className="tool-panel import-panel"><div className="panel-title"><div><span>Database & Benchmark Adapter</span><small>SQLite · CSV · XLSX</small></div></div>{showDatabaseUpload && <><label className="file-drop"><input type="file" multiple accept=".sqlite,.db,.csv,.xlsx,.xls" onChange={event => setFiles(event.target.files)} /><strong>{files.length ? `${files.length} file${files.length > 1 ? 's' : ''} selected` : 'Choose database files'}</strong><span>Schema is normalized to the Squrve data contract.</span></label><button className="button primary" disabled={!files.length || uploading} onClick={upload}>{uploading ? 'Normalizing schema…' : 'Integrate database'}</button>{error && <p className="error-banner">{error}</p>}</>}</section><section className="registry-list"><div className="registry-head"><span>Registered databases</span><b>{databases.length}</b></div>{databases.map(item => <button key={item.id} className={selectedDb === item.id ? 'active' : ''} onClick={() => setSelectedDb(item.id)}><div><b>{item.id}</b><span>{item.tables.join(' · ') || 'No tables'}</span></div><small>{item.tables.length} tables</small></button>)}</section></div>
}

function MethodRegistry({ capabilities }) {
  const configs = capabilities?.reproduce_configs || []
  const methods = [...new Set(configs.map(item => item.method))].sort()
  const [method, setMethod] = useState('')
  useEffect(() => { if (!methods.includes(method)) setMethod(methods[0] || '') }, [methods.join('|'), method])
  const selected = configs.filter(item => item.method === method)
  return <div className="registry-grid"><section className="method-list">{methods.map(item => <button key={item} className={item === method ? 'active' : ''} onClick={() => setMethod(item)}><span>{item}</span><small>{configs.filter(config => config.method === item).length} registered pair(s)</small></button>)}</section><section className="tool-panel method-detail"><div className="panel-title"><div><span>{method || 'Method Adapter'}</span><small>Squrve-native reproduce configurations</small></div><Status tone="success">registered</Status></div>{selected.map(config => <div className="config-row" key={`${config.dataset}/${config.method}`}><div className="config-identity"><b>{config.dataset}</b><span>{config.split} · {config.scope} · {config.provider}/{config.model}</span></div><div className="pipeline-strip">{config.stages.map((stage, index) => <span key={`${stage.id}-${index}`}><i>{index + 1}</i>{stage.actor || stage.type || stage.id}</span>)}</div><code>{config.config_path}</code></div>)}</section></div>
}

function Integrate({ capabilities, databases, selectedDb, setSelectedDb, refreshDatabases }) {
  const [tab, setTab] = useState('database')
  const showDatabaseUpload = featureEnabled(capabilities, 'database_upload')
  return <div className="workspace"><PageHeading eyebrow="Integration Harness" title="Reusable platform components" status={<Status tone="success">native contract</Status>} /><div className="section-tabs"><button className={tab === 'database' ? 'active' : ''} onClick={() => setTab('database')}>Database & Benchmark Adapter</button><button className={tab === 'method' ? 'active' : ''} onClick={() => setTab('method')}>Method Adapter Registry</button></div>{tab === 'database' ? <DatabaseManager {...{ databases, selectedDb, setSelectedDb, refreshDatabases, showDatabaseUpload }} /> : <MethodRegistry capabilities={capabilities} />}</div>
}

function EvaluationGraph({ configs, methods, datasets, selected, setSelected, onMissingConfig }) {
  const [activeMethod, setActiveMethod] = useState('')
  const keyOf = item => `${item.dataset}/${item.method}`
  const graphHeight = Math.max(360, Math.max(methods.length, datasets.length) * 54)
  const methodY = method => ((methods.indexOf(method) + .5) / methods.length) * graphHeight
  const datasetY = dataset => ((datasets.indexOf(dataset) + .5) / datasets.length) * graphHeight
  const pathFor = item => `M 280 ${methodY(item.method)} C 430 ${methodY(item.method)}, 570 ${datasetY(item.dataset)}, 720 ${datasetY(item.dataset)}`

  useEffect(() => { if (!methods.includes(activeMethod)) setActiveMethod(methods[0] || '') }, [methods.join('|'), activeMethod])

  const toggleDataset = dataset => {
    const config = configs.find(item => item.method === activeMethod && item.dataset === dataset)
    const pair = config || { method: activeMethod, dataset }
    const key = keyOf(pair)
    const connected = selected.includes(key)
    if (!connected && !config && !onMissingConfig) return
    if (!connected && selected.length >= 6) return
    if (!connected && !config) onMissingConfig?.(pair)
    setSelected(current => current.includes(key)
      ? current.filter(item => item !== key)
      : current.length < 6 ? [...current, key] : current)
  }

  return <div className="relation-graph" style={{ '--graph-height': `${graphHeight}px` }}>
    <div className="relation-head"><span>Text-to-SQL methods</span><b>{selected.length} / 6 connections</b><span>Databases / evaluation sets</span></div>
    <div className="relation-canvas" style={{ height: graphHeight }}>
      <svg viewBox={`0 0 1000 ${graphHeight}`} preserveAspectRatio="none" role="img" aria-label="Selected many-to-many evaluation connections between methods and databases">
        <title>Method to database evaluation graph</title>
        <desc>Faint lines are registered reproduce configurations. Bright lines are selected for the next evaluation.</desc>
        {configs.map(item => {
          const key = keyOf(item)
          const isSelected = selected.includes(key)
          const isActive = item.method === activeMethod
          return <path key={key} d={pathFor(item)} className={isSelected ? 'selected' : isActive ? 'available' : ''} />
        })}
        {selected.filter(key => !configs.some(item => keyOf(item) === key)).map(key => { const [dataset, method] = key.split('/'); return <path key={`pending-${key}`} d={pathFor({ dataset, method })} className="pending" /> })}
      </svg>
      <div className="relation-nodes method-nodes">{methods.map((method, index) => {
        const count = selected.filter(key => key.endsWith(`/${method}`)).length
        return <button key={method} style={{ top: ((index + .5) / methods.length) * 100 + '%' }} className={`${activeMethod === method ? 'active' : ''} ${count ? 'connected' : ''}`} onClick={() => setActiveMethod(method)} aria-pressed={activeMethod === method}><span>{method}</span><small>{count || configs.filter(item => item.method === method).length} {count ? 'selected' : 'available'}</small><i /></button>
      })}</div>
      <div className="relation-nodes dataset-nodes">{datasets.map((dataset, index) => {
        const config = configs.find(item => item.method === activeMethod && item.dataset === dataset)
        if (!config && !onMissingConfig) return null
        const key = keyOf(config || { method: activeMethod, dataset })
        const connected = selected.includes(key)
        const count = selected.filter(item => item.startsWith(`${dataset}/`)).length
        return <button key={dataset} style={{ top: ((index + .5) / datasets.length) * 100 + '%' }} className={connected ? config ? 'connected' : 'pending' : ''} onClick={() => toggleDataset(dataset)} aria-pressed={connected} aria-label={connected ? `Disconnect ${activeMethod} and ${dataset}` : config ? `Connect ${activeMethod} and ${dataset}` : `Create config and connect ${activeMethod} and ${dataset}`}><i /><span>{dataset}</span><small>{count ? `${count} selected` : config?.split || 'config required'}</small></button>
      })}</div>
    </div>
    <div className="selected-pairs">{selected.map(key => {
      const config = configs.find(item => keyOf(item) === key)
      const relation = config || (() => { const [dataset, method] = key.split('/'); return { dataset, method } })()
      return <button key={key} className={config ? '' : 'pending'} onClick={() => setSelected(current => current.filter(item => item !== key))} aria-label={`Remove ${relation.method} on ${relation.dataset}`}><span>{relation.method}</span><i>→</i><b>{relation.dataset}</b>{!config && <small>config required</small>}<em>×</em></button>
    })}</div>
  </div>
}

function Evaluate({ capabilities, jobs, refreshSession }) {
  const configs = capabilities?.reproduce_configs || []
  const [selected, setSelected] = useState([])
  const [comparisonId, setComparisonId] = useState('')
  const [selectedJob, setSelectedJob] = useState('')
  const [log, setLog] = useState('')
  const [error, setError] = useState('')
  const [sampleLimit, setSampleLimit] = useState(100)
  const [sampleMode, setSampleMode] = useState('random')
  const [sampleSeed, setSampleSeed] = useState(42)
  const keyOf = item => `${item.dataset}/${item.method}`

  useEffect(() => { if (!comparisonId) { const latest = jobs.find(job => job.comparison_id)?.comparison_id; if (latest) setComparisonId(latest) } }, [jobs, comparisonId])
  const comparisonJobs = jobs.filter(job => job.comparison_id === comparisonId)
  useEffect(() => { if (comparisonJobs.length && !comparisonJobs.some(job => job.job_id === selectedJob)) setSelectedJob(comparisonJobs[0].job_id) }, [comparisonJobs.map(job => job.job_id).join('|'), selectedJob])
  useEffect(() => {
    if (!selectedJob) { setLog(''); return }
    let active = true
    const load = async () => { try { const detail = await api(`/api/evaluations/${selectedJob}`); if (active) setLog(detail.log || '') } catch (err) { if (active) setError(err.message) } }
    load(); const timer = setInterval(load, 2000); return () => { active = false; clearInterval(timer) }
  }, [selectedJob])

  const start = async () => {
    setError('')
    try {
      const pairs = configs.filter(item => selected.includes(keyOf(item))).map(({ dataset, method }) => ({ dataset, method }))
      const data = await postJson('/api/comparisons', { pairs, sample_limit: sampleLimit, sample_mode: sampleMode, sample_seed: sampleSeed })
      setComparisonId(data.comparison_id); setSelectedJob(data.jobs[0]?.job_id || ''); await refreshSession()
    } catch (err) { setError(err.message) }
  }
  const cancel = async jobId => { try { await postJson(`/api/evaluations/${jobId}/cancel`, {}); await refreshSession() } catch (err) { setError(err.message) } }

  return <div className="workspace"><PageHeading eyebrow="Evaluation Module" title="Figure Studio" status={<Status tone={comparisonJobs.some(job => job.status === 'running') ? 'running' : comparisonJobs.length ? 'success' : 'neutral'}>{comparisonJobs.length ? `${comparisonJobs.length} session runs` : 'No session runs'}</Status>} />
    <section className="tool-panel experiment-builder relation-studio"><div className="panel-title"><div><span>Method × database evaluation graph</span><small>Many-to-many reproduce configurations</small></div><Status tone={selected.length >= 2 ? 'success' : 'neutral'}>{selected.length} selected</Status></div><EvaluationGraph configs={configs} selected={selected} setSelected={setSelected} /><div className="evaluation-command"><div className="sampling-controls"><div className="scope-control"><span>Sample size</span><div>{[[20, '20'], [50, '50'], [100, '100'], [200, '200']].map(([value, label]) => <button key={label} className={sampleLimit === value ? 'active' : ''} onClick={() => setSampleLimit(value)}>{label}</button>)}</div></div><div className="sample-mode"><span>Sampling</span><div className="segmented"><button className={sampleMode === 'slice' ? 'active' : ''} onClick={() => setSampleMode('slice')}>Dev slice</button><button className={sampleMode === 'random' ? 'active' : ''} onClick={() => setSampleMode('random')}>Random</button></div>{sampleMode === 'random' && <label><span>Seed</span><input type="number" value={sampleSeed} onChange={event => setSampleSeed(Number(event.target.value))} /></label>}</div></div><button className="button primary" disabled={selected.length < 2 || comparisonJobs.some(job => job.status === 'running')} onClick={start}>Run {selected.length} connected evaluations · {sampleMode} {sampleLimit}{sampleMode === 'random' ? ` · seed ${sampleSeed}` : ''}</button></div>{error && <p className="error-banner">{error}</p>}</section>
    <div className="run-monitor-layout"><section className="tool-panel live-runs"><div className="panel-title"><div><span>Live run control</span><small>{comparisonId || 'New demo session'}</small></div></div>{comparisonJobs.length ? comparisonJobs.map(job => <button key={job.job_id} className={selectedJob === job.job_id ? 'active' : ''} onClick={() => setSelectedJob(job.job_id)}><span><b>{job.method}</b><small>{job.dataset} · {job.config?.scope}</small></span><Status tone={jobTone(job.status)}>{job.status}</Status>{job.status === 'running' && <i role="button" aria-label={`Cancel ${job.method} on ${job.dataset}`} onClick={event => { event.stopPropagation(); cancel(job.job_id) }}>×</i>}</button>) : <Empty title="No evaluations started" detail="Connect at least two method-database pairs." />}</section><section className="tool-panel evaluation-log"><div className="panel-title"><div><span>Selected run log</span><small>{selectedJob || 'No run selected'}</small></div></div><pre>{log || 'Waiting for a connected evaluation.'}</pre></section></div>
  </div>
}

function Adapt({ jobs, setPage, refreshSession }) {
  const completed = jobs.filter(job => job.status === 'completed' && job.result)
  const [jobId, setJobId] = useState('')
  const [profile, setProfile] = useState(null)
  const [profiling, setProfiling] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!completed.some(job => job.job_id === jobId)) setJobId(completed[0]?.job_id || '') }, [completed.map(job => job.job_id).join('|'), jobId])
  const job = completed.find(item => item.job_id === jobId)
  useEffect(() => { setProfile(job?.weakness_profile || null) }, [jobId, job?.weakness_profile])
  const runProfile = async () => { setProfiling(true); setError(''); try { const data = await postJson(`/api/evaluations/${jobId}/profile`, {}); setProfile(data.profile); await refreshSession() } catch (err) { setError(err.message) } finally { setProfiling(false) } }
  if (!completed.length) return <div className="workspace"><PageHeading eyebrow="Metric-Guided Adaptation" title="Bounded loop" status={<Status tone="warning">score bundle required</Status>} /><div className="adapt-empty"><div className="gate-diagram"><span className="complete">Reproduce Run</span><i>→</i><span>Score Bundle</span><i>→</i><span>Weakness Profile</span><i>→</i><span>Candidate Review</span></div><Empty title="No completed evaluation in this demo session" detail="Historical artifacts are intentionally excluded." action={<button className="button primary" onClick={() => setPage('evaluate')}>Open Evaluate</button>} /></div></div>
  const result = job?.result
  return <div className="workspace"><PageHeading eyebrow="Metric-Guided Adaptation" title="Bounded loop" status={<Status tone={profile ? 'success' : 'warning'}>{profile ? 'profile ready' : 'diagnosis pending'}</Status>} /><label className="field run-select"><span>Session score bundle</span><select value={jobId} onChange={event => setJobId(event.target.value)}>{completed.map(item => <option key={item.job_id} value={item.job_id}>{item.method} / {item.dataset} / {item.run_id}</option>)}</select></label><div className="adapt-steps"><section className="tool-panel adapt-step done"><div className="step-label"><i>01</i><span>Baseline score bundle</span></div><div className="baseline-metrics">{['ex', 'em', 'sf1', 'ves'].map(metric => <div key={metric}><span>{metric.toUpperCase()}</span><b>{percent(result?.metrics?.[metric])}</b></div>)}</div><code>{result?.run_id}</code></section><section className={`tool-panel adapt-step ${profile ? 'done' : 'current'}`}><div className="step-label"><i>02</i><span>Weakness profile</span></div>{profile ? <div className="weakness-list">{(profile.top_error_roots || []).map(item => <div key={item.root}><span>{item.root.replaceAll('_', ' ')}</span><b>{item.count}</b></div>)}</div> : <Empty title="Profile this run" detail="Uses the current session score bundle and execution store." />}<button className="button secondary" disabled={profiling} onClick={runProfile}>{profiling ? 'Profiling…' : profile ? 'Refresh profile' : 'Profile weaknesses'}</button></section><section className="tool-panel adapt-step gated"><div className="step-label"><i>03</i><span>Candidate plan review</span></div><div className="gate-status"><Status tone="warning">human gate</Status><p>{profile ? 'A reviewed action pool and isolated feature branch are required before smoke evaluation.' : 'Complete weakness profiling before proposing a bounded candidate.'}</p></div><ul><li>Actor / prompt / config scope</li><li>Smoke → bounded → full confirmation</li><li>Accept / reject / merge review</li></ul></section></div>{error && <p className="error-banner">{error}</p>}</div>
}

function App() {
  const [page, setPage] = useState('studio')
  const [health, setHealth] = useState(null)
  const [capabilities, setCapabilities] = useState(null)
  const [databases, setDatabases] = useState([])
  const [selectedDb, setSelectedDb] = useState('')
  const [busy, setBusy] = useState(false)
  const hosted = deploymentTarget(capabilities) === 'hf-space'
  const selectedStudio = studioSurface(capabilities)
  const showProviderConfig = featureEnabled(capabilities, 'provider_configuration')
  const showAgentHarness = featureEnabled(capabilities, 'agent_chat')
  const liveEvaluation = featureEnabled(capabilities, 'live_evaluation')
  const refresh = async () => { setBusy(true); try { const [healthData, capabilityData, databaseData] = await Promise.all([api('/api/health'), api('/api/capabilities'), api('/api/databases')]); setHealth(healthData); setCapabilities(capabilityData); setDatabases(databaseData.databases) } catch (error) { setHealth({ status: 'error', provider: { configured: false, ready: false, message: error.message } }) } finally { setBusy(false) } }
  useEffect(() => { refresh() }, [])
  return <div className="app-shell"><ShellNav page={page} setPage={setPage} /><main><Topbar health={health} capabilities={capabilities} refresh={refresh} busy={busy} hosted={hosted} showProviderConfig={showProviderConfig} />{hosted && <div className="hosted-demo-notice">Hugging Face Live Demo · the LLM and model are configured by SqurveBridge</div>}{page === 'board' ? <ExperimentBoard {...{ capabilities, liveEvaluation, api, postJson, Status, PageHeading, Empty }} /> : page === 'archive' ? <Archive {...{ api, Status, PageHeading, Empty }} /> : selectedStudio === 'live-sql' ? <Studio {...{ health, capabilities, databases, selectedDb, setSelectedDb, showAgentHarness }} /> : <WorkspaceStudio {...{ capabilities, databases, showAgentHarness, liveEvaluation }} />}</main></div>
}

const root = globalThis.__SQURVE_DEMO_ROOT__ || createRoot(document.getElementById('root'))
globalThis.__SQURVE_DEMO_ROOT__ = root
root.render(<App />)
