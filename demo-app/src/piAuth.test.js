import test from 'node:test'
import assert from 'node:assert/strict'

async function authModule() {
  try {
    return await import('./piAuth.js')
  } catch (error) {
    assert.fail(`Pi auth state module must load: ${error.message}`)
  }
}

test('tracks Pi native catalogs, prompts, events, and selected model', async () => {
  const { applyPiAuthEvent, createPiAuthState } = await authModule()
  let state = createPiAuthState()
  state = applyPiAuthEvent(state, {
    type: 'auth_catalog',
    providers: [{ id: 'anthropic', name: 'Anthropic', auth_methods: ['api_key', 'subscription'], configured: false }],
  })
  state = applyPiAuthEvent(state, {
    type: 'auth_prompt', request_id: 'auth-1', kind: 'secret', message: 'Enter API key', placeholder: 'API key',
  })
  state = applyPiAuthEvent(state, {
    type: 'auth_event', event: 'auth_url', url: 'https://auth.example', instructions: 'Open URL',
  })
  state = applyPiAuthEvent(state, {
    type: 'model_catalog',
    models: [{ provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet', configured: true, selected: true }],
  })

  assert.equal(state.providers[0].name, 'Anthropic')
  assert.equal(state.prompt.kind, 'secret')
  assert.equal(state.events[0].url, 'https://auth.example')
  assert.equal(state.selectedModel.id, 'claude-sonnet')
})

test('builds a prompt response without persisting the entered secret', async () => {
  const { commandForPrompt, createPiAuthState } = await authModule()
  const state = createPiAuthState()
  const prompt = { request_id: 'auth-2', kind: 'secret', message: 'API key' }

  assert.deepEqual(commandForPrompt(prompt, 'pi-auth-secret'), {
    type: 'auth_prompt_response',
    request_id: 'auth-2',
    value: 'pi-auth-secret',
  })
  assert.equal(JSON.stringify(state).includes('pi-auth-secret'), false)
})

test('clears auth interaction state after logout or session stop', async () => {
  const { applyPiAuthEvent, createPiAuthState } = await authModule()
  let state = applyPiAuthEvent(createPiAuthState(), {
    type: 'auth_error', code: 'authentication_failed', message: 'Pi authentication failed.',
  })
  state = applyPiAuthEvent(state, {
    type: 'auth_complete', provider: 'anthropic', method: 'logout', status: 'logged_out',
  })
  state = applyPiAuthEvent(state, { type: 'exit' })

  assert.deepEqual(state, createPiAuthState())
})
