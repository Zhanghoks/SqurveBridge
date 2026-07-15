import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

async function bridgeModule() {
  try {
    return await import('../demo/pi_agent_bridge.mjs')
  } catch (error) {
    assert.fail(`Pi bridge module must load: ${error.message}`)
  }
}

test('parses the embedded Pi bridge configuration', async () => {
  const { parseBridgeArgs } = await bridgeModule()
  assert.deepEqual(
    parseBridgeArgs([
      '--cwd', '/workspace',
      '--profile', 'hosted-readonly',
      '--tools', '["read","grep"]',
      '--provider', 'deepseek',
      '--model', 'deepseek-chat',
    ]),
    {
      cwd: '/workspace',
      profile: 'hosted-readonly',
      tools: ['read', 'grep'],
      provider: 'deepseek',
      model: 'deepseek-chat',
    },
  )
})

test('maps Pi streaming and tool events to stable chat events', async () => {
  const { eventToWire } = await bridgeModule()
  assert.deepEqual(
    eventToWire({
      type: 'message_update',
      assistantMessageEvent: { type: 'text_delta', delta: 'hello' },
    }),
    { type: 'text_delta', delta: 'hello' },
  )
  assert.deepEqual(
    eventToWire({ type: 'tool_execution_start', toolCallId: '1', toolName: 'read', args: { path: 'README.md' } }),
    { type: 'tool_start', tool_call_id: '1', tool_name: 'read', args: { path: 'README.md' } },
  )
  assert.deepEqual(
    eventToWire({ type: 'agent_end' }),
    { type: 'agent_end' },
  )
})

test('loads only SqurveBridge project skills', async () => {
  const { resourceLoaderOptions } = await bridgeModule()
  const options = resourceLoaderOptions({ cwd: '/workspace', profile: 'hosted-readonly' })
  assert.equal(options.noSkills, true)
  assert.deepEqual(options.additionalSkillPaths, ['/workspace/skills'])
  assert.equal(options.noExtensions, true)
})

test('hosted paths cannot escape the project through absolute paths or symlinks', async () => {
  const { assertConfinedPath } = await bridgeModule()
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'squrve-pi-path-'))
  const root = path.join(temporary, 'project')
  const outside = path.join(temporary, 'secret.txt')
  await fs.mkdir(root)
  await fs.writeFile(path.join(root, 'README.md'), 'public')
  await fs.writeFile(outside, 'secret')
  await fs.symlink(outside, path.join(root, 'escape'))

  assert.equal(await assertConfinedPath(root, 'README.md'), path.join(root, 'README.md'))
  await assert.rejects(() => assertConfinedPath(root, outside), /outside the SqurveBridge project/)
  await assert.rejects(() => assertConfinedPath(root, 'escape'), /outside the SqurveBridge project/)
})
