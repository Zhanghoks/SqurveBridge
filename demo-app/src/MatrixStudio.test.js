import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
globalThis.React = React
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: window.localStorage,
})
const { cleanup, render, screen } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
registerLoader('./cssTestLoader.mjs', import.meta.url)
const unregister = register()

const { default: FullFlowDemo } = await import('./MatrixStudio.jsx')
const fullFlowCss = readFileSync(
  new URL('./full-flow/full-flow.css', import.meta.url),
  'utf8',
)

const baseCapabilities = {
  reproduce_configs: [{
    method: 'c3sql',
    dataset: 'spider',
    config_path: 'reproduce/configs/spider/c3sql.json',
    stages: [{ id: 'generate', type: 'GenerateTask', actor: 'C3SQLGenerator' }],
  }],
}

function renderDemo(locale = 'en-US', capabilities = baseCapabilities, overrides = {}) {
  localStorage.setItem('squrve-demo-locale', locale)
  window.history.replaceState(null, '', '#configure')
  return render(React.createElement(FullFlowDemo, {
    capabilities,
    databases: [],
    sqlAuth: { configured: false },
    api: async () => ({ runs: [] }),
    postJson: async () => ({}),
    onConfigureSql: () => {},
    ...overrides,
  }))
}

async function goToStep(user, name) {
  await user.click(screen.getByRole('button', { name: `Go to ${name}` }))
}

test.afterEach(() => {
  cleanup()
  localStorage.clear()
  window.history.replaceState(null, '', '#configure')
})

test.after(() => {
  unregister()
  closeDom()
})

test('renders six bilingual modules in process order', () => {
  renderDemo('en-US')
  assert.ok(document.querySelector('.flow-demo'))
  assert.ok(document.querySelector('.flow-process-rail'))
  assert.ok(document.querySelector('.flow-demo-body'))
  assert.equal(document.querySelectorAll('.flow-module').length, 6)
  assert.ok(document.querySelector('.flow-glass'))
  assert.equal(screen.getByTestId('flow-stage').getAttribute('data-active-step'), 'configure')
  assert.deepEqual(
    [...document.querySelectorAll('.flow-module')].map(section => section.id),
    ['configure', 'compose', 'run', 'inspect', 'diagnose', 'improve'],
  )
  assert.equal(screen.getByRole('heading', { level: 2 }).textContent, 'Configuration Studio')
  assert.equal(screen.getAllByRole('button', { name: /^Go to / }).length, 6)
})

test('switches process pages from the left rail', async () => {
  renderDemo()
  const user = userEvent.setup()

  await goToStep(user, 'Compose')
  assert.equal(screen.getByTestId('flow-stage').getAttribute('data-active-step'), 'compose')
  assert.ok(screen.getByRole('heading', { name: 'Workflow Composition' }))
  assert.equal(window.location.hash, '#compose')

  await user.click(screen.getByRole('button', { name: 'Next' }))
  assert.equal(screen.getByTestId('flow-stage').getAttribute('data-active-step'), 'run')
  assert.ok(screen.getByRole('heading', { name: 'Run Workspace' }))

  await goToStep(user, 'Improve')
  assert.equal(screen.getByTestId('flow-stage').getAttribute('data-active-step'), 'improve')
  assert.equal(
    screen.getByRole('button', { name: 'Go to Improve' }).getAttribute('aria-current'),
    'page',
  )
})

test('keeps functional controls and technical metadata readable', () => {
  assert.match(fullFlowCss, /--flow-type-control:\s*12px/)
  assert.match(fullFlowCss, /--flow-type-meta:\s*11px/)
  for (const selector of [
    '.catalog-card-select',
    '.flashcard-tile-open',
    '.flashcard-face section p',
    '.flow-graph-nodes button',
    '.flow-actor-workflow li > span',
    '.run-phase-list li',
    '.result-run-context dt',
  ]) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    assert.match(
      fullFlowCss,
      new RegExp(`${escaped}[^{]*\\{[^}]*var\\(--flow-type-(?:control|meta)\\)`, 's'),
      `${selector} must use the readable type scale`,
    )
  }
})

test('switches to Chinese and persists the locale', async () => {
  renderDemo('en-US')
  await userEvent.setup().click(screen.getByRole('button', { name: '切换到中文' }))
  assert.ok(screen.getByRole('heading', { name: '配置工作台' }))
  assert.equal(localStorage.getItem('squrve-demo-locale'), 'zh-CN')
  assert.equal(document.documentElement.lang, 'zh-CN')
})

