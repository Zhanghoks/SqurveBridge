import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
const { cleanup, render, screen } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
const unregister = register()

async function loadDialog() {
  try {
    return (await import('./PiAuthDialog.jsx')).default
  } catch (error) {
    assert.fail(`Pi auth dialog must load: ${error.message}`)
  }
}

const baseState = {
  providers: [{ id: 'anthropic', name: 'Anthropic', auth_methods: ['api_key', 'subscription'], configured: false, credential_type: null }],
  models: [],
  selectedModel: null,
  prompt: null,
  events: [],
  status: 'idle',
  error: '',
}

test.afterEach(() => cleanup())
test.after(() => {
  unregister()
  closeDom()
})

test('starts Pi API-key login and clears the secret after answering a prompt', async () => {
  const PiAuthDialog = await loadDialog()
  const commands = []
  const user = userEvent.setup()
  const view = render(React.createElement(PiAuthDialog, {
    open: true,
    state: baseState,
    send: command => commands.push(command),
    onClose: () => {},
  }))

  await user.click(screen.getByRole('button', { name: 'API key' }))
  assert.deepEqual(commands.at(-1), { type: 'auth_start', provider: 'anthropic', method: 'api_key' })

  view.rerender(React.createElement(PiAuthDialog, {
    open: true,
    state: { ...baseState, status: 'prompting', prompt: { request_id: 'auth-1', kind: 'secret', message: 'Enter API key', placeholder: 'API key' } },
    send: command => commands.push(command),
    onClose: () => {},
  }))
  const input = screen.getByLabelText('Enter API key')
  assert.equal(input.type, 'password')
  await user.type(input, 'pi-dialog-secret')
  await user.click(screen.getByRole('button', { name: 'Continue' }))

  assert.deepEqual(commands.at(-1), {
    type: 'auth_prompt_response', request_id: 'auth-1', value: 'pi-dialog-secret',
  })
  assert.equal(input.value, '')
  assert.equal(document.body.textContent.includes('pi-dialog-secret'), false)
})

test('renders Pi OAuth events, select prompts, and cancellation', async () => {
  const PiAuthDialog = await loadDialog()
  const commands = []
  const user = userEvent.setup()
  render(React.createElement(PiAuthDialog, {
    open: true,
    state: {
      ...baseState,
      status: 'prompting',
      events: [
        { event: 'auth_url', url: 'https://auth.example/login', instructions: 'Authorize Pi.' },
        { event: 'device_code', verification_uri: 'https://auth.example/device', user_code: 'ABCD-EFGH' },
        { event: 'progress', message: 'Waiting for authorization' },
      ],
      prompt: {
        request_id: 'auth-2', kind: 'select', message: 'Choose tenant',
        options: [{ id: 'team-a', label: 'Team A' }],
      },
    },
    send: command => commands.push(command),
    onClose: () => {},
  }))

  const link = screen.getByRole('link', { name: /auth.example\/login/i })
  assert.equal(link.target, '_blank')
  assert.equal(link.rel, 'noreferrer')
  assert.match(document.body.textContent, /ABCD-EFGH/)
  assert.match(document.body.textContent, /Waiting for authorization/)
  await user.click(screen.getByRole('radio', { name: 'Team A' }))
  await user.click(screen.getByRole('button', { name: 'Continue' }))
  assert.equal(commands.at(-1).value, 'team-a')
  await user.click(screen.getByRole('button', { name: 'Cancel login' }))
  assert.deepEqual(commands.at(-1), { type: 'auth_cancel' })
})

test('selects an authenticated Pi model and logs out', async () => {
  const PiAuthDialog = await loadDialog()
  const commands = []
  let closed = false
  const user = userEvent.setup()
  render(React.createElement(PiAuthDialog, {
    open: true,
    state: {
      ...baseState,
      providers: [{ ...baseState.providers[0], configured: true, credential_type: 'api_key' }],
      models: [{ provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet', configured: true, selected: false }],
    },
    send: command => commands.push(command),
    onClose: () => { closed = true },
  }))

  await user.click(screen.getByRole('button', { name: /Claude Sonnet/ }))
  assert.deepEqual(commands.at(-1), { type: 'model_select', provider: 'anthropic', model: 'claude-sonnet' })
  await user.click(screen.getByRole('button', { name: 'Logout' }))
  assert.deepEqual(commands.at(-1), { type: 'logout', provider: 'anthropic' })
  await user.click(screen.getAllByRole('button', { name: 'Close' }).at(-1))
  assert.equal(closed, true)
})
