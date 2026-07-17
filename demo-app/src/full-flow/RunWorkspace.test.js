import assert from 'node:assert/strict'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from '../testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
registerLoader('../cssTestLoader.mjs', import.meta.url)
const unregister = register()

const { default: RunWorkspace, sanitizeRunError } = await import('./RunWorkspace.jsx')
const { default: ResultWorkspace } = await import('./ResultWorkspace.jsx')

const translations = {
  'process.run': 'Run',
  'run.title': 'Run Workspace',
  'run.description': 'Ask a question and execute the composed Text-to-SQL workflow.',
  'run.question': 'Natural-language question',
  'run.questionPlaceholder': 'Ask a question',
  'run.configPreview': 'Configuration preview',
  'run.action': 'Run Reproduce',
  'run.connectModel': 'Connect a model to run',
  'run.configureModel': 'Configure SQL API',
  'run.configureModelAction': 'Configure SQL API from Run Workspace',
  'run.unavailable': 'This configuration is unavailable.',
  'run.databaseUnavailable': 'The focused database is not available in the live runtime.',
  'run.ready': 'Ready to run',
  'run.completed': 'Run completed',
  'run.loadingData': 'Loading data',
  'run.buildingWorkflow': 'Building workflow',
  'run.generatingSql': 'Generating SQL',
  'run.executingSql': 'Executing SQL',
  'run.evaluating': 'Evaluating',
  'run.notApplicable': 'Not applicable',
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
}

const t = key => translations[key] || key

