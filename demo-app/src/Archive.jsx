import { useEffect, useMemo, useState } from 'react'

const percent = value => (value == null || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(1)}%`)
const compact = value => (value == null ? '—' : Intl.NumberFormat('en', { notation: 'compact' }).format(value))
const bytes = value => {
  if (value == null) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function renderMarkdown(text) {
  const lines = String(text || '').split(/\r?\n/)
  const blocks = []
  let list = null
  const flushList = () => {
    if (list?.length) {
      blocks.push(<ul key={`ul-${blocks.length}`}>{list.map((item, index) => <li key={index}>{item}</li>)}</ul>)
    }
    list = null
  }
  lines.forEach((line, index) => {
    if (/^\s*[-*]\s+/.test(line)) {
      list = list || []
      list.push(line.replace(/^\s*[-*]\s+/, ''))
      return
    }
    flushList()
    if (!line.trim()) {
      blocks.push(<div key={`sp-${index}`} className="md-space" />)
    } else if (line.startsWith('### ')) {
      blocks.push(<h4 key={index}>{line.slice(4)}</h4>)
    } else if (line.startsWith('## ')) {
      blocks.push(<h3 key={index}>{line.slice(3)}</h3>)
    } else if (line.startsWith('# ')) {
      blocks.push(<h2 key={index}>{line.slice(2)}</h2>)
    } else if (line.startsWith('```')) {
      blocks.push(<pre key={index} className="md-code">{line}</pre>)
    } else {
      blocks.push(<p key={index}>{line}</p>)
    }
  })
  flushList()
  return blocks
}

function FileViewer({ file, onClose }) {
  if (!file) {
    return <div className="archive-viewer empty-viewer"><strong>Select a report file</strong><span>Open scores.json, weakness_profile.md, detailed-report.txt, or config snapshots.</span></div>
  }
  return (
    <section className="archive-viewer">
      <header>
        <div>
          <span>{file.name}</span>
          <small>{file.path} · {bytes(file.size_bytes)}{file.truncated ? ' · truncated' : ''}</small>
        </div>
        <button className="button compact secondary" type="button" onClick={onClose}>Close</button>
      </header>
      {file.kind === 'markdown' ? (
        <div className="md-body">{renderMarkdown(file.content)}</div>
      ) : file.kind === 'json' && file.json != null ? (
        <pre className="raw-json">{JSON.stringify(file.json, null, 2)}</pre>
      ) : (
        <pre className="raw-json">{file.content}</pre>
      )}
    </section>
  )
}