test('supports additive method and database selection without clearing the last item', async () => {
  renderDemo()
  const user = userEvent.setup()

  assert.equal(screen.getAllByRole('button', { name: /^Select method / }).length, 8)
  assert.equal(screen.getAllByRole('button', { name: /^Select database / }).length, 8)
  assert.ok(document.querySelector('[data-testid="catalog-workspaces"]'))
  assert.equal(document.querySelectorAll('.catalog-workspace').length, 2)
  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))

  assert.equal(screen.getByRole('button', { name: 'Select method C3SQL' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select method DINSQL' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select database Spider' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select database BIRD' }).getAttribute('aria-pressed'), 'true')
  await goToStep(user, 'Compose')
  assert.equal(screen.getAllByRole('button', { name: /^Focus connection / }).length, 4)

  await goToStep(user, 'Configure')
  await user.click(screen.getByRole('button', { name: 'Select method C3SQL' }))
  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))
  assert.equal(screen.getByRole('button', { name: 'Select method DINSQL' }).getAttribute('aria-pressed'), 'true')
})

test('shows an honest read-only Pi surface on hosted Configure', async () => {
  renderDemo()
  const user = userEvent.setup()

  assert.ok(screen.getByTestId('configure-agent-panel'))
  assert.match(screen.getByTestId('configure-agent-panel').textContent, /Inspect the published SqurveBridge bundle/)
  assert.match(screen.getByTestId('configure-agent-panel').textContent, /cannot fetch or integrate external repositories/)
  assert.match(document.querySelector('#configure').textContent, /published configurations bundled with SqurveBridge/)
  assert.doesNotMatch(screen.getByTestId('configure-agent-panel').textContent, /candidate-reader/)
  assert.ok(screen.getByRole('button', { name: 'Open Pi Agent chat' }))
  assert.match(screen.getByTestId('focused-configuration').textContent, /Compose/)
  assert.equal(document.querySelector('#configure .flow-connection-graph'), null)
  assert.equal(document.querySelector('#configure [data-testid="actor-workflow"]'), null)

  await goToStep(user, 'Compose')
  assert.ok(document.querySelector('#compose .flow-connection-graph'))
  assert.ok(screen.getByTestId('actor-workflow'))
  assert.match(document.querySelector('#compose').textContent, /Method × Database/)
})

test('keeps external integration intake on the trusted local Configure surface', () => {
  renderDemo('en-US', baseCapabilities, { credentialMode: 'local' })

  assert.match(screen.getByTestId('configure-agent-panel').textContent, /Integrate external methods/)
  assert.match(screen.getByTestId('configure-agent-panel').textContent, /candidate-reader/)
  assert.ok(screen.getByLabelText('Candidate GitHub repository'))
})

test('opens method and database flashcards with what, origin, and intro', async () => {
  renderDemo()
  const user = userEvent.setup()

  assert.match(document.querySelector('#configure').textContent, /Three-layer recall/)
  assert.match(document.querySelector('#configure').textContent, /Classic cross-domain/)
  await user.click(screen.getByRole('button', { name: 'Open flashcard for method E-SQL' }))
  const dialog = screen.getByTestId('flashcard-dialog')
  assert.match(dialog.textContent, /What it is/)
  assert.match(dialog.textContent, /Origin/)
  assert.match(dialog.textContent, /Introduction/)
  assert.match(dialog.textContent, /CSG-QE-SR/)
  assert.match(dialog.textContent, /arXiv:2409\.16751/)
  assert.ok(screen.getByRole('link', { name: 'arXiv:2409.16751' }))
  await user.click(screen.getByRole('button', { name: 'Done' }))
  await user.click(screen.getByRole('button', { name: 'Open flashcard for database BIRD' }))
  assert.ok(screen.getByRole('link', { name: 'https://bird-bench.github.io/' }))
  assert.match(screen.getByTestId('flashcard-dialog').textContent, /bird-bench\.github\.io/)
})

test('supports arbitrary graph connections without cartesian expansion', async () => {
  renderDemo()
  const user = userEvent.setup()

  await goToStep(user, 'Compose')
  await user.click(screen.getByRole('button', { name: 'Toggle connection DINSQL to BIRD' }))

  assert.equal(screen.getAllByRole('button', { name: /^Focus connection / }).length, 2)
  assert.ok(screen.getByRole('button', { name: 'Focus connection C3SQL to Spider' }))
  assert.ok(screen.getByRole('button', { name: 'Focus connection DINSQL to BIRD' }))
  assert.equal(
    screen.queryByRole('button', { name: 'Focus connection C3SQL to BIRD' }),
    null,
  )
  assert.equal(
    screen.queryByRole('button', { name: 'Focus connection DINSQL to Spider' }),
    null,
  )
  assert.equal(
    screen.getByRole('button', { name: 'Toggle connection DINSQL to BIRD' }).getAttribute('aria-pressed'),
    'true',
  )
  await goToStep(user, 'Configure')
  assert.match(screen.getByTestId('focused-configuration').textContent, /DINSQL → BIRD/)
  await goToStep(user, 'Compose')
  assert.match(screen.getByTestId('compose-workflow-panel').textContent, /DINSQL → BIRD/)
})

