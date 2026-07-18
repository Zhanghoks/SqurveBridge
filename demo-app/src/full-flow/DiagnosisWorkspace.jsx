const DIAGNOSTIC_FIELDS = [
  ['errors', 'diagnose.errorRoots'],
  ['by_hardness', 'diagnose.hardness'],
  ['by_sql_feature', 'diagnose.components'],
  ['stage_metrics', 'diagnose.stages'],
  ['latency', 'diagnose.latency'],
]

const SAMPLE_FIELDS = [
  'instance_id',
  'db_id',
  'hardness',
  'ex',
  'error_root',
  'error_sub',
  'sl_recall',
  'act_elapsed_s',
]

const hasEntries = value =>
  value != null
  && typeof value === 'object'
  && Object.keys(value).length > 0

function EvidenceValue({ value }) {
  if (value != null && typeof value === 'object') {
    return <pre>{JSON.stringify(value, null, 2)}</pre>
  }
  return <span>{String(value)}</span>
}

function DiagnosticGroup({ title, value }) {
  return <section>
    <h3>{title}</h3>
    <dl>
      {Object.entries(value).map(([name, detail]) => <div key={name}>
        <dt>{name}</dt>
        <dd><EvidenceValue value={detail} /></dd>
      </div>)}
    </dl>
  </section>
}

function SanitizedSamples({ samples, title }) {
  return <section>
    <h3>{title}</h3>
    <ol>
      {samples.map((sample, index) => <li key={sample.instance_id || index}>
        <dl>
          {SAMPLE_FIELDS.flatMap(field =>
            sample[field] == null
              ? []
              : [<div key={field}><dt>{field}</dt><dd>{String(sample[field])}</dd></div>],
          )}
        </dl>
      </li>)}
    </ol>
  </section>
}

function Provenance({ run, t }) {
  const fields = ['run_id', 'method', 'dataset', 'split', 'sampling', 'source', 'timestamp', 'artifact_ref']
  return <aside className="evidence-provenance">
    <strong>{run.evidence_origin === 'historical-archive' ? t('evidence.historicalArchive') : t('evidence.persisted')}</strong>
    <p>{t('evidence.independent')}</p>
    <dl>{fields.flatMap(field => run[field] == null ? [] : [<div key={field}><dt>{field}</dt><dd><EvidenceValue value={run[field]} /></dd></div>])}</dl>
  </aside>
}

export default function DiagnosisWorkspace({ evidence, t, compact = false }) {
  const selectedRun = evidence?.selectedRun
  const groups = DIAGNOSTIC_FIELDS
    .map(([field, label]) => ({ field, label, value: selectedRun?.[field] }))
    .filter(group => hasEntries(group.value))
  const samples = Array.isArray(selectedRun?.samples) ? selectedRun.samples : []
  const hasEvidence = groups.length > 0 || samples.length > 0

  const Shell = compact ? 'div' : 'section'
  return <Shell id={compact ? undefined : 'diagnose'} className={compact ? 'board-section diagnosis-workspace' : 'flow-module flow-glass diagnosis-workspace'}>
    <header className={compact ? 'board-section-header' : 'flow-module-header'}>
      <div>
        {!compact && <span>{t('process.diagnose')}</span>}
        {compact ? <h3>{t('board.diagnoseSection')}</h3> : <h2>{t('diagnose.title')}</h2>}
      </div>
    </header>
    {evidence?.loading
      ? <p>{t('diagnose.loading')}</p>
      : evidence?.error
        ? <p role="alert">{t('diagnose.loadError')}</p>
        : !hasEvidence
          ? <p>{t('diagnose.empty')}</p>
          : <><Provenance run={selectedRun} t={t} /><div className="diagnostic-grid">
      {groups.map(group => <DiagnosticGroup
        key={group.field}
        title={t(group.label)}
        value={group.value}
      />)}
      {samples.length > 0 && <SanitizedSamples samples={samples} title={t('diagnose.samples')} />}
    </div></>}
  </Shell>
}
