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

const { default: RunWorkspace, sanitizeRunError } = await import('./RunWorkspace.jsx')
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
  'run.action': 'Run config',
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