test('switches inspected workflow across multiple selected connections', async () => {
  renderDemo()
  const user = userEvent.setup()

  await goToStep(user, 'Compose')
  await user.click(screen.getByRole('button', { name: 'Toggle connection DINSQL to BIRD' }))
  assert.match(screen.getByTestId('compose-workflow-panel').textContent, /DINSQL → BIRD/)
  assert.match(screen.getByTestId('compose-connection-switcher').textContent, /2 \/ 2/)

  await user.click(screen.getByRole('button', { name: 'Focus connection C3SQL to Spider' }))
  assert.match(screen.getByTestId('compose-workflow-panel').textContent, /C3SQL → Spider/)
  assert.equal(
    screen.getByRole('button', { name: 'Focus connection C3SQL to Spider' }).getAttribute('aria-pressed'),
    'true',
  )
  assert.equal(
    screen.getByRole('button', { name: 'Focus connection DINSQL to BIRD' }).getAttribute('aria-pressed'),
    'false',
  )

  await user.click(screen.getByRole('button', { name: 'Next connection' }))
  assert.match(screen.getByTestId('compose-workflow-panel').textContent, /DINSQL → BIRD/)

  await user.click(screen.getByRole('button', { name: 'Remove connection DINSQL to BIRD' }))
  assert.equal(screen.getAllByRole('button', { name: /^Focus connection / }).length, 1)
  assert.match(screen.getByTestId('compose-workflow-panel').textContent, /C3SQL → Spider/)
})

test('moves method focus to a remaining selected method when removing the focused method', async () => {
  renderDemo('en-US', {
    reproduce_configs: [
      ...baseCapabilities.reproduce_configs,
      {
        method: 'dinsql',
        dataset: 'spider',
        config_path: 'reproduce/configs/spider/dinsql.json',
        stages: [{ id: 'generate', type: 'GenerateTask', actor: 'DINSQLGenerator' }],
      },
    ],
  })
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))
  assert.match(screen.getByTestId('focused-configuration').textContent, /dinsql\.json/)
  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))

  assert.equal(screen.getByRole('button', { name: 'Select method C3SQL' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select method DINSQL' }).getAttribute('aria-pressed'), 'false')
  assert.match(screen.getByTestId('focused-configuration').textContent, /c3sql\.json/)
})

test('moves database focus to a remaining selected database when removing the focused database', async () => {
  renderDemo('en-US', {
    reproduce_configs: [
      ...baseCapabilities.reproduce_configs,
      {
        method: 'c3sql',
        dataset: 'bird',
        config_path: 'reproduce/configs/bird/c3sql.json',
        stages: [{ id: 'generate', type: 'GenerateTask', actor: 'C3SQLGenerator' }],
      },
    ],
  })
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))
  assert.match(screen.getByTestId('focused-configuration').textContent, /bird\/c3sql\.json/)
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))

  assert.equal(screen.getByRole('button', { name: 'Select database Spider' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select database BIRD' }).getAttribute('aria-pressed'), 'false')
  assert.match(screen.getByTestId('focused-configuration').textContent, /spider\/c3sql\.json/)
})

test('renders real run controls while preserving persisted-evidence boundaries', async () => {
  renderDemo('en-US')
  const user = userEvent.setup()

  await goToStep(user, 'Run')
  assert.match(document.querySelector('#run').textContent, /Configuration preview/)
  assert.doesNotMatch(document.querySelector('#run').textContent, /configuration is unavailable/)
  assert.equal(screen.getByRole('button', { name: 'Run workflow' }).disabled, true)
  await goToStep(user, 'Inspect')
  assert.match(document.querySelector('#inspect').textContent, /Run a workflow to inspect its artifacts/)
  assert.equal(screen.queryByTestId('inspect-sample-banner'), null)
  await goToStep(user, 'Diagnose')
  await screen.findByText(/Diagnosis requires a persisted score bundle/)
  assert.match(document.querySelector('#diagnose').textContent, /persisted score bundle/)
  await goToStep(user, 'Improve')
  assert.match(document.querySelector('#improve').textContent, /persisted improvement or weakness-evolution record/)
})

test('translates the process navigation, run controls, and evidence boundaries', async () => {
  renderDemo('en-US')
  assert.ok(screen.getByRole('navigation', { name: 'Text-to-SQL workflow' }))

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '切换到中文' }))

  assert.ok(screen.getByRole('navigation', { name: 'Text-to-SQL 工作流' }))
  await user.click(screen.getByRole('button', { name: '前往运行' }))
  assert.match(document.querySelector('#run').textContent, /配置预览/)
  assert.ok(screen.getByRole('button', { name: '从运行工作台配置 SQL API' }))
  await user.click(screen.getByRole('button', { name: '前往诊断' }))
  assert.match(document.querySelector('#diagnose').textContent, /持久化评分包/)
  await user.click(screen.getByRole('button', { name: '前往改进' }))
  assert.match(document.querySelector('#improve').textContent, /持久化改进记录或弱点演化记录/)
})

