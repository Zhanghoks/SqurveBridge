import test from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'
import React from 'react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen, waitFor } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
registerLoader('./cssTestLoader.mjs', import.meta.url)
const unregister = register()
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
let HostedApp

test.afterEach(() => cleanup())
test.after(() => {
  unregister()
  closeDom()
})

test('hosted App exposes session SQL configuration instead of local env configuration', async () => {
  const providers = [{ id: 'qwen', models: ['qwen-plus'], default_model: 'qwen-plus' }]
  const matrix = JSON.parse(fs.readFileSync(path.join(root, 'config/reproduce_matrix.json'), 'utf8'))
  const configs = matrix.databases.flatMap(database => matrix.methods.map(method => {
    const configPath = path.join(root, 'reproduce/configs', database.directory, `${method}.json`)
    assert.ok(fs.existsSync(configPath), configPath)
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'))
    return {
      method,
      dataset: database.directory,
      split: database.split,
      config_path: path.relative(root, configPath),
      stages: config.task.task_meta.map(task => ({
        id: task.task_id,
        type: task.task_type,
        actor: Object.values(task.meta.task)[0],
      })),
    }
  }))
  const datasets = matrix.databases.map(database => database.directory)
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
      json: async () => path.startsWith('/api/comparisons/latest/results') ? responses['/api/comparisons/latest/results'] : responses[path],
    }
  }
  let appElement
  globalThis.__SQURVE_DEMO_ROOT__ = { render: element => { appElement = element } }
  await import(`./main.jsx?hosted-test=${Date.now()}`)
  HostedApp = appElement.type
  render(React.createElement(appElement.type))

  const configure = await screen.findByRole('button', { name: 'Configure SQL API' })
  assert.equal(screen.queryByRole('button', { name: 'Configure LLM' }), null)
  assert.match(document.body.textContent, /Bring your own SQL model credential/i)
  assert.deepEqual(
    [...document.querySelectorAll('.flow-module h2')].map(heading => heading.textContent),
    [
      'Configuration Studio',
      'Workflow Composition',
      'Run Workspace',
      'Result Inspection',
      'Weakness Diagnosis',
      'Bounded Improvement',
    ],
  )
  assert.match(document.body.textContent, /64 canonical configurations/i)
  assert.match(document.body.textContent, /Method × Database/i)
  assert.equal(screen.queryByText('Experiment Board'), null)
  assert.equal(screen.queryByText('Archive'), null)
  await waitFor(() => {
    assert.ok(requested.some(path => path.startsWith('/api/comparisons/latest/results?')))
    assert.ok(requested.includes('/api/archive'))
  })
  await userEvent.setup().click(configure)
  assert.ok(screen.getByRole('dialog', { name: 'Configure SQL API' }))
})

test('does not expose the local console while capabilities are pending', async () => {
  let resolveFetch
  globalThis.fetch = () => new Promise(resolve => { resolveFetch = resolve })
  render(React.createElement(HostedApp))
  assert.match(document.body.textContent, /Loading demo/)
  assert.equal(screen.queryByText('Experiment Board'), null)
  assert.equal(screen.queryByText('Archive'), null)
  resolveFetch?.({ ok: false, statusText: 'offline', json: async () => ({}) })
})

test('shows a neutral boot error instead of falling back to the local console', async () => {
  globalThis.fetch = async () => { throw new Error('offline') }
  render(React.createElement(HostedApp))
  assert.ok(await screen.findByRole('alert'))
  assert.match(document.body.textContent, /could not load its deployment configuration/i)
  assert.equal(screen.queryByText('Experiment Board'), null)
  assert.equal(screen.queryByText('Archive'), null)
})

test('localizes the pre-capabilities failure for a Chinese session', async () => {
  window.localStorage.setItem('squrve-demo-locale', 'zh-CN')
  globalThis.fetch = async () => { throw new Error('offline') }
  render(React.createElement(HostedApp))
  assert.ok(await screen.findByRole('alert'))
  assert.match(document.body.textContent, /无法加载演示部署配置/)
  assert.equal(screen.queryByText('Experiment Board'), null)
})
