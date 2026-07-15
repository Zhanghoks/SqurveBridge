import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { act, cleanup, render, screen } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
const unregister = register()

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    this.listeners = new Map()
    this.sent = []
    FakeWebSocket.instances.push(this)
    setImmediate(() => {
      this.readyState = FakeWebSocket.OPEN
      this.listeners.get('open')?.forEach(listener => listener())
    })
  }

  addEventListener(type, listener) {
    const current = this.listeners.get(type) || []
    current.push(listener)
    this.listeners.set(type, current)
  }

  send(value) {
    this.sent.push(JSON.parse(value))
  }

  emit(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }
}

test.afterEach(() => {
  cleanup()
  FakeWebSocket.instances = []
})
test.after(() => {
  unregister()
  closeDom()
})

test('Agent Harness authenticates and selects a model before enabling chat', async () => {
  globalThis.WebSocket = FakeWebSocket
  globalThis.fetch = async () => ({ ok: true })
  const AgentHarness = (await import('./AgentHarness.jsx')).default
  const api = async path => {
    assert.equal(path, '/api/agent')
    return { available: true, backend: 'pi', profile: 'hosted-readonly', provider: null, model: null, skills: [], tools: ['read'] }
  }
  const postJson = async path => {
    assert.equal(path, '/api/agent/sessions')
    return { session_id: 'session-auth', running: true, profile: 'hosted-readonly' }
  }
  const Status = ({ children }) => React.createElement('span', null, children)
  const user = userEvent.setup()
  render(React.createElement(AgentHarness, { api, postJson, Status }))

  await user.click(await screen.findByRole('button', { name: 'Login to Pi' }))
  const socket = FakeWebSocket.instances[0]
  assert.ok(socket)
  await act(async () => {
    socket.emit({ type: 'ready', backend: 'pi', profile: 'hosted-readonly', provider: null, model: null, skills: [] })
    socket.emit({
      type: 'auth_catalog',
      providers: [{ id: 'anthropic', name: 'Anthropic', auth_methods: ['api_key'], configured: false, credential_type: null }],
    })
    socket.emit({ type: 'model_catalog', models: [{ provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet', configured: false, selected: false }] })
  })

  assert.ok(await screen.findByRole('dialog', { name: 'Login to Pi' }))
  await user.click(screen.getByRole('button', { name: 'API key' }))
  assert.deepEqual(socket.sent.at(-1), { type: 'auth_start', provider: 'anthropic', method: 'api_key' })
  await act(async () => socket.emit({ type: 'auth_prompt', request_id: 'auth-1', kind: 'secret', message: 'Enter API key', placeholder: 'API key' }))
  const key = await screen.findByLabelText('Enter API key')
  await user.type(key, 'agent-dialog-secret')
  await user.click(screen.getByRole('button', { name: 'Continue' }))
  assert.equal(socket.sent.at(-1).value, 'agent-dialog-secret')
  assert.equal(document.body.textContent.includes('agent-dialog-secret'), false)

  await act(async () => {
    socket.emit({
      type: 'auth_catalog',
      providers: [{ id: 'anthropic', name: 'Anthropic', auth_methods: ['api_key'], configured: true, credential_type: 'api_key' }],
    })
    socket.emit({ type: 'model_catalog', models: [{ provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet', configured: true, selected: false }] })
    socket.emit({ type: 'auth_complete', provider: 'anthropic', method: 'api_key', status: 'authenticated' })
  })
  await user.click(await screen.findByRole('button', { name: /Claude Sonnet/ }))
  assert.deepEqual(socket.sent.at(-1), { type: 'model_select', provider: 'anthropic', model: 'claude-sonnet' })
  await act(async () => socket.emit({ type: 'model_catalog', models: [{ provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet', configured: true, selected: true }] }))

  assert.match(await screen.findByText(/anthropic\/claude-sonnet/i).then(node => node.textContent), /anthropic\/claude-sonnet/i)
  assert.equal(screen.getByPlaceholderText('Message Pi or use a Skill…').disabled, false)
})
