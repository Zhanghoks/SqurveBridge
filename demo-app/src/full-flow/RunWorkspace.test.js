import assert from 'node:assert/strict'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from '../testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen, waitFor } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
registerLoader('../cssTestLoader.mjs', import.meta.url)
const unregister = register()

const {
  default: RunWorkspace,
  mergeJobDetail,
  resolveJobArtifact,
  sanitizeRunError,
  summarizeRunProgress,
} = await import('./RunWorkspace.jsx')
const { default: ResultWorkspace } = await import('./ResultWorkspace.jsx')

const translations = {
  'process.run': 'Run',
  'run.title': 'Run Workspace',
  'run.description': 'Run Compose connections through their reproduce config scripts.',
  'run.noConnections': 'No connections yet.',
  'run.composeConnections': 'Compose connections',
  'run.parameters': 'Parameter console',
  'run.configRunUnavailable': 'Config-script runs are available in the local demo only.',
  'run.configCommand': 'Config command',
  'run.activeTarget': 'Active target',
  'run.configPath': 'Config path',
  'run.workflow': 'Workflow',
  'run.batchTargetCount': '{count} Compose connections · max {max}',
  'run.batchJobs': 'Config jobs',
  'run.batchEmpty': 'No config jobs yet.',
  'run.batchLog': 'Selected job log',
  'run.batchLogEmpty': 'Waiting for job output…',
  'run.viewDebugLog': 'View debug log',
  'run.artifactTitle': 'Run artifacts',
  'run.artifactPending': 'Score bundle is not available for this completed job yet.',
  'run.artifactSplit': 'Split',
  'run.artifactSamples': 'Samples',
  'run.artifactTokens': 'Tokens',
  'run.artifactLatency': 'Latency',
  'run.artifactComponentF1': 'Component F1',
  'run.artifactErrorRoots': 'Error roots',
  'run.artifactStages': 'Actor stages',
  'run.artifactEmptySlice': 'No slice evidence in this score bundle.',
  'run.action': 'Run config',
  'run.stop': 'Stop run',
  'run.resume': 'Resume run',
  'run.resumeMeta': 'Resume {count}/{max}',
  'run.resumeCount': 'Resumed {count}×',
  'run.checkpointReady': 'Resumable',
  'run.resumeHint': 'Checkpoint ready · resume {count}/{max} · same as {command}',
  'run.sampleUnit': 'samples',
  'run.samplesStarted': '{count} samples started',
  'run.waiting': 'Waiting to run',
  'run.unavailable': 'This configuration is unavailable.',
  'run.databaseUnavailable': 'The focused database is not available in the live runtime.',
  'configure.sampleLimit': 'Sample limit',
  'configure.sampleMode': 'Sample mode',
  'configure.sampleSeed': 'Sample seed',
  'configure.sampleSlice': 'Dev slice',
  'configure.sampleRandom': 'Random',
  'inspect.title': 'Result Inspection',
  'inspect.description': 'Inspect evidence returned by the current run.',
  'inspect.sql': 'SQL',
  'inspect.result': 'Result',
  'inspect.trace': 'Trace',
  'inspect.metrics': 'Metrics',
  'inspect.logs': 'Logs',
  'inspect.empty': 'Run a workflow to inspect its artifacts.',
  'inspect.evidenceRequired': 'Evidence is required for this view.',
  'inspect.noSql': 'No SQL was returned.',
  'inspect.noResult': 'No execution result was returned.',
  'inspect.noTrace': 'No trace was returned.',
  'inspect.runContext': 'Run context',
  'inspect.question': 'Question',
  'inspect.artifactRef': 'Artifact ref',
  'inspect.contextDatabase': 'Live database',
  'inspect.contextConfig': 'Configuration',
  'inspect.contextActors': 'Actors',
  'status.ready': 'Ready',
  'status.running': 'Running',
  'status.cancelled': 'Cancelled',
  'status.completed': 'Completed',
  'status.failed': 'Failed',
  'status.unavailable': 'Unavailable',
}

const t = (key, params = {}) => Object.entries(params).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
  translations[key] || key,
)

