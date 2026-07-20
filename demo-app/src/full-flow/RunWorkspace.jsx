import { useEffect, useMemo, useState } from 'react'
import {
  configKey,
  connectionKeyOf,
  resolveFocusedConfig,
  withConnectionKeys,
} from './model.js'

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

const SAMPLE_LIMITS = [3, 10, 20, 50, 100, 200]
const MAX_BATCH_TARGETS = 6

export const INITIAL_RUN_STATE = {
  phase: 'ready',
  sql: '',
  trace: [],
  result: null,
  error: '',
  busy: false,
  context: null,
}

export function summarizeRunProgress(log, job) {
  // Prefer server progress computed from the full run.log (UI log is a truncated tail).
  const server = job?.progress
  if (server && typeof server.percent === 'number') {
    return {
      currentStage: server.current_stage || '准备中',
      started: Number(server.started) || 0,
      completed: Number(server.completed) || 0,
      total: Number(server.total) || 1,
      percent: Math.min(100, Math.max(0, Number(server.percent) || 0)),
    }
  }

  const text = String(log || '')
  const target = Number(job?.sample_limit) || 0
  const started = new Set([...text.matchAll(/开始处理样本\s+(\S+)/g)].map(match => match[1]))
  const finished = new Set([...text.matchAll(/样本\s+(\S+)\s+处理完成/g)].map(match => match[1]))
  const stageHits = [...text.matchAll(/样本\s+(\S+)\s+@\s+(\S+)/g)]
  for (const match of stageHits) started.add(match[1])
  let currentStage = stageHits.at(-1)?.[2] || '准备中'
  const reportMatch = text.match(/评估结果[^\n]*\n\s*样本\s+(\d+)\s*条/)
  const reportTotal = reportMatch ? Number(reportMatch[1]) : 0
  if (reportTotal) currentStage = '评估完成'

  const total = target || reportTotal || Math.max(started.size, finished.size, 1)
  let completed = finished.size
  if (job?.status === 'completed' || reportTotal) {
    completed = Math.max(completed, reportTotal || total)
    if (job?.status === 'completed') currentStage = '评估完成'
  }
  completed = Math.min(completed, total)
  const startedCount = Math.max(started.size, completed)
  const percent = job?.status === 'completed'
    ? 100
    : Math.min(100, Math.round((completed / total) * 100))
  return { currentStage, started: startedCount, completed, total, percent }
}

const sensitivePatterns = [
  [/\b(authorization\s*:\s*)?bearer\s+[^\s;,]+/gi, (_, authorization = '') => `${authorization}Bearer [redacted]`],
  [/\b([a-z0-9_]*(?:api_key|access_token|auth_token|secret_key|client_secret|password))\s*=\s*[^\s;,]+/gi, '$1=[redacted]'],
  [/\b(api[\s_-]*key)\s*[:=]\s*[^\s;,]+/gi, '$1: [redacted]'],
  [/\b((?:openai|deepseek|dashscope|qwen|anthropic|gemini|groq|mistral)\s+(?:api\s+)?key)\s*[:=]\s*[^\s;,]+/gi, '$1: [redacted]'],
  [/\b(?:sk[_-]?live[_-]?|sk[_-]?test[_-]?|sk-|hf_|ghp_|github_pat_|AIza)[A-Za-z0-9_-]{6,}\b/g, '[redacted]'],
]

export function sanitizeRunError(error) {
  const fallback = 'Request failed'
  return sensitivePatterns.reduce(
    (message, [pattern, replacement]) => message.replace(pattern, replacement),
    String(error?.message || fallback),
  )
}

export const databaseIdFor = (databases, focusedDatabase) =>
  (databases || []).find(
    database => String(database.id).toLowerCase() === String(focusedDatabase).toLowerCase()
      || String(database.benchmark || '').toLowerCase() === String(focusedDatabase).toLowerCase(),
  )?.id || ''