test('renders only configuration-backed workflow and provenance', async () => {
  renderDemo()
  const user = userEvent.setup()

  await goToStep(user, 'Compose')
  assert.ok(screen.getByRole('group', { name: /^Method to database configuration matrix/ }))
  await goToStep(user, 'Configure')
  assert.match(screen.getByTestId('focused-configuration').textContent, /reproduce\/configs\/spider\/c3sql\.json/)
  await goToStep(user, 'Compose')
  assert.match(screen.getByTestId('actor-workflow').textContent, /C3SQLGenerator/)
  assert.match(screen.getByTestId('actor-workflow').textContent, /GenerateTask/)

  await user.click(screen.getByRole('button', { name: 'Behind this configuration' }))
  const provenance = screen.getByTestId('integration-provenance').textContent
  assert.match(provenance, /reproduce\/configs\/spider\/c3sql\.json/)
  assert.match(provenance, /C3SQLGenerator/)
})

test('does not invent stages for an unavailable connection', async () => {
  renderDemo()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))
  await goToStep(user, 'Compose')
  await user.click(screen.getByRole('button', { name: 'Focus connection C3SQL to BIRD' }))

  await goToStep(user, 'Configure')
  assert.match(screen.getByTestId('focused-configuration').textContent, /Unavailable/)
  await goToStep(user, 'Compose')
  assert.match(screen.getByTestId('actor-workflow').textContent, /No verified workflow/)
  assert.doesNotMatch(screen.getByTestId('actor-workflow').textContent, /Generator/)
  await goToStep(user, 'Run')
  assert.match(document.querySelector('#run').textContent, /configuration is unavailable/)
  assert.equal(screen.getByRole('button', { name: 'Run workflow' }).disabled, true)
})

test('keeps completed evidence labelled with its immutable run connection after focus changes', async () => {
  const capabilities = {
    reproduce_configs: [
      baseCapabilities.reproduce_configs[0],
      {
        method: 'c3sql',
        dataset: 'bird',
        config_path: 'reproduce/configs/bird/c3sql.json',
        stages: [{ id: 'generate', type: 'GenerateTask', actor: 'C3SQLGenerator' }],
      },
    ],
  }
  const postJson = async path => path === '/api/query'
    ? { sql: 'SELECT sku FROM demo_inventory', trace: [{ actor_name: 'C3SQLGenerator' }] }
    : { columns: ['sku'], rows: [['SKU-001']], row_count: 1, elapsed_ms: 4 }
  renderDemo('en-US', capabilities, {
    databases: [{ id: 'Spider' }, { id: 'BIRD' }],
    sqlAuth: { configured: true, provider: 'openai', model: 'gpt-4.1-mini' },
    postJson,
  })
  const user = userEvent.setup()

  await goToStep(user, 'Run')
  await user.type(screen.getByLabelText('Question'), 'List demo inventory SKUs')
  await user.click(screen.getByRole('button', { name: 'Run workflow' }))
  assert.equal((await screen.findAllByText('SELECT sku FROM demo_inventory')).length, 2)

  await goToStep(user, 'Configure')
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))
  await goToStep(user, 'Compose')
  await user.click(screen.getByRole('button', { name: 'Focus connection C3SQL to BIRD' }))

  await goToStep(user, 'Configure')
  assert.match(screen.getByTestId('focused-configuration').textContent, /bird\/c3sql\.json/)
  await goToStep(user, 'Inspect')
  const context = screen.getByTestId('run-context').textContent
  assert.match(context, /Spider/)
  assert.match(context, /spider\/c3sql\.json/)
  assert.doesNotMatch(context, /bird\/c3sql\.json/)
})