const baseConfig = {
  method: 'dinsql',
  dataset: 'spider',
  config_path: 'reproduce/configs/spider/dinsql.json',
  stages: [{ id: 'generate', type: 'GenerateTask', actor: 'DINSQLGenerator' }],
}

function renderRun(overrides = {}) {
  const props = {
    selectedConnections: [{ method: 'DINSQL', database: 'Spider' }],
    configs: [baseConfig],
    focusedMethod: 'DINSQL',
    focusedDatabase: 'Spider',
    onFocusConnection: () => {},
    databases: [{ id: 'Spider' }],
    sampleLimit: 20,
    sampleMode: 'slice',
    sampleSeed: 42,
    onSampleLimitChange: () => {},
    onSampleModeChange: () => {},
    onSampleSeedChange: () => {},
    postJson: async () => ({}),
    api: async () => ({}),
    onRunStateChange: () => {},
    liveEvaluation: true,
    t,
    ...overrides,
  }
  return render(React.createElement(RunWorkspace, props))
}

test.afterEach(cleanup)

test.after(() => {
  unregister()
  closeDom()
})

test('launches reproduce/run.py through evaluations for one Compose connection', async () => {
  const calls = []
  const states = []
  renderRun({
    postJson: async (path, body) => {
      calls.push([path, body])
      return { job_id: 'job-1', method: 'dinsql', dataset: 'spider', status: 'running' }
    },
    onRunStateChange: state => states.push(state),
  })
  const user = userEvent.setup()

  assert.ok(screen.getByTestId('run-parameter-console'))
  assert.match(screen.getByTestId('run-compose-connections').textContent, /DINSQL→Spider/)
  assert.match(screen.getByTestId('run-config-command').textContent, /reproduce\/run\.py spider dinsql/)
  assert.equal(screen.queryByLabelText('Natural-language question'), null)
  await user.click(screen.getByRole('button', { name: 'Run config' }))

  assert.deepEqual(calls, [[
    '/api/evaluations',
    {
      sample_limit: 20,
      sample_mode: 'slice',
      sample_seed: 42,
      dataset: 'spider',
      method: 'dinsql',
    },
  ]])
  assert.ok(screen.getByTestId('run-batch-monitor'))
  assert.match(screen.getByTestId('run-batch-monitor').textContent, /dinsql \/ spider/)
  assert.equal(states.at(-1).phase, 'evaluating')
  assert.match(states.at(-1).context.command, /reproduce\/run\.py/)
})

test('launches comparisons for multiple Compose connections', async () => {
  const calls = []
  const secondConfig = {
    method: 'c3sql',
    dataset: 'spider',
    config_path: 'reproduce/configs/spider/c3sql.json',
    stages: [{ id: 'generate', type: 'GenerateTask', actor: 'C3SQLGenerator' }],
  }
  renderRun({
    selectedConnections: [
      { method: 'DINSQL', database: 'Spider' },
      { method: 'C3SQL', database: 'Spider' },
    ],
    configs: [baseConfig, secondConfig],
    postJson: async (path, body) => {
      calls.push([path, body])
      return {
        comparison_id: 'cmp-1',
        jobs: [
          { job_id: 'job-1', method: 'dinsql', dataset: 'spider', status: 'running' },
          { job_id: 'job-2', method: 'c3sql', dataset: 'spider', status: 'running' },
        ],
      }
    },
  })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Run config' }))

  assert.equal(calls[0][0], '/api/comparisons')
  assert.deepEqual(calls[0][1].pairs, [
    { dataset: 'spider', method: 'dinsql' },
    { dataset: 'spider', method: 'c3sql' },
  ])
})