const actorNames = config => (config?.stages || [])
  .map(stage => stage.actor)
  .filter(Boolean)

const jobTone = status => {
  if (status === 'completed') return 'completed'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  if (status === 'running' || status === 'resuming' || status === 'starting') return 'current'
  return 'pending'
}

const isActiveJob = job => ['running', 'resuming', 'starting'].includes(job?.status)

export const isResumableJob = job => Boolean(
  job?.resumable
  || (['failed', 'cancelled'].includes(job?.status) && job?.checkpoint_present),
)

const phaseFromJobs = jobs => {
  if (!jobs.length) return 'ready'
  if (jobs.some(isActiveJob)) return 'evaluating'
  if (jobs.some(job => job.status === 'failed' || job.status === 'cancelled')) return 'failed'
  if (jobs.every(job => job.status === 'completed')) return 'completed'
  return 'ready'
}

const reproduceCommand = (dataset, method, { resume = false } = {}) => (
  resume
    ? `python reproduce/run.py ${dataset} ${method} --resume`
    : `python reproduce/run.py ${dataset} ${method}`
)

const jobResumeLabel = (job, t) => {
  const count = Number(job?.resume_count) || 0
  const max = Number(job?.max_resume_attempts)
  if (!count && !job?.checkpoint_present && !job?.resumable) return ''
  if (Number.isFinite(max) && max >= 0) {
    return t('run.resumeMeta', { count, max })
  }
  return t('run.resumeCount', { count })
}

function describeTarget(connection, configs, databases) {
  const config = resolveFocusedConfig(configs, connection.method, connection.database)
  const liveId = databaseIdFor(databases, connection.database)
  return {
    ...connection,
    key: connection.key || connectionKeyOf(connection),
    config,
    liveId,
    configBacked: Boolean(config),
    runnable: Boolean(config),
  }
}

