import { useState } from 'react'
import { resolveInspectArtifacts } from './sampleRunArtifacts.js'

const TAB_IDS = ['sql', 'result', 'trace', 'metrics', 'logs']

function EmptyEvidence({ children }) {
  return <p className="result-empty">{children}</p>
}

function ResultTable({ result, empty }) {
  if (!result || !Array.isArray(result.columns) || !Array.isArray(result.rows)) {
    return <EmptyEvidence>{empty}</EmptyEvidence>
  }
  return <div className="results-table-wrap">
    <table>
      <thead>
        <tr>{result.columns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}</tr>
      </thead>
      <tbody>
        {result.rows.map((row, rowIndex) => <tr key={rowIndex}>
          {row.map((value, columnIndex) => <td key={columnIndex}>
            {value == null ? <em>NULL</em> : String(value)}
          </td>)}
        </tr>)}
      </tbody>
    </table>
    <p>{result.row_count} · {result.elapsed_ms} ms</p>
  </div>
}

function MetricsPanel({ metrics, empty }) {
  if (!metrics || typeof metrics !== 'object' || !Object.keys(metrics).length) {
    return <EmptyEvidence>{empty}</EmptyEvidence>
  }
  return <dl className="inspect-metrics" data-testid="inspect-metrics">
    {Object.entries(metrics).map(([key, value]) => <div key={key}>
      <dt>{key}</dt>
      <dd><code>{typeof value === 'number' ? String(value) : JSON.stringify(value)}</code></dd>
    </div>)}
  </dl>
}

function LogsPanel({ logs, empty }) {
  if (!Array.isArray(logs) || !logs.length) {
    return <EmptyEvidence>{empty}</EmptyEvidence>
  }
  return <ol className="inspect-logs" data-testid="inspect-logs">
    {logs.map((line, index) => <li key={`${index}-${line}`}>
      <code>{line}</code>
    </li>)}
  </ol>
}

function TracePanel({ trace, empty }) {
  if (!trace?.length) {
    return <EmptyEvidence>{empty}</EmptyEvidence>
  }
  return <div className="inspect-trace" data-testid="inspect-trace">
    <ol>
      {trace.map((item, index) => {
        const label = item.actor_name || item.actor || item.stage || `#${index + 1}`
        return (
          <li key={`${label}-${index}`}>
            <span>{item.stage || String(index + 1)}</span>
            <strong>{label}</strong>
            {item.status ? <small>{item.status}</small> : null}
            {item.elapsed_ms != null ? <em>{item.elapsed_ms} ms</em> : null}
          </li>
        )
      })}
    </ol>
  </div>
}

export default function ResultWorkspace({ runState, t }) {
  const [selectedTab, setSelectedTab] = useState('sql')
  const state = resolveInspectArtifacts(runState)
  const showPanels = Boolean(state.sql || state.result || state.trace?.length || state.phase === 'failed')

  const content = {
    sql: state.sql
      ? <div className="inspect-sql" data-testid="inspect-sql">
        {state.question ? <p className="inspect-question"><span>{t('inspect.question')}</span> {state.question}</p> : null}
        <code>{state.sql}</code>
      </div>
      : <EmptyEvidence>{t('inspect.noSql')}</EmptyEvidence>,
    result: <ResultTable result={state.result} empty={t('inspect.noResult')} />,
    trace: <TracePanel trace={state.trace} empty={t('inspect.noTrace')} />,
    metrics: <MetricsPanel metrics={state.metrics} empty={t('inspect.evidenceRequired')} />,
    logs: <LogsPanel logs={state.logs} empty={t('inspect.evidenceRequired')} />,
  }

  return <section id="inspect" className="flow-module flow-glass result-workspace">
    <header className="flow-module-header">
      <div>
        <span>{t('process.inspect')}</span>
        <h2>{t('inspect.title')}</h2>
        <p>{t('inspect.description')}</p>
      </div>
    </header>

    {state.context && <aside className="result-run-context" data-testid="run-context">
      <span>{t('inspect.runContext')}</span>
      <strong>{state.context.method} → {state.context.database}</strong>
      <dl>
        <div>
          <dt>{t('inspect.contextDatabase')}</dt>
          <dd><code>{state.context.db_id}</code></dd>
        </div>
        <div>
          <dt>{t('inspect.contextConfig')}</dt>
          <dd><code>{state.context.config_path || t('status.unavailable')}</code></dd>
        </div>
        <div>
          <dt>{t('inspect.contextActors')}</dt>
          <dd>{state.context.actors?.join(' → ') || t('status.unavailable')}</dd>
        </div>
        {state.artifact_ref ? (
          <div>
            <dt>{t('inspect.artifactRef')}</dt>
            <dd><code>{state.artifact_ref}</code></dd>
          </div>
        ) : null}
      </dl>
    </aside>}

    {!showPanels
      ? <EmptyEvidence>{t('inspect.empty')}</EmptyEvidence>
      : <>
        <div role="tablist" aria-label={t('inspect.title')}>
          {TAB_IDS.map(tab => <button
            key={tab}
            id={`inspect-tab-${tab}`}
            type="button"
            role="tab"
            aria-controls={`inspect-panel-${tab}`}
            aria-selected={selectedTab === tab}
            onClick={() => setSelectedTab(tab)}
          >
            {t(`inspect.${tab}`)}
          </button>)}
        </div>
        <div
          id={`inspect-panel-${selectedTab}`}
          role="tabpanel"
          aria-labelledby={`inspect-tab-${selectedTab}`}
        >
          {content[selectedTab]}
        </div>
      </>}
  </section>
}
