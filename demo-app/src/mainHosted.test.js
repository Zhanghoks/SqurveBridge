import test from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen, waitFor } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
registerLoader('./cssTestLoader.mjs', import.meta.url)
const unregister = register()

test.afterEach(() => cleanup())
test.after(() => {
  unregister()
  closeDom()
})

test('hosted App exposes session SQL configuration instead of local env configuration', async () => {
  const providers = [{ id: 'qwen', models: ['qwen-plus'], default_model: 'qwen-plus' }]
  const methods = ['C3SQL', 'DINSQL', 'FinSQL', 'RESDSQL', 'E-SQL', 'SEDE', 'UNISAR', 'GPT Baseline']
  const datasets = ['Spider', 'BIRD', 'BookSQL', 'BULL-EN', 'BULL-CN', 'EHRSQL-2024', 'AmbiDB', 'Spider2']
  const configs = methods.flatMap(method => datasets.map(dataset => ({
    method,
    dataset,
    split: 'dev',
    stages: [{ id: 'generate', type: 'GenerateTask', actor: `${method.replaceAll(/[^A-Za-z0-9]/g, '')}Generator` }],
  })))
  const responses = {
    '/api/health': { status: 'ok', provider: { configured: false, ready: false } },
    '/api/capabilities': {
      llm_providers: providers,
      actors: {},
      workflows: [[]],
      reproduce_configs: configs,
      deployment: {
        target: 'hf-space',
        features: {
          live_sql: true,
          session_sql_auth: true,
          provider_configuration: false,
          agent_chat: false,
          live_evaluation: false,
        },
      },
    },
    '/api/databases': { databases: datasets.map(id => ({ id, tables: [] })) },
    '/api/sql-auth': { status: 'ok', configured: false, providers },
    '/api/comparisons/latest/results': { runs: [] },
    '/api/archive': { runs: [] },
  }
  const requested = []
  globalThis.fetch = async path => {
    requested.push(path)
    return {
      ok: true,
      statusText: 'OK',
      json: async () => responses[path],
    }
  }
  let appElement
  globalThis.__SQURVE_DEMO_ROOT__ = { render: element => { appElement = element } }
  await import(`./main.jsx?hosted-test=${Date.now()}`)
  render(React.createElement(appElement.type))

  const configure = await screen.findByRole('button', { name: 'Configure SQL API' })
  assert.equal(screen.queryByRole('button', { name: 'Configure LLM' }), null)
  assert.match(document.body.textContent, /Bring your own SQL model credential/i)
  for (const title of [
    'Configuration Studio',
    'Workflow Composition',
    'Run Workspace',
    'Result Inspection',
    'Weakness Diagnosis',
    'Bounded Improvement',
  ]) {
    assert.ok(screen.getByRole('heading', { name: title }))
  }
  assert.match(document.body.textContent, /64 runnable configurations/i)
  assert.match(document.body.textContent, /Method × Database/i)
  assert.equal(screen.queryByText('Experiment Board'), null)
  assert.equal(screen.queryByText('Archive'), null)
  await waitFor(() => {
    assert.ok(requested.includes('/api/comparisons/latest/results'))
    assert.ok(requested.includes('/api/archive'))
  })
  await userEvent.setup().click(configure)
  assert.ok(screen.getByRole('dialog', { name: 'Configure SQL API' }))
})