export default function Archive({
  api,
  Status,
  PageHeading,
  Empty,
}) {
  const [query, setQuery] = useState('')
  const [dataset, setDataset] = useState('')
  const [method, setMethod] = useState('')
  const [source, setSource] = useState('')
  const [catalog, setCatalog] = useState({ runs: [], filters: { datasets: [], methods: [], sources: [] }, total: 0 })
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState(null)
  const [filePayload, setFilePayload] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadCatalog = async () => {
    setBusy(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (query.trim()) params.set('q', query.trim())
      if (dataset) params.set('dataset', dataset)
      if (method) params.set('method', method)
      if (source) params.set('source', source)
      const data = await api(`/api/archive?${params}`)
      setCatalog(data)
      if (selectedId && !data.runs.some(run => run.run_id === selectedId)) {
        setSelectedId(data.runs[0]?.run_id || '')
      } else if (!selectedId && data.runs[0]) {
        setSelectedId(data.runs[0].run_id)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const timer = setTimeout(loadCatalog, 120)
    return () => clearTimeout(timer)
  }, [query, dataset, method, source])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setFilePayload(null)
      return
    }
    let active = true
    const load = async () => {
      try {
        const data = await api(`/api/archive/${encodeURIComponent(selectedId)}`)
        if (!active) return
        setDetail(data)
        setFilePayload(null)
        const preferred = data.files?.find(item => item.name === 'scores.json')
          || data.files?.find(item => item.kind === 'markdown')
          || data.files?.[0]
        if (preferred) {
          const file = await api(`/api/archive/${encodeURIComponent(selectedId)}/files/${preferred.path}`)
          if (active) setFilePayload(file)
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }
    load()
    return () => { active = false }
  }, [selectedId])

  const openFile = async path => {
    if (!selectedId || !path) return
    setError('')
    try {
      const file = await api(`/api/archive/${encodeURIComponent(selectedId)}/files/${path}`)
      setFilePayload(file)
    } catch (err) {
      setError(err.message)
    }
  }

  const groupedFiles = useMemo(() => {
    const groups = { reports: [], scores: [], configs: [], other: [] }
    for (const file of detail?.files || []) {
      if (file.kind === 'markdown' || file.name.includes('report') || file.name.endsWith('.log')) groups.reports.push(file)
      else if (file.name.includes('score') || file.name.includes('token') || file.name.includes('meta-evo')) groups.scores.push(file)
      else if (file.name.includes('config') || file.name.includes('task')) groups.configs.push(file)
      else groups.other.push(file)
    }
    return groups
  }, [detail])

  return (
    <div className="workspace archive-workspace">
      <PageHeading
        eyebrow="Experiment archive"
        title="Artifacts library"
        status={<Status tone={catalog.total ? 'success' : 'neutral'}>{catalog.total} runs indexed</Status>}
      />

      <section className="tool-panel archive-filters">
        <div className="panel-title">
          <div>
            <span>Find experiment data</span>
            <small>Search verified public evidence, local artifacts, and demo-run score bundles</small>
          </div>
          <button className="button compact secondary" disabled={busy} onClick={loadCatalog}>{busy ? 'Scanning…' : 'Refresh'}</button>
        </div>
        <div className="archive-filter-grid">
          <label className="field">
            <span>Search</span>
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="run id · method · dataset · filename" />
          </label>
          <label className="field">
            <span>Dataset</span>
            <select value={dataset} onChange={event => setDataset(event.target.value)}>
              <option value="">All datasets</option>
              {(catalog.filters?.datasets || []).map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Method</span>
            <select value={method} onChange={event => setMethod(event.target.value)}>
              <option value="">All methods</option>
              {(catalog.filters?.methods || []).map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Source</span>
            <select value={source} onChange={event => setSource(event.target.value)}>
              <option value="">All sources</option>
              {(catalog.filters?.sources || []).map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
        </div>
        {error && <p className="error-banner">{error}</p>}
      </section>

      <div className="archive-layout">
        <section className="tool-panel archive-list">
          <div className="panel-title">
            <div>
              <span>Runs</span>
              <small>{catalog.total} matching</small>
            </div>
          </div>
          <div className="archive-run-list">
            {catalog.runs.length ? catalog.runs.map(run => (
              <button
                key={run.run_id}
                className={selectedId === run.run_id ? 'active' : ''}
                onClick={() => setSelectedId(run.run_id)}
              >
                <div>
                  <b>{run.method || 'unknown'} / {run.dataset || 'unknown'}</b>
                  <small>{run.run_id}</small>
                </div>
                <div className="archive-run-meta">
                  <span>{percent(run.metrics?.ex)} EX</span>
                  <span>{run.sample_count ?? '—'} n</span>
                  <span>{run.source}</span>
                </div>
                <div className="archive-run-flags">
                  {run.has_report && <i>report</i>}
                  {run.has_markdown && <i>md</i>}
                  <i>{run.file_count} files</i>
                </div>
              </button>
            )) : <Empty title="No archived runs" detail="Verified public bundles live under evidence/reported-results; local evaluations write into artifacts/ and tmp/demo-runs." />}
          </div>
        </section>

        <div className="archive-detail">
          {!detail ? (
            <section className="tool-panel board-empty">
              <Empty title="Select a run" detail="Browse score bundles, markdown weakness profiles, and JSON reports." />
            </section>
          ) : (
            <>
              <section className="tool-panel archive-summary">
                <div className="panel-title">
                  <div>
                    <span>{detail.method} on {detail.dataset}</span>
                    <small>{detail.run_id}</small>
                  </div>
                  <Status tone="success">{detail.source}</Status>
                </div>
                <div className="archive-metric-strip">
                  {['ex', 'em', 'sf1', 'ves', 'rves'].map(metric => (
                    <div key={metric}>
                      <span>{metric.toUpperCase()}</span>
                      <b>{percent(detail.metrics?.[metric])}</b>
                    </div>
                  ))}
                  <div>
                    <span>Tokens</span>
                    <b>{compact(detail.token?.total_tokens)}</b>
                  </div>
                  <div>
                    <span>Samples</span>
                    <b>{detail.sample_count ?? '—'}</b>
                  </div>
                </div>
                <div className="archive-summary-meta">
                  <span>Split <b>{detail.split || '—'}</b></span>
                  <span>Scope <b>{detail.scope || '—'}</b></span>
                  <span>Sampling <b>{detail.sampling?.mode || '—'}{detail.sampling?.limit ? `-${detail.sampling.limit}` : ''}{detail.sampling?.seed != null ? ` · seed ${detail.sampling.seed}` : ''}</b></span>
                  <span>Timestamp <b>{detail.timestamp || '—'}</b></span>
                </div>
              </section>

              <div className="archive-reader">
                <section className="tool-panel archive-files">
                  <div className="panel-title">
                    <div>
                      <span>Files</span>
                      <small>Expand markdown / JSON / text reports</small>
                    </div>
                  </div>
                  {Object.entries(groupedFiles).map(([group, files]) => files.length ? (
                    <div key={group} className="archive-file-group">
                      <header>{group}</header>
                      {files.map(file => (
                        <button
                          key={file.path}
                          className={filePayload?.path === file.path ? 'active' : ''}
                          onClick={() => openFile(file.path)}
                        >
                          <span>{file.name}</span>
                          <small>{file.kind} · {bytes(file.size_bytes)}</small>
                        </button>
                      ))}
                    </div>
                  ) : null)}
                </section>
                <div className="tool-panel archive-viewer-shell">
                  <FileViewer file={filePayload} onClose={() => setFilePayload(null)} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
