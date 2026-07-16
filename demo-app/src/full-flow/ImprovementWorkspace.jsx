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

export default function ImprovementWorkspace({ evidence, t }) {
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

  return <section id="improve" className="flow-module improvement-workspace">
    <header className="flow-module-header">
      <div>
        <span>{t('process.improve')}</span>
        <h2>{t('improve.title')}</h2>
      </div>
    </header>
    {records.length === 0 && <p>{t('improve.empty')}</p>}
    {records.length > 0 && <ol>
      {records.map(record => <li key={record.field}>
        <h3>{t(record.label)}</h3>
        <RecordedValue value={record.value} />
      </li>)}
    </ol>}
  </section>
}