export default function RunWorkspace({
  selectedConnections = [],
  configs = [],
  focusedMethod,
  focusedDatabase,
  onFocusConnection,
  databases,
  sampleLimit,
  sampleMode,
  sampleSeed,
  onSampleLimitChange,
  onSampleModeChange,
  onSampleSeedChange,
  postJson,
  api,
  onRunStateChange,
  liveEvaluation = false,
  compact = false,
  t,
}) {
  const connections = useMemo(
    () => withConnectionKeys(selectedConnections).map(item => describeTarget(item, configs, databases)),
    [selectedConnections, configs, databases],
  )
  const focusedKey = configKey(focusedMethod, focusedDatabase)

  const [jobs, setJobs] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selectedJobId, setSelectedJobId] = useState('')
  const [log, setLog] = useState('')
  const progress = summarizeRunProgress(log, jobs.find(job => job.job_id === selectedJobId))

  const primaryTarget = connections.find(item => item.key === focusedKey)
    || connections[0]
    || null
  const runTargets = connections
    .filter(item => item.runnable)
    .slice(0, MAX_BATCH_TARGETS)
  const primaryConfig = primaryTarget?.config || null
  const actors = useMemo(() => actorNames(primaryConfig), [primaryConfig])
  const selectedJob = jobs.find(job => job.job_id === selectedJobId) || null
  const resumableJobs = jobs.filter(isResumableJob)
  const commandPreview = (() => {
    if (selectedJob && isResumableJob(selectedJob)) {
      return reproduceCommand(selectedJob.dataset, selectedJob.method, { resume: true })
    }
    if (runTargets.length === 1) {
      return reproduceCommand(runTargets[0].config.dataset, runTargets[0].config.method)
    }
    if (runTargets.length > 1) {
      return `python reproduce/run.py <dataset> <method> × ${runTargets.length}`
    }
    return 'python reproduce/run.py <dataset> <method>'
  })()

  const publishRunState = (phase, additions = {}) => {
    const context = primaryTarget
      ? Object.freeze({
        method: primaryTarget.method,
        database: primaryTarget.database,
        db_id: primaryTarget.liveId || null,
        config_path: primaryConfig?.config_path || null,
        actors: Object.freeze([...actors]),
        command: commandPreview,
      })
      : null
    onRunStateChange?.({
      ...INITIAL_RUN_STATE,
      phase,
      busy: phase === 'evaluating' || busy,
      context,
      error: additions.error || '',
      ...additions,
    })
  }

  const activeJobs = jobs.filter(isActiveJob)
  const runnable = Boolean(
    liveEvaluation
    && runTargets.length >= 1
    && !busy
    && !activeJobs.length,
  )
  const canResume = Boolean(liveEvaluation && resumableJobs.length && !busy && !activeJobs.length)

  const refreshJobs = async current => {
    if (!api || !current.length) return current
    return Promise.all(current.map(async job => {
      try {
        return await api(`/api/evaluations/${job.job_id}`)
      } catch {
        return job
      }
    }))
  }

  useEffect(() => {
    if (!api) return undefined
    let active = true
    api('/api/session').then(data => {
      if (!active) return
      const restored = Array.isArray(data?.jobs) ? data.jobs : []
      setJobs(restored)
      setSelectedJobId(current => current || restored[0]?.job_id || '')
      if (restored.length) publishRunState(phaseFromJobs(restored))
    }).catch(() => {})
    return () => { active = false }
  }, [api])

  useEffect(() => {
    if (!jobs.some(isActiveJob) || !api) return undefined
    let active = true
    const timer = setInterval(() => {
      refreshJobs(jobs).then(next => {
        if (!active) return
        setJobs(next)
        publishRunState(phaseFromJobs(next))
      }).catch(() => {})
    }, 2500)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [jobs, api])

  useEffect(() => {
    if (!api || !selectedJobId) {
      setLog('')
      return undefined
    }
    let active = true
    api(`/api/evaluations/${selectedJobId}`).then(detail => {
      if (!active) return
      setLog(detail.log || '')
      setJobs(current => current.map(job => (
        job.job_id === selectedJobId
          ? {
            ...job,
            status: detail.status ?? job.status,
            progress: detail.progress ?? job.progress,
            log: detail.log ?? job.log,
            checkpoint_present: detail.checkpoint_present ?? job.checkpoint_present,
            resumable: detail.resumable ?? job.resumable,
            resume_count: detail.resume_count ?? job.resume_count,
          }
          : job
      )))
    }).catch(err => {
      if (active) setLog(sanitizeRunError(err))
    })
    return () => { active = false }
  }, [api, selectedJobId])

  useEffect(() => {
    const selected = jobs.find(job => job.job_id === selectedJobId)
    if (selected?.log) setLog(selected.log)
  }, [jobs, selectedJobId])

  const runConfigs = async () => {
    if (!runnable) return
    setBusy(true)
    setError('')
    publishRunState('evaluating')
    try {
      const pairs = runTargets.map(item => ({
        dataset: item.config.dataset,
        method: item.config.method,
      }))
      const payload = {
        sample_limit: sampleLimit,
        sample_mode: sampleMode,
        sample_seed: sampleSeed,
      }
      let nextJobs = []
      if (pairs.length === 1) {
        const job = await postJson('/api/evaluations', {
          ...payload,
          dataset: pairs[0].dataset,
          method: pairs[0].method,
        })
        nextJobs = [job]
      } else {
        const data = await postJson('/api/comparisons', {
          ...payload,
          pairs,
        })
        nextJobs = Array.isArray(data.jobs) ? data.jobs : []
      }
      setJobs(nextJobs)
      setSelectedJobId(nextJobs[0]?.job_id || '')
      onFocusConnection?.(runTargets[0].method, runTargets[0].database)
      publishRunState(phaseFromJobs(nextJobs))
    } catch (err) {
      const message = sanitizeRunError(err)
      setError(message)
      publishRunState('failed', { error: message })
    } finally {
      setBusy(false)
    }
  }

  const stopRuns = async () => {
    if (!postJson || !activeJobs.length) return
    setBusy(true)
    setError('')
    try {
      await Promise.all(activeJobs.map(job => postJson(`/api/evaluations/${job.job_id}/cancel`, {})))
      const next = await refreshJobs(jobs)
      setJobs(next)
      publishRunState(phaseFromJobs(next))
    } catch (err) {
      const message = sanitizeRunError(err)
      setError(message)
      publishRunState('failed', { error: message })
    } finally {
      setBusy(false)
    }
  }

  const resumeRuns = async () => {
    if (!postJson || !resumableJobs.length) return
    const targets = selectedJob && isResumableJob(selectedJob)
      ? [selectedJob]
      : resumableJobs
    setBusy(true)
    setError('')
    publishRunState('evaluating')
    try {
      const resumed = await Promise.all(
        targets.map(job => postJson(`/api/evaluations/${job.job_id}/resume`, {})),
      )
      const byId = new Map(resumed.map(job => [job.job_id, job]))
      const next = jobs.map(job => byId.get(job.job_id) || job)
      setJobs(next)
      setSelectedJobId(resumed[0]?.job_id || selectedJobId)
      publishRunState(phaseFromJobs(next))
    } catch (err) {
      const message = sanitizeRunError(err)
      setError(message)
      publishRunState('failed', { error: message })
    } finally {
      setBusy(false)
    }
  }

  const statusLabel = () => {
    if (busy || jobs.some(isActiveJob)) return t('status.running')
    if (jobs.some(job => job.status === 'cancelled') && !jobs.some(job => job.status === 'failed')) {
      return t('status.cancelled')
    }
    if (jobs.some(job => job.status === 'failed')) return t('status.failed')
    if (jobs.length && jobs.every(job => job.status === 'completed')) return t('status.completed')
    return t('status.ready')
  }

  const Shell = compact ? 'div' : 'section'
  return <Shell id={compact ? undefined : 'run'} className={compact ? 'board-section run-workspace' : 'flow-module flow-glass run-workspace'}>
    <header className={compact ? 'board-section-header' : 'flow-module-header'}>
      <div>
        {!compact && <span>{t('process.run')}</span>}
        {compact ? <h3>{t('board.runSection')}</h3> : <h2>{t('run.title')}</h2>}
        {!compact && <p>{t('run.description')}</p>}
      </div>
      <strong>{statusLabel()}</strong>
    </header>

    <div className="run-workspace-layout">
      <section className="run-parameter-console" data-testid="run-parameter-console" aria-labelledby="run-params-title">
        <header>
          <h3 id="run-params-title">{t('run.parameters')}</h3>
        </header>

        {!connections.length && <p className="run-empty">{t('run.noConnections')}</p>}
        {!liveEvaluation && <p className="run-batch-note">{t('run.configRunUnavailable')}</p>}

        <dl className="run-param-summary">
          <div>
            <dt>{t('run.activeTarget')}</dt>
            <dd>{primaryTarget ? `${primaryTarget.method} → ${primaryTarget.database}` : t('status.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('run.composeConnections')}</dt>
            <dd data-testid="run-compose-connections">
              {connections.length
                ? connections.map(item => `${item.method}→${item.database}`).join(', ')
                : t('status.unavailable')}
            </dd>
          </div>
          <div>
            <dt>{t('run.configPath')}</dt>
            <dd>{primaryConfig?.config_path || t('status.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('run.workflow')}</dt>
            <dd>{actors.length ? actors.join(' → ') : t('status.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('run.configCommand')}</dt>
            <dd data-testid="run-config-command"><code>{commandPreview}</code></dd>
          </div>
        </dl>

        <div className="run-batch-params" data-testid="run-config-sampling">
          <div className="run-sampling-fields">
            <label>
              <span>{t('configure.sampleLimit')}</span>
              <select
                value={sampleLimit}
                onChange={event => onSampleLimitChange?.(Number(event.target.value))}
              >
                {SAMPLE_LIMITS.map(limit => (
                  <option key={limit} value={limit}>{limit}</option>
                ))}
              </select>
            </label>
            <label>
              <span>{t('configure.sampleMode')}</span>
              <select
                value={sampleMode}
                onChange={event => onSampleModeChange?.(event.target.value)}
              >
                <option value="slice">{t('configure.sampleSlice')}</option>
                <option value="random">{t('configure.sampleRandom')}</option>
              </select>
            </label>
            <label>
              <span>{t('configure.sampleSeed')}</span>
              <input
                type="number"
                value={sampleSeed}
                onChange={event => onSampleSeedChange?.(Number(event.target.value))}
              />
            </label>
          </div>
          <p>{t('run.batchTargetCount', { count: runTargets.length, max: MAX_BATCH_TARGETS })}</p>
          {!primaryConfig && <p>{t('run.unavailable')}</p>}
        </div>

        <div className="run-action-bar">
          <button
            type="button"
            className="run-primary-action"
            disabled={!runnable}
            onClick={runConfigs}
          >
            {t('run.action')}
          </button>
          <button
            type="button"
            className="run-resume-action"
            data-testid="run-resume-action"
            disabled={!canResume}
            onClick={resumeRuns}
          >
            {t('run.resume')}
          </button>
          <button
            type="button"
            className="run-stop-action"
            data-testid="run-stop-action"
            disabled={!liveEvaluation || !activeJobs.length || busy}
            onClick={stopRuns}
          >
            {t('run.stop')}
          </button>
        </div>
      </section>
    </div>

    <div className="run-batch-monitor" data-testid="run-batch-monitor">
      <div className="run-batch-jobs">
        <h3>{t('run.batchJobs')}</h3>
        {!jobs.length
          ? <p className="run-empty">{t('run.batchEmpty')}</p>
          : <ul>
            {jobs.map(job => (
              <li key={job.job_id} data-state={jobTone(job.status)}>
                <button
                  type="button"
                  className={selectedJobId === job.job_id ? 'active' : ''}
                  onClick={() => setSelectedJobId(job.job_id)}
                >
                  <strong>{job.method} / {job.dataset}</strong>
                  <span>{job.status}</span>
                  {jobResumeLabel(job, t) && <small>{jobResumeLabel(job, t)}</small>}
                  {isResumableJob(job) && <em>{t('run.checkpointReady')}</em>}
                </button>
              </li>
            ))}
          </ul>}
      </div>
      <div className="run-progress-card">
        <div className="run-progress-heading">
          <div><strong>{progress.percent}%</strong><span>{progress.currentStage}</span></div>
          <small>{progress.completed} / {progress.total} {t('run.sampleUnit')}</small>
        </div>
        <div className="run-progress-track" role="progressbar" aria-valuenow={progress.percent} aria-valuemin="0" aria-valuemax="100">
          <span style={{ width: `${progress.percent}%` }} />
        </div>
        <div className="run-progress-meta">
          <span>{t('run.samplesStarted', { count: progress.started })}</span>
          <span>{selectedJob?.status || t('run.waiting')}</span>
        </div>
        {selectedJob && (selectedJob.checkpoint_present || selectedJob.resume_count > 0) && (
          <p className="run-resume-note" data-testid="run-resume-note">
            {t('run.resumeHint', {
              count: Number(selectedJob.resume_count) || 0,
              max: Number(selectedJob.max_resume_attempts) || 0,
              command: reproduceCommand(selectedJob.dataset, selectedJob.method, { resume: true }),
            })}
          </p>
        )}
        <details className="run-log-details">
          <summary>查看调试日志</summary>
          <pre className="run-batch-log" aria-label={t('run.batchLog')}>{log || t('run.batchLogEmpty')}</pre>
        </details>
      </div>
    </div>

    {error && <p className="error-banner" role="alert">{error}</p>}
  </Shell>
}
