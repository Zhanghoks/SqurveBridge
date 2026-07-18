const EVOLUTION_STAGES = [
  ['baseline', 'improve.baseline'],
  ['weakness_profile', 'improve.weakness'],
  ['candidate_change', 'improve.candidate'],
  ['smoke', 'improve.smoke'],
  ['bounded_evaluation', 'improve.bounded'],
  ['confirmation', 'improve.confirmation'],
  ['human_review', 'improve.review'],
]

const isRecorded = value => {
  if (value == null || value === '') return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value).length > 0
  return true
}

function RecordedValue({ value }) {
  if (value != null && typeof value === 'object') {
    return <pre>{JSON.stringify(value, null, 2)}</pre>
  }
  return <p>{String(value)}</p>
}

function Provenance({ run, t }) {
  const fields = ['run_id', 'method', 'dataset', 'split', 'sampling', 'source', 'timestamp', 'artifact_ref']
  return <aside className="evidence-provenance">
    <strong>{run.evidence_origin === 'historical-archive' ? t('evidence.historicalArchive') : t('evidence.persisted')}</strong>
    <p>{t('evidence.independent')}</p>
    <dl>{fields.flatMap(field => run[field] == null ? [] : [<div key={field}><dt>{field}</dt><dd><RecordedValue value={run[field]} /></dd></div>])}</dl>
  </aside>
}

export default function ImprovementWorkspace({ evidence, t, compact = false }) {
  const selectedRun = evidence?.selectedRun
  const weakness = selectedRun?.weakness ?? selectedRun?.weakness_profile
  const evolution = selectedRun?.evolution ?? selectedRun?.evolution_record
  const records = EVOLUTION_STAGES
    .map(([field, label]) => ({
      field,
      label,
      value: field === 'weakness_profile' && isRecorded(weakness)
        ? weakness
        : evolution?.[field],
    }))
    .filter(record => isRecorded(record.value))

  const Shell = compact ? 'div' : 'section'
  return <Shell id={compact ? undefined : 'improve'} className={compact ? 'board-section improvement-workspace' : 'flow-module flow-glass improvement-workspace'}>
    <header className={compact ? 'board-section-header' : 'flow-module-header'}>
      <div>
        {!compact && <span>{t('process.improve')}</span>}
        {compact ? <h3>{t('board.evolveSection')}</h3> : <h2>{t('improve.title')}</h2>}
      </div>
    </header>
    {evidence?.loading
      ? <p>{t('improve.loading')}</p>
      : evidence?.error
        ? <p role="alert">{t('improve.loadError')}</p>
        : records.length === 0
          ? <p>{t('improve.empty')}</p>
          : <><Provenance run={selectedRun} t={t} /><ol>
            {records.map(record => <li key={record.field}>
              <h3>{t(record.label)}</h3>
              <RecordedValue value={record.value} />
            </li>)}
          </ol></>}
  </Shell>
}