test('summarizeRunProgress prefers finished samples and server progress', () => {
  const fromLog = summarizeRunProgress([
    '开始处理样本 dev_0',
    '样本 dev_0 @ c3sql_reduce1',
    '样本 dev_0 @ c3sql_generate1',
    '样本 dev_0 处理完成 (1.0s)',
    '开始处理样本 dev_1',
    '样本 dev_1 @ c3sql_generate1',
  ].join('\n'), { sample_limit: 20, status: 'running' })
  assert.equal(fromLog.completed, 1)
  assert.equal(fromLog.started, 2)
  assert.equal(fromLog.percent, 5)
  assert.equal(fromLog.currentStage, 'c3sql_generate1')

  const fromServer = summarizeRunProgress('truncated tail only', {
    sample_limit: 20,
    status: 'completed',
    progress: {
      current_stage: '评估完成',
      started: 20,
      completed: 20,
      total: 20,
      percent: 100,
    },
  })
  assert.equal(fromServer.percent, 100)
  assert.equal(fromServer.completed, 20)
  assert.equal(fromServer.currentStage, '评估完成')
})

test('resumes a cancelled board job through the reproduce resume endpoint', async () => {
  const calls = []
  let resumed = false
  const cancelledJob = {
    job_id: 'job-resume',
    method: 'dinsql',
    dataset: 'spider',
    status: 'cancelled',
    checkpoint_present: true,
    resumable: true,
    resume_count: 0,
    max_resume_attempts: 2,
    progress: { current_stage: 'c3sql_generate1', started: 8, completed: 8, total: 20, percent: 40 },
  }
  renderRun({
    api: async path => {
      if (path === '/api/session') {
        return { jobs: [cancelledJob] }
      }
      if (path === '/api/evaluations/job-resume') {
        if (!resumed) {
          return { ...cancelledJob, log: 'checkpoint ready' }
        }
        return {
          ...cancelledJob,
          status: 'running',
          resumable: false,
          resume_count: 1,
          log: '[demo] manual resume 1/2',
          progress: { current_stage: 'c3sql_generate1', started: 8, completed: 8, total: 20, percent: 40 },
        }
      }
      return {}
    },
    postJson: async (path, body) => {
      calls.push([path, body])
      resumed = true
      return {
        job_id: 'job-resume',
        method: 'dinsql',
        dataset: 'spider',
        status: 'running',
        checkpoint_present: true,
        resumable: false,
        resume_count: 1,
        max_resume_attempts: 2,
        resume_mode: 'manual',
      }
    },
  })

  const resume = await screen.findByTestId('run-resume-action')
  await waitFor(() => assert.equal(resume.disabled, false))
  assert.match(screen.getByTestId('run-config-command').textContent, /--resume/)
  await userEvent.setup().click(resume)

  assert.deepEqual(calls, [['/api/evaluations/job-resume/resume', {}]])
  await waitFor(() => assert.match(screen.getByTestId('run-batch-monitor').textContent, /running/i))
})

test('stops active board jobs through the cancel endpoint', async () => {
  const calls = []
  let cancelled = false
  renderRun({
    api: async path => {
      if (path === '/api/session') {
        return {
          jobs: [{
            job_id: 'job-stop',
            method: 'dinsql',
            dataset: 'spider',
            status: 'running',
            progress: { current_stage: 'c3sql_parse1', started: 4, completed: 2, total: 20, percent: 10 },
          }],
        }
      }
      if (path === '/api/evaluations/job-stop') {
        return {
          job_id: 'job-stop',
          method: 'dinsql',
          dataset: 'spider',
          status: cancelled ? 'cancelled' : 'running',
          log: cancelled ? 'cancelled by user' : 'running…',
          progress: {
            current_stage: cancelled ? '评估完成' : 'c3sql_parse1',
            started: cancelled ? 4 : 4,
            completed: cancelled ? 4 : 2,
            total: 20,
            percent: cancelled ? 20 : 10,
          },
        }
      }
      return {}
    },
    postJson: async (path, body) => {
      calls.push([path, body])
      cancelled = true
      return {
        job_id: 'job-stop',
        method: 'dinsql',
        dataset: 'spider',
        status: 'cancelled',
      }
    },
  })

  const stop = await screen.findByTestId('run-stop-action')
  await waitFor(() => assert.equal(stop.disabled, false))
  await userEvent.setup().click(stop)

  assert.deepEqual(calls, [['/api/evaluations/job-stop/cancel', {}]])
  await waitFor(() => assert.match(screen.getByTestId('run-batch-monitor').textContent, /cancelled/i))
})

