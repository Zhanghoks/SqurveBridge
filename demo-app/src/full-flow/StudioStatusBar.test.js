import assert from 'node:assert/strict'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from '../testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen, fireEvent } = await import('@testing-library/react')
registerLoader('../cssTestLoader.mjs', import.meta.url)
const unregister = register()

const { default: StudioStatusBar, runPhaseStatusKey } = await import('./StudioStatusBar.jsx')
const { translate } = await import('../i18n/index.js')

const t = (key, params) => translate('en-US', key, params)

function renderBar(overrides = {}) {
  const props = {
    connectionCount: 2,
    focusedMethod: 'DINSQL',
    focusedDatabase: 'Spider',
    credentialConfigured: true,
    credentialLabel: 'qwen / qwen-plus',
    runPhase: 'ready',
    onNavigate: () => {},
    t,
    ...overrides,
  }
  return render(React.createElement(StudioStatusBar, props))
}

test('renders personal workspace heading and local-session note', () => {
  renderBar()
  assert.ok(screen.getByText('Personal workspace'))
  assert.ok(screen.getByText('Local session data only'))
  cleanup()
})

test('shows connection count, focus pair and credential label', () => {
  renderBar()
  assert.ok(screen.getByText('2 Method × Database'))
  assert.ok(screen.getByText('DINSQL × Spider'))
  assert.ok(screen.getByText('qwen / qwen-plus'))
  cleanup()
})

test('shows not-configured state without any credential value', () => {
  renderBar({ credentialConfigured: false, credentialLabel: '' })
  assert.ok(screen.getByText('Not configured'))
  cleanup()
})

test('falls back to generic configured label when no model name given', () => {
  renderBar({ credentialConfigured: true, credentialLabel: '' })
  assert.ok(screen.getByText('Configured'))
  cleanup()
})

test('clicking status items navigates to the matching stage tab', () => {
  const visited = []
  renderBar({ onNavigate: step => visited.push(step) })
  fireEvent.click(screen.getByTestId('studio-status-connections'))
  fireEvent.click(screen.getByTestId('studio-status-focus'))
  fireEvent.click(screen.getByTestId('studio-status-credential'))
  fireEvent.click(screen.getByTestId('studio-status-run'))
  assert.deepEqual(visited, ['compose', 'query', 'query', 'board'])
  cleanup()
})

test('shows empty-focus placeholder when no pair is focused', () => {
  renderBar({ focusedMethod: '', focusedDatabase: '' })
  assert.ok(screen.getByText('Not selected'))
  cleanup()
})

test('maps run phases onto shared status keys', () => {
  assert.equal(runPhaseStatusKey('ready'), 'status.ready')
  assert.equal(runPhaseStatusKey(''), 'status.ready')
  assert.equal(runPhaseStatusKey(undefined), 'status.ready')
  assert.equal(runPhaseStatusKey('generatingSql'), 'status.running')
  assert.equal(runPhaseStatusKey('evaluating'), 'status.running')
  assert.equal(runPhaseStatusKey('completed'), 'status.completed')
  assert.equal(runPhaseStatusKey('failed'), 'status.failed')
  assert.equal(runPhaseStatusKey('unknown-phase'), 'status.ready')
})

test('renders run status text for a running phase', () => {
  renderBar({ runPhase: 'executingSql' })
  assert.ok(screen.getByText('Running'))
  cleanup()
})

test.after(() => {
  unregister()
  closeDom()
})
