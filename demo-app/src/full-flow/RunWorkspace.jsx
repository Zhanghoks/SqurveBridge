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

const OPERATION_PHASES = new Set(['generatingSql', 'executingSql'])

export const INITIAL_RUN_STATE = {
  phase: 'ready',
  sql: '',
  trace: [],
  result: null,
  error: '',
  busy: false,
  context: null,
}

const sensitivePatterns = [
  [/\b(authorization\s*:\s*)?bearer\s+[^\s;,]+/gi, (_, authorization = '') => `${authorization}Bearer [redacted]`],
  [/\b([a-z0-9_]*(?:api_key|access_token|auth_token|secret_key))\s*=\s*[^\s;,]+/gi, '$1=[redacted]'],
  [/\b(api[\s_-]*key)\s*[:=]\s*[^\s;,]+/gi, '$1: [redacted]'],
  [/\b((?:openai|deepseek|dashscope|qwen|anthropic|gemini|groq|mistral)\s+(?:api\s+)?key)\s*[:=]\s*[^\s;,]+/gi, '$1: [redacted]'],
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
    database => String(database.id).toLowerCase() === String(focusedDatabase).toLowerCase()
      || String(database.benchmark || '').toLowerCase() === String(focusedDatabase).toLowerCase(),
  )?.id || ''

const phaseState = (phase, runPhase, failedPhase) => {
  if (!OPERATION_PHASES.has(phase)) return 'neutral'
  const phasePosition = RUN_PHASES.indexOf(phase)
  if (runPhase === 'failed') {
    const failedPosition = RUN_PHASES.indexOf(failedPhase)
    if (phasePosition === failedPosition) return 'failed'
    return phasePosition < failedPosition ? 'completed' : 'pending'
  }
  const runPosition = RUN_PHASES.indexOf(runPhase)
  if (runPhase === 'completed' || phasePosition < runPosition) return 'completed'
  return phasePosition === runPosition ? 'current' : 'pending'
}

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
  credentialMode = 'session',
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
    database: focusedDatabase,
    live_database: databaseId || null,
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

    const context = Object.freeze({
      method: focusedMethod,
      database: focusedDatabase,
      db_id: databaseId,
      config_path: focusedConfig.config_path || null,
      actors: Object.freeze([...actors]),
    })
    setFailedPhase('')
    let current = advance('generatingSql', {
      ...INITIAL_RUN_STATE,
      busy: true,
      context,
    })
    try {
      const generated = await postJson('/api/query', {
        question: question.trim(),
        db_id: context.db_id,
        mode: context.actors.length ? 'workflow' : 'direct',
        actors: context.actors,
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
        db_id: context.db_id,
        sql: generated.sql,
      })
      advance('completed', current, { result: execution, busy: false })
    } catch (error) {
      setFailedPhase(current.phase)
      advance('failed', current, {
        busy: false,
        error: sanitizeRunError(error),
      })
    }
  }

  return <section id="run" className="flow-module flow-glass run-workspace">
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
        {focusedConfig && !databaseId && <p>{t('run.databaseUnavailable')}</p>}
        {!sqlAuth?.configured && <button
          type="button"
          aria-label={t(credentialMode === 'local' ? 'run.configureLocalModelAction' : 'run.configureModelAction')}
          onClick={onConfigureSql}
        >
          {t(credentialMode === 'local' ? 'run.configureLocalModel' : 'run.configureModel')}
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
        const state = phaseState(phase, runState.phase, failedPhase)
        return <li key={phase} data-state={state}>
          <i>{index + 1}</i>
          <span>{t(`run.${phase}`)}</span>
          {state === 'neutral' && <small>{t('run.notApplicable')}</small>}
        </li>
      })}
    </ol>

    {runState.sql && <code className="run-sql">{runState.sql}</code>}
    {runState.error && <p className="error-banner" role="alert">{runState.error}</p>}
  </section>
}