test('visualizes completed job score-bundle artifacts in the run monitor', async () => {
  renderRun({
    api: async path => {
      if (path === '/api/session') {
        return {
          jobs: [{
            job_id: 'job-done',
            method: 'c3sql',
            dataset: 'spider',
            status: 'completed',
            progress: { current_stage: '评估完成', started: 20, completed: 20, total: 20, percent: 100 },
            result: {
              run_id: 'spider-c3sql-job-done',
              method: 'c3sql',
              dataset: 'spider',
              split: 'dev',
              sample_count: 20,
              metrics: { ex: 0.9, em: 0.85, sf1: 0.88, ves: 0.7, rves: 0.65 },
              component_f1: { select: 0.92, where: 0.8 },
              error_roots: [{ name: 'schema_link', count: 3, rate: 0.15 }],
              token: { total_tokens: 12000, avg_per_sample: 600 },
              stages: [{ name: 'generate', task_type: 'GenerateTask' }],
            },
            artifact: {
              run_id: 'spider-c3sql-job-done',
              artifact_ref: 'session:spider-c3sql-job-done/scores.json',
              latency: { mean_s: 1.25 },
            },
          }],
        }
      }
      if (path === '/api/evaluations/job-done') {
        return {
          job_id: 'job-done',
          method: 'c3sql',
          dataset: 'spider',
          status: 'completed',
          log: '评估完成',
          progress: { current_stage: '评估完成', started: 20, completed: 20, total: 20, percent: 100 },
          result: {
            run_id: 'spider-c3sql-job-done',
            method: 'c3sql',
            dataset: 'spider',
            split: 'dev',
            sample_count: 20,
            metrics: { ex: 0.9, em: 0.85, sf1: 0.88, ves: 0.7, rves: 0.65 },
            component_f1: { select: 0.92, where: 0.8 },
            error_roots: [{ name: 'schema_link', count: 3, rate: 0.15 }],
            token: { total_tokens: 12000 },
            stages: [{ name: 'generate', task_type: 'GenerateTask' }],
          },
          artifact: {
            run_id: 'spider-c3sql-job-done',
            artifact_ref: 'session:spider-c3sql-job-done/scores.json',
            latency: { mean_s: 1.25 },
          },
        }
      }
      return {}
    },
  })

  const panel = await screen.findByTestId('run-artifact-panel')
  assert.match(panel.textContent, /90\.0%/)
  assert.match(panel.textContent, /Component F1/)
  assert.match(panel.textContent, /schema_link/)
  assert.match(panel.textContent, /session:spider-c3sql-job-done\/scores\.json/)
})

test('resolveJobArtifact maps summary metrics for visualization', () => {
  const resolved = resolveJobArtifact({
    job_id: 'x',
    result: {
      metrics: { ex: 0.5 },
      component_f1: { select: 0.7 },
      error_roots: [],
      token: { total_tokens: 10 },
      stages: [],
    },
  })
  assert.equal(resolved.metricCards.find(item => item.key === 'ex').value, 0.5)
  assert.equal(resolved.componentF1[0].name, 'select')
})

test('mergeJobDetail keeps terminal status and preserves newer artifacts', () => {
  const merged = mergeJobDetail(
    {
      job_id: 'job-1',
      status: 'completed',
      progress: { percent: 100 },
      result: { metrics: { ex: 0.9 } },
      artifact: { run_id: 'done' },
      resumable: false,
    },
    {
      job_id: 'job-1',
      status: 'running',
      progress: { percent: 40 },
      log: 'stale log should not be merged into job state',
      log_path: '/Users/example/secret/run.log',
      resumable: false,
    },
  )
  assert.equal(merged.status, 'completed')
  assert.equal(merged.progress.percent, 100)
  assert.equal(merged.result.metrics.ex, 0.9)
  assert.equal(merged.artifact.run_id, 'done')
  assert.equal(merged.log, undefined)
  assert.equal(merged.log_path, undefined)
})

