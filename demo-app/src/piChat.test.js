import test from 'node:test'
import assert from 'node:assert/strict'

async function chatModule() {
  try {
    return await import('./piChat.js')
  } catch (error) {
    assert.fail(`Pi chat state module must load: ${error.message}`)
  }
}

test('builds assistant text from Pi streaming events', async () => {
  const { createPiChatState, applyPiEvent } = await chatModule()
  let state = createPiChatState()
  state = applyPiEvent(state, { type: 'agent_start' })
  state = applyPiEvent(state, { type: 'text_delta', delta: 'Hello' })
  state = applyPiEvent(state, { type: 'text_delta', delta: ' world' })
  state = applyPiEvent(state, { type: 'agent_end' })
  assert.equal(state.messages.at(-1).content, 'Hello world')
  assert.equal(state.messages.at(-1).streaming, false)
  assert.equal(state.status, 'ready')
})

test('tracks Pi tool calls as structured activity', async () => {
  const { createPiChatState, applyPiEvent } = await chatModule()
  let state = applyPiEvent(createPiChatState(), {
    type: 'tool_start', tool_call_id: 'tool-1', tool_name: 'read', args: { path: 'README.md' },
  })
  state = applyPiEvent(state, {
    type: 'tool_end', tool_call_id: 'tool-1', tool_name: 'read', is_error: false,
  })
  assert.deepEqual(state.tools[0], {
    id: 'tool-1', name: 'read', args: { path: 'README.md' }, status: 'complete', isError: false,
  })
})

test('formats project skills with Pi native command syntax', async () => {
  const { skillPrompt } = await chatModule()
  assert.equal(skillPrompt('run'), '/skill:run')
  assert.equal(skillPrompt('candidate-reader', 'https://github.com/example/repo'), '/skill:candidate-reader https://github.com/example/repo')
})
