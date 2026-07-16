import { useState } from 'react'

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
        <tr>{result.columns.map(column => <th key={column}>{column}</th>)}</tr>
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

export default function ResultWorkspace({ runState, t }) {
  const [selectedTab, setSelectedTab] = useState('sql')
  const state = runState || {}
  const hasRunEvidence = Boolean(state.sql || state.result || state.trace?.length)

  const content = {
    sql: state.sql
      ? <code>{state.sql}</code>
      : <EmptyEvidence>{t('inspect.noSql')}</EmptyEvidence>,
    result: <ResultTable result={state.result} empty={t('inspect.noResult')} />,
    trace: state.trace?.length
      ? <div>
        <ul>{state.trace.map((item, index) => <li key={index}>
          {item.actor_name || item.actor || item.stage || `#${index + 1}`}
        </li>)}</ul>
        <pre>{JSON.stringify(state.trace, null, 2)}</pre>
      </div>
      : <EmptyEvidence>{t('inspect.noTrace')}</EmptyEvidence>,
    metrics: <EmptyEvidence>{t('inspect.evidenceRequired')}</EmptyEvidence>,
    logs: <EmptyEvidence>{t('inspect.evidenceRequired')}</EmptyEvidence>,
  }

  return <section id="inspect" className="flow-module result-workspace">
    <header className="flow-module-header">
      <div>
        <span>{t('process.inspect')}</span>
        <h2>{t('inspect.title')}</h2>
        <p>{t('inspect.description')}</p>
      </div>
    </header>

    {!hasRunEvidence && state.phase !== 'failed'
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
            tabIndex={selectedTab === tab ? 0 : -1}
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
