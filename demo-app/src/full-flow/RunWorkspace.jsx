import { useMemo, useState } from 'react'

export const RUN_PHASES = [
  'ready',
  'loadingData',
  'buildingWorkflow',
  'generatingSql',
  'executingSql',
  'evaluating',
  'completed',
  'failed',
]

export const INITIAL_RUN_STATE = {
  phase: 'ready',
  sql: '',
  trace: [],
  result: null,
  error: '',
  busy: false,
}

const sensitivePatterns = [
  [/\bAuthorization\s*:\s*Bearer\s+\S+/gi, 'Authorization: Bearer [redacted]'],
  [/\b(api[_-]?key|token|secret)\s*[=:]\s*\S+/gi, '$1=[redacted]'],
  [/\bsk-[A-Za-z0-9_-]{6,}\b/g, '[redacted]'],
]

export function sanitizeRunError(error) {
  const fallback = 'Request failed'
  return sensitivePatterns.reduce(
    (message, [pattern, replacement]) => message.replace(pattern, replacement),
    String(error?.message || fallback),
  )
}

const actorNames = config => (config?.stages || [])
  .map(stage => stage.actor)
  .filter(Boolean)

const databaseIdFor = (databases, focusedDatabase) =>
  (databases || []).find(
    database => String(database.id).toLowerCase() === String(focusedDatabase).toLowerCase(),
  )?.id || focusedDatabase

export default function RunWorkspace({
  focusedConfig,
  focusedMethod,
  focusedDatabase,
  databases,
  sampleLimit,
  sampleMode,
  sampleSeed,
  sqlAuth,
  postJson,
  onConfigureSql,
  onRunStateChange,
  t,
}) {
  const [question, setQuestion] = useState('')
  const [runState, setRunState] = useState(INITIAL_RUN_STATE)
  const [failedPhase, setFailedPhase] = useState('')
  const actors = useMemo(() => actorNames(focusedConfig), [focusedConfig])
  const databaseId = databaseIdFor(databases, focusedDatabase)
  const generator = (focusedConfig?.stages || []).find(stage => stage.type === 'GenerateTask')?.actor
    || actors.at(-1)
    || ''
  const runnable = Boolean(focusedConfig && sqlAuth?.configured && databaseId)
  const preview = {
    method: focusedMethod,
    database: databaseId,
    config: focusedConfig?.config_path || null,
    sampling: {
      limit: sampleLimit,
      mode: sampleMode,
      seed: sampleSeed,
    },
    workflow: (focusedConfig?.stages || []).map(stage => ({
      id: stage.id,
      type: stage.type,
      actor: stage.actor,
    })),
  }

  const publish = next => {
    setRunState(next)
    onRunStateChange(next)
  }

  const advance = (phase, current, additions = {}) => {
    const next = { ...current, ...additions, phase }
    publish(next)
    return next
  }

  const run = async () => {
    if (!runnable || !question.trim() || runState.busy) return

    setFailedPhase('')
    let current = advance('loadingData', {
      ...INITIAL_RUN_STATE,
      busy: true,
    })
    try {
      current = advance('buildingWorkflow', current)
      current = advance('generatingSql', current)
      const generated = await postJson('/api/query', {
        question: question.trim(),
        db_id: databaseId,
        mode: actors.length ? 'workflow' : 'direct',
        actors,
        generator,
        provider: sqlAuth?.provider,
        model: sqlAuth?.model,
      })
      if (!generated?.sql) throw new Error('The query endpoint returned no SQL.')

      current = advance('executingSql', current, {
        sql: generated.sql,
        trace: Array.isArray(generated.trace) ? generated.trace : [],
      })
      const execution = await postJson('/api/execute', {
        db_id: databaseId,
        sql: generated.sql,
      })
      current = advance('evaluating', current, { result: execution })
      advance('completed', current, { busy: false })
    } catch (error) {
      setFailedPhase(current.phase)
      advance('failed', current, {
        busy: false,
        error: sanitizeRunError(error),
      })
    }
  }

  const phasePosition = RUN_PHASES.indexOf(runState.phase)
  const failedPhasePosition = RUN_PHASES.indexOf(failedPhase)

  return <section id="run" className="flow-module run-workspace">
    <header className="flow-module-header">
      <div>
        <span>{t('process.run')}</span>
        <h2>{t('run.title')}</h2>
        <p>{t('run.description')}</p>
      </div>
      <strong>{t(`status.${runState.phase === 'failed' ? 'failed' : runState.busy ? 'running' : runState.phase}`)}</strong>
    </header>

    <div className="run-workspace-grid">
      <div>
        <span>{t('run.configPreview')}</span>
        <pre>{JSON.stringify(preview, null, 2)}</pre>
      </div>
      <div>
        <label>
          <span>{t('run.question')}</span>
          <textarea
            value={question}
            onChange={event => setQuestion(event.target.value)}
            placeholder={t('run.questionPlaceholder')}
          />
        </label>
        {!focusedConfig && <p>{t('run.unavailable')}</p>}
        {!sqlAuth?.configured && <button
          type="button"
          aria-label={t('run.configureModelAction')}
          onClick={onConfigureSql}
        >
          {t('run.configureModel')}
        </button>}
        <button
          type="button"
          disabled={!runnable || !question.trim() || runState.busy}
          onClick={run}
        >
          {t('run.action')}
        </button>
      </div>
    </div>

    <ol className="run-phase-list" aria-label={t('run.stageStatus')}>
      {RUN_PHASES.slice(1, -2).map((phase, index) => {
        const absoluteIndex = RUN_PHASES.indexOf(phase)
        const state = runState.phase === 'failed'
          ? absoluteIndex === failedPhasePosition
            ? 'failed'
            : absoluteIndex < failedPhasePosition
              ? 'completed'
              : 'pending'
          : runState.phase === 'completed' || absoluteIndex < phasePosition
            ? 'completed'
            : absoluteIndex === phasePosition
              ? 'current'
              : 'pending'
        return <li key={phase} data-state={state}>
          <i>{index + 1}</i>
          <span>{t(`run.${phase}`)}</span>
        </li>
      })}
    </ol>

    {runState.sql && <code className="run-sql">{runState.sql}</code>}
    {runState.error && <p className="error-banner" role="alert">{runState.error}</p>}
  </section>
}
