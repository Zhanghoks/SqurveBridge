import assert from 'node:assert/strict'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from '../testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, fireEvent, render } = await import('@testing-library/react')
registerLoader('../cssTestLoader.mjs', import.meta.url)
const unregister = register()

const { default: FullFlowDemo } = await import('./FullFlowDemo.jsx')

// The resize handler bails out on narrow viewports via matchMedia.
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

const pointer = (type, props = {}) => new window.MouseEvent(type, { bubbles: true, cancelable: true, ...props })

const renderShell = () => render(React.createElement(FullFlowDemo, {
  capabilities: {
    reproduce_configs: [],
    llm_providers: [],
    deployment: { target: 'local', features: {} },
  },
  databases: [],
  sqlAuth: null,
  api: async () => ({}),
  postJson: async () => ({}),
  onConfigureSql: () => {},
  credentialMode: 'local',
}))

test.afterEach(() => {
  cleanup()
  window.localStorage.clear()
})
test.after(() => {
  unregister()
  closeDom()
})

test('divider drag moves only the transform ghost and commits the grid once on release', () => {
  const { container, getByTestId } = renderShell()
  const shell = container.querySelector('.agent-shell')
  const panes = container.querySelector('.agent-shell-panes')
  const divider = container.querySelector('.agent-shell-divider')
  const ghost = getByTestId('agent-shell-divider-ghost')
  panes.getBoundingClientRect = () => ({ left: 0, width: 1000, top: 0, right: 1000, bottom: 800, height: 800 })

  assert.equal(divider.getAttribute('aria-valuenow'), '62')

  fireEvent(divider, pointer('pointerdown', { clientX: 620 }))
  assert.ok(document.body.classList.contains('agent-shell-resizing'))
  // The ghost is parked at the current width as soon as the drag starts.
  assert.equal(ghost.style.transform, 'translateX(620px)')

  fireEvent(window, pointer('pointermove', { clientX: 500 }))
  // During the drag only the ghost indicator moves, synchronously per
  // pointermove (transform = compositor work, no layout). The panes grid and
  // the inherited --dashboard-width variable stay untouched so the heavy
  // pane content is never relaid out mid-drag.
  assert.equal(ghost.style.transform, 'translateX(500px)')
  assert.equal(panes.style.gridTemplateColumns, '')
  assert.equal(shell.style.getPropertyValue('--dashboard-width'), '62%')
  assert.equal(divider.getAttribute('aria-valuenow'), '50')

  // Width is clamped to the aria-declared 35–75 range.
  fireEvent(window, pointer('pointermove', { clientX: 100 }))
  assert.equal(ghost.style.transform, 'translateX(350px)')
  assert.equal(divider.getAttribute('aria-valuenow'), '35')

  fireEvent(window, pointer('pointerup', { clientX: 100 }))
  // On release the final width is committed once to the shell variable and
  // React state; the ghost is hidden again via the body class.
  assert.equal(shell.style.getPropertyValue('--dashboard-width'), '35%')
  assert.equal(divider.getAttribute('aria-valuenow'), '35')
  assert.equal(panes.style.gridTemplateColumns, '')
  assert.equal(document.body.classList.contains('agent-shell-resizing'), false)
  assert.equal(JSON.parse(window.localStorage.getItem('squrve-demo-shell-layout')).dashboardWidth, 35)
})