test('restores supervised jobs from the backend session after a page reload', async () => {
  const calls = []
  renderRun({
    api: async path => {
      calls.push(path)
      if (path === '/api/session') {
        return {
          jobs: [{
            job_id: 'resumed-job',
            method: 'dinsql',
            dataset: 'spider',
            status: 'resuming',
            resume_count: 1,
            max_resume_attempts: 2,
          }],
        }
      }
      return { log: '[demo] autonomous resume 1/2' }
    },
  })

  assert.match((await screen.findByTestId('run-batch-monitor')).textContent, /dinsql \/ spider/)
  assert.ok(calls.includes('/api/session'))
  await waitFor(() => assert.ok(calls.includes('/api/evaluations/resumed-job')))
})

test('disables config runs when live_evaluation is unavailable', () => {
  renderRun({ liveEvaluation: false })
  assert.equal(screen.getByRole('button', { name: 'Run config' }).disabled, true)
  assert.match(document.querySelector('#run').textContent, /local demo only/)
})

test('runs config without requiring a connected model', () => {
  renderRun()
  assert.equal(screen.queryByRole('button', { name: /Configure SQL API|Configure LLM/ }), null)
  assert.doesNotMatch(document.querySelector('#run').textContent, /\bModel\b/)
  assert.equal(screen.getByRole('button', { name: 'Run config' }).disabled, false)
})

test('disables config runs when the focused configuration is missing', () => {
  renderRun({ configs: [] })
  assert.equal(screen.getByRole('button', { name: 'Run config' }).disabled, true)
  assert.match(document.querySelector('#run').textContent, /configuration is unavailable/)
})

test('sanitizes a rejected config-run error without exposing secrets', async () => {
  renderRun({
    postJson: async () => {
      throw new Error('Provider rejected api_key=sk-live-secret with Authorization: Bearer sk-live-secret')
    },
  })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Run config' }))
  assert.ok(await screen.findByRole('alert'))
  assert.equal(document.body.textContent.includes('sk-live-secret'), false)
})

test('sanitizes supported credential forms while preserving benign technical text', () => {
  const sanitized = sanitizeRunError(new Error([
    'API key: api-secret',
    'OPENAI_API_KEY=openai-secret',
    'Bearer bearer-secret',
    'password=pw-secret',
    'client_secret=oauth-secret',
    'sk_test_51LeakTokenValue',
    'SQLite syntax error near SELECT at line 4',
  ].join('; ')))
  assert.equal(sanitized.includes('api-secret'), false)
  assert.equal(sanitized.includes('bearer-secret'), false)
  assert.equal(sanitized.includes('pw-secret'), false)
  assert.equal(sanitized.includes('oauth-secret'), false)
  assert.equal(sanitized.includes('sk_test_51LeakTokenValue'), false)
  assert.match(sanitized, /SQLite syntax error near SELECT at line 4/)
})

test('result tabs show only returned evidence and keep metrics and logs empty', async () => {
  render(React.createElement(ResultWorkspace, {
    runState: {
      phase: 'completed',
      sql: 'SELECT sku FROM demo_inventory',
      trace: [{ actor_name: 'DINSQLGenerator' }],
      result: {
        columns: ['sku'],
        rows: [['SKU-001']],
        row_count: 1,
        elapsed_ms: 4,
      },
      error: '',
      busy: false,
      context: {
        method: 'DINSQL',
        database: 'Spider',
        db_id: 'Spider',
        config_path: 'reproduce/configs/spider/dinsql.json',
        actors: ['DINSQLGenerator'],
      },
    },
    t,
  }))
  const user = userEvent.setup()
  assert.ok(screen.getByText('SELECT sku FROM demo_inventory'))
  await user.click(screen.getByRole('tab', { name: 'Result' }))
  assert.ok(screen.getByRole('cell', { name: 'SKU-001' }))
})

test('keeps inspection empty before a live run', () => {
  render(React.createElement(ResultWorkspace, {
    runState: {
      phase: 'ready',
      sql: '',
      trace: [],
      result: null,
      error: '',
      busy: false,
      context: null,
    },
    t,
  }))
  assert.match(document.querySelector('#inspect').textContent, /Run a workflow/)
})