function renderRun(overrides = {}) {
  const props = {
    focusedConfig: {
      method: 'dinsql',
      dataset: 'spider',
      config_path: 'reproduce/configs/spider/dinsql.json',
      stages: [{ id: 'generate', type: 'GenerateTask', actor: 'DINSQLGenerator' }],
    },
    focusedMethod: 'DINSQL',
    focusedDatabase: 'Spider',
    databases: [{ id: 'Spider' }],
    sampleLimit: 20,
    sampleMode: 'slice',
    sampleSeed: 42,
    sqlAuth: { configured: true, provider: 'openai', model: 'gpt-4.1-mini' },
    postJson: async () => ({}),
    onConfigureSql: () => {},
    onRunStateChange: () => {},
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

test('runs query then execute for the focused connection', async () => {
  const calls = []
  const states = []
  const postJson = async (path, body) => {
    calls.push([path, body])
    if (path === '/api/query') {
      return {
        sql: 'SELECT sku FROM demo_inventory',
        trace: [{ actor_name: 'DINSQLGenerator' }],
      }
    }
    return {
      columns: ['sku'],
      rows: [['SKU-001']],
      row_count: 1,
      elapsed_ms: 4,
    }
  }
  renderRun({
    postJson,
    onRunStateChange: state => states.push(state),
  })
  const user = userEvent.setup()

  await user.type(screen.getByLabelText('Natural-language question'), 'List demo inventory SKUs')
  await user.click(screen.getByRole('button', { name: 'Run Reproduce' }))

  assert.deepEqual(calls, [
    ['/api/query', {
      question: 'List demo inventory SKUs',
      db_id: 'Spider',
      mode: 'workflow',
      actors: ['DINSQLGenerator'],
      generator: 'DINSQLGenerator',
      provider: 'openai',
      model: 'gpt-4.1-mini',
    }],
    ['/api/execute', {
      db_id: 'Spider',
      sql: 'SELECT sku FROM demo_inventory',
    }],
  ])
  assert.ok(await screen.findByText('SELECT sku FROM demo_inventory'))
  assert.equal(states.at(-1).phase, 'completed')
  assert.equal(states.at(-1).result.rows[0][0], 'SKU-001')
  assert.deepEqual(states.map(state => state.phase), [
    'generatingSql',
    'executingSql',
    'completed',
  ])
  assert.deepEqual(states.at(-1).context, {
    method: 'DINSQL',
    database: 'Spider',
    db_id: 'Spider',
    config_path: 'reproduce/configs/spider/dinsql.json',
    actors: ['DINSQLGenerator'],
  })
  assert.equal(screen.getByText('Loading data').closest('li').dataset.state, 'neutral')
  assert.equal(screen.getByText('Building workflow').closest('li').dataset.state, 'neutral')
  assert.equal(screen.getByText('Generating SQL').closest('li').dataset.state, 'completed')
  assert.equal(screen.getByText('Executing SQL').closest('li').dataset.state, 'completed')
  assert.equal(screen.getByText('Evaluating').closest('li').dataset.state, 'neutral')
  for (const phase of ['Loading data', 'Building workflow', 'Evaluating']) {
    assert.match(screen.getByText(phase).closest('li').textContent, /Not applicable/)
  }
})

test('uses a benchmark-labelled Spider reference database for the focused Spider config', async () => {
  const calls = []
  renderRun({
    databases: [{ id: 'college_2', benchmark: 'spider' }],
    postJson: async (path, body) => {
      calls.push([path, body])
      return path === '/api/query'
        ? { sql: 'SELECT 1', trace: [] }
        : { columns: ['1'], rows: [[1]], row_count: 1, elapsed_ms: 1 }
    },
  })
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Natural-language question'), 'Count rows')
  await user.click(screen.getByRole('button', { name: 'Run Reproduce' }))

  assert.equal(calls[0][1].db_id, 'college_2')
  assert.equal(calls[1][1].db_id, 'college_2')
})

test('preserves the question and sanitizes a rejected query error', async () => {
  const postJson = async () => {
    throw new Error('Provider rejected api_key=sk-live-secret with Authorization: Bearer sk-live-secret')
  }
  renderRun({ postJson })
  const user = userEvent.setup()
  const question = screen.getByLabelText('Natural-language question')

  await user.type(question, 'Which demo item was added first?')
  await user.click(screen.getByRole('button', { name: 'Run Reproduce' }))

  assert.equal(question.value, 'Which demo item was added first?')
  assert.ok(await screen.findByRole('alert'))
  assert.equal(document.body.textContent.includes('sk-live-secret'), false)
  assert.match(screen.getByRole('alert').textContent, /Provider rejected/)
})

test('sanitizes supported credential forms while preserving benign technical text', () => {
  const error = new Error([
    'API key: api-secret',
    'OPENAI_API_KEY=openai-secret',
    'DEEPSEEK_API_KEY=deepseek-secret',
    'DASHSCOPE_API_KEY=dashscope-secret',
    'Bearer bearer-secret',
    'qwen key: qwen-secret',
    'SQLite syntax error near SELECT at line 4',
  ].join('; '))

  const sanitized = sanitizeRunError(error)

  for (const secret of [
    'api-secret',
    'openai-secret',
    'deepseek-secret',
    'dashscope-secret',
    'bearer-secret',
    'qwen-secret',
  ]) {
    assert.equal(sanitized.includes(secret), false)
  }
  assert.match(sanitized, /SQLite syntax error near SELECT at line 4/)
})

test('marks the actual stage that failed instead of completing later stages', async () => {
  let rejectQuery
  const postJson = () => new Promise((resolve, reject) => {
    void resolve
    rejectQuery = reject
  })
  renderRun({ postJson })
  const user = userEvent.setup()

  await user.type(screen.getByLabelText('Natural-language question'), 'List demo inventory SKUs')
  await user.click(screen.getByRole('button', { name: 'Run Reproduce' }))
  rejectQuery(new Error('Query failed'))

  assert.ok(await screen.findByRole('alert'))
  assert.equal(screen.getByText('Generating SQL').closest('li').dataset.state, 'failed')
  assert.equal(screen.getByText('Executing SQL').closest('li').dataset.state, 'pending')
})

test('disables real execution when the config or SQL session is unavailable', async () => {
  let configured = 0
  const { rerender } = renderRun({
    focusedConfig: null,
    onConfigureSql: () => { configured += 1 },
  })

  assert.equal(screen.getByRole('button', { name: 'Run Reproduce' }).disabled, true)
  assert.match(document.querySelector('#run').textContent, /configuration is unavailable/)

  rerender(React.createElement(RunWorkspace, {
    focusedConfig: {
      method: 'dinsql',
      dataset: 'spider',
      stages: [{ id: 'generate', type: 'GenerateTask', actor: 'DINSQLGenerator' }],
    },
    focusedMethod: 'DINSQL',
    focusedDatabase: 'Spider',
    databases: [{ id: 'Spider' }],
    sampleLimit: 20,
    sampleMode: 'slice',
    sampleSeed: 42,
    sqlAuth: { configured: false },
    postJson: async () => ({}),
    onConfigureSql: () => { configured += 1 },
    onRunStateChange: () => {},
    t,
  }))

  assert.equal(screen.getByRole('button', { name: 'Run Reproduce' }).disabled, true)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Configure SQL API from Run Workspace' }))
  assert.equal(configured, 1)
})

test('disables execution when the focused catalog database has no live database match', async () => {
  renderRun({ databases: [] })

  await userEvent.setup().type(
    screen.getByLabelText('Natural-language question'),
    'List demo inventory SKUs',
  )

  assert.equal(screen.getByRole('button', { name: 'Run Reproduce' }).disabled, true)
  assert.match(document.querySelector('#run').textContent, /not available in the live runtime/)
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

  assert.equal(screen.queryByTestId('inspect-sample-banner'), null)
  assert.match(screen.getByTestId('run-context').textContent, /DINSQL/)
  assert.match(screen.getByTestId('run-context').textContent, /Spider/)
  assert.match(screen.getByTestId('run-context').textContent, /dinsql\.json/)
  assert.match(screen.getByTestId('run-context').textContent, /DINSQLGenerator/)
  for (const tab of screen.getAllByRole('tab')) {
    assert.equal(tab.tabIndex, 0)
  }
  assert.ok(screen.getByText('SELECT sku FROM demo_inventory'))
  await user.click(screen.getByRole('tab', { name: 'Result' }))
  assert.ok(screen.getByRole('cell', { name: 'SKU-001' }))
  await user.click(screen.getByRole('tab', { name: 'Trace' }))
  assert.ok(screen.getByTestId('inspect-trace'))
  assert.equal(screen.getAllByText('DINSQLGenerator').length, 2)
  await user.click(screen.getByRole('tab', { name: 'Metrics' }))
  assert.match(screen.getByTestId('inspect-metrics').textContent, /row_count/)
  assert.match(screen.getByTestId('inspect-metrics').textContent, /elapsed_ms/)
  await user.click(screen.getByRole('tab', { name: 'Logs' }))
  assert.match(document.querySelector('#inspect').textContent, /Evidence is required/)
  assert.doesNotMatch(document.querySelector('#inspect').textContent, /Loading data|Generating SQL|Executing SQL/)
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

  assert.equal(screen.queryByTestId('inspect-sample-banner'), null)
  assert.equal(screen.queryByTestId('run-context'), null)
  assert.match(document.querySelector('#inspect').textContent, /Run a workflow/)
  assert.equal(screen.queryByRole('tab'), null)
})

test('renders duplicate SQL column labels without duplicate React key warnings', async () => {
  const errors = []
  const originalError = console.error
  console.error = (...args) => { errors.push(args.join(' ')) }
  try {
    render(React.createElement(ResultWorkspace, {
      runState: {
        phase: 'completed',
        sql: 'SELECT a.name, b.name FROM a JOIN b',
        trace: [],
        result: {
          columns: ['name', 'name'],
          rows: [['Alice', 'Bob']],
          row_count: 1,
          elapsed_ms: 2,
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
    await userEvent.setup().click(screen.getByRole('tab', { name: 'Result' }))
  } finally {
    console.error = originalError
  }

  assert.equal(screen.getAllByRole('columnheader', { name: 'name' }).length, 2)
  assert.equal(errors.some(message => /same key|unique "key"/i.test(message)), false)
})
