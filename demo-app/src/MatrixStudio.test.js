import assert from 'node:assert/strict'
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

const baseCapabilities = {
  reproduce_configs: [{
    method: 'c3sql',
    dataset: 'spider',
    config_path: 'reproduce/configs/spider/c3sql.json',
    stages: [{ id: 'generate', type: 'GenerateTask', actor: 'C3SQLGenerator' }],
  }],
}

function renderDemo(locale = 'en-US', capabilities = baseCapabilities) {
  localStorage.setItem('squrve-demo-locale', locale)
  return render(React.createElement(FullFlowDemo, {
    capabilities,
    databases: [],
    sqlAuth: { configured: false },
    api: async () => ({ runs: [] }),
    postJson: async () => ({}),
    onConfigureSql: () => {},
  }))
}

test.afterEach(() => {
  cleanup()
  localStorage.clear()
})

test.after(() => {
  unregister()
  closeDom()
})

test('renders six bilingual modules in process order', () => {
  renderDemo('en-US')
  const headings = screen.getAllByRole('heading', { level: 2 }).map(node => node.textContent)
  assert.deepEqual(headings, [
    'Configuration Studio',
    'Workflow Composition',
    'Run Workspace',
    'Result Inspection',
    'Weakness Diagnosis',
    'Bounded Improvement',
  ])
  assert.deepEqual(
    [...document.querySelectorAll('.flow-module')].map(section => section.id),
    ['configure', 'compose', 'run', 'inspect', 'diagnose', 'improve'],
  )
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
  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))

  assert.equal(screen.getByRole('button', { name: 'Select method C3SQL' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select method DINSQL' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select database Spider' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getByRole('button', { name: 'Select database BIRD' }).getAttribute('aria-pressed'), 'true')
  assert.equal(screen.getAllByRole('button', { name: /^Focus connection / }).length, 4)

  await user.click(screen.getByRole('button', { name: 'Select method C3SQL' }))
  await user.click(screen.getByRole('button', { name: 'Select method DINSQL' }))
  assert.equal(screen.getByRole('button', { name: 'Select method DINSQL' }).getAttribute('aria-pressed'), 'true')
})

test('renders only configuration-backed workflow and provenance', async () => {
  renderDemo()

  assert.ok(screen.getByRole('img', { name: /^Method to database configuration matrix/ }))
  assert.match(screen.getByTestId('focused-configuration').textContent, /reproduce\/configs\/spider\/c3sql\.json/)
  assert.match(screen.getByTestId('actor-workflow').textContent, /C3SQLGenerator/)
  assert.match(screen.getByTestId('actor-workflow').textContent, /GenerateTask/)

  await userEvent.setup().click(screen.getByRole('button', { name: 'Behind this configuration' }))
  const provenance = screen.getByTestId('integration-provenance').textContent
  assert.match(provenance, /reproduce\/configs\/spider\/c3sql\.json/)
  assert.match(provenance, /C3SQLGenerator/)
})

test('does not invent stages for an unavailable connection', async () => {
  renderDemo()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Select database BIRD' }))
  await user.click(screen.getByRole('button', { name: 'Focus connection C3SQL to BIRD' }))

  assert.match(screen.getByTestId('focused-configuration').textContent, /Unavailable/)
  assert.match(screen.getByTestId('actor-workflow').textContent, /No verified workflow/)
  assert.doesNotMatch(screen.getByTestId('actor-workflow').textContent, /Generator/)
})
