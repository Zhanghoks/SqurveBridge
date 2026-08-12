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

test('a lost event pipe exits the bridge quietly instead of crashing', async () => {
  const { exitOnLostEventPipe } = await bridgeModule()
  assert.equal(process.stdout.listeners('error').includes(exitOnLostEventPipe), true)

  const exits = []
  const realExit = process.exit
  process.exit = code => { exits.push(code) }
  try {
    exitOnLostEventPipe(Object.assign(new Error('write EPIPE'), { code: 'EPIPE' }))
    exitOnLostEventPipe(Object.assign(new Error('destroyed'), { code: 'ERR_STREAM_DESTROYED' }))
  } finally {
    process.exit = realExit
  }
  assert.deepEqual(exits, [0, 0])

  const unrelated = Object.assign(new Error('boom'), { code: 'EACCES' })
  assert.throws(() => exitOnLostEventPipe(unrelated), /boom/)
})

test('the in-memory credential store never persists and follows CredentialStore semantics', async () => {
  const { createInMemoryCredentialStore } = await bridgeModule()
  const store = createInMemoryCredentialStore()

  assert.equal(await store.read('anthropic'), undefined)
  await store.modify('anthropic', async () => ({ type: 'api_key', key: 'secret' }))
  assert.deepEqual(await store.read('anthropic'), { type: 'api_key', key: 'secret' })
  assert.deepEqual(await store.list(), [{ providerId: 'anthropic', type: 'api_key' }])

  const unchanged = await store.modify('anthropic', async () => undefined)
  assert.deepEqual(unchanged, { type: 'api_key', key: 'secret' })

  await store.delete('anthropic')
  assert.equal(await store.read('anthropic'), undefined)
  assert.deepEqual(await store.list(), [])
})

test('hosted bridge runtime keeps credentials, models, and settings in memory', async () => {
  const { createBridgeRuntime } = await bridgeModule()
  const calls = []
  const runtime = { kind: 'runtime' }
  const settingsManager = { kind: 'memory-settings' }
  const sdk = {
    ModelRuntime: {
      async create(options) {
        calls.push(['runtime-create', options])
        return runtime
      },
    },
    ModelRegistry: class {
      constructor(value) {
        calls.push(['registry', value])
        this.runtime = value
      }
    },
    SettingsManager: {
      inMemory() {
        calls.push('settings-memory')
        return settingsManager
      },
    },
  }

  const hosted = await createBridgeRuntime(sdk, { cwd: '/workspace', profile: 'hosted-readonly' })
  assert.equal(hosted.modelRuntime, runtime)
  assert.equal(hosted.settingsManager, settingsManager)
  assert.equal(hosted.modelRegistry.runtime, runtime)

  const [, hostedOptions] = calls.find(entry => entry[0] === 'runtime-create')
  assert.equal(hostedOptions.modelsPath, null)
  assert.equal(hostedOptions.refreshOnCreate, false)
  assert.equal(typeof hostedOptions.credentials.read, 'function')
  assert.equal(calls.includes('settings-memory'), true)
})

test('local bridge runtime reads the project model catalog from config/pi_models.json', async () => {
  const { createBridgeRuntime } = await bridgeModule()
  const calls = []
  const runtime = { kind: 'runtime' }
  const sdk = {
    ModelRuntime: {
      async create(options) {
        calls.push(options)
        return runtime
      },
    },
    ModelRegistry: class {
      constructor(value) {
        this.runtime = value
      }
    },
    SettingsManager: {
      inMemory() {
        assert.fail('local profile must not force in-memory settings')
      },
    },
  }

  const local = await createBridgeRuntime(sdk, { cwd: '/workspace', profile: 'local-full' })
  assert.equal(local.modelRuntime, runtime)
  assert.equal(local.settingsManager, null)
  assert.equal(calls[0].modelsPath, path.join('/workspace', 'config', 'pi_models.json'))
  assert.equal(
    calls[0].modelsStorePath,
    path.join('/workspace', 'workspace', 'sessions', 'pi-agent', 'models-store.json'),
  )
  assert.equal(calls[0].credentials, undefined)
})

function fakePi() {
  const credentials = new Map()
  const models = [
    { provider: 'anthropic', id: 'claude-sonnet', name: 'Claude Sonnet' },
    { provider: 'openai-codex', id: 'gpt-5-codex', name: 'GPT-5 Codex' },
  ]
  const providers = {
    anthropic: { id: 'anthropic', auth: { apiKey: { name: 'Anthropic API key' } } },
    'openai-codex': { id: 'openai-codex', auth: { apiKey: { name: 'OpenAI API key' }, oauth: { name: 'OpenAI Codex' } } },
  }
  const modelRuntime = {
    getProvider: provider => providers[provider],
    async listCredentials() {
      return [...credentials.entries()].map(([providerId, credential]) => ({ providerId, type: credential.type }))
    },
    async login(provider, type, interaction) {
      if (type === 'api_key') {
        const key = await interaction.prompt({ type: 'secret', message: `Enter API key for ${provider}`, placeholder: 'API key' })
        if (!String(key).trim()) throw new Error('API key is required')
        const credential = { type: 'api_key', key: String(key).trim() }
        credentials.set(provider, credential)
        return credential
      }
      interaction.notify({ type: 'auth_url', url: 'https://auth.example/login', instructions: 'Open this URL.' })
      interaction.notify({ type: 'device_code', userCode: 'ABCD-EFGH', verificationUri: 'https://auth.example/device' })
      interaction.notify({ type: 'progress', message: 'Waiting for authorization' })
      const account = await interaction.prompt({ type: 'text', message: 'Account label', placeholder: 'work' })
      const tenant = await interaction.prompt({
        type: 'select',
        message: 'Choose tenant',
        options: [{ id: 'team-a', label: 'Team A' }],
      })
      const code = await interaction.prompt({ type: 'manual_code', message: 'Paste the authorization code' })
      const credential = { type: 'oauth', access: `${account}:${tenant}:${code}`, refresh: 'refresh', expires: 1 }
      credentials.set(provider, credential)
      return credential
    },
    async logout(provider) {
      credentials.delete(provider)
    },
  }
  const modelRegistry = {
    getAll: () => models,
    getProviderDisplayName: provider => provider === 'anthropic' ? 'Anthropic' : 'OpenAI Codex',
    getProviderAuthStatus: provider => ({ configured: credentials.has(provider), source: credentials.has(provider) ? 'stored' : undefined }),
    find: (provider, model) => models.find(item => item.provider === provider && item.id === model),
    hasConfiguredAuth: model => credentials.has(model.provider),
  }
  const session = {
    selected: null,
    prompts: [],
    async setModel(model) { this.selected = model },
    async prompt(message) { this.prompts.push(message) },
    async abort() {},
  }
  return { modelRuntime, modelRegistry, session, credentials }
}

const nextTurn = () => new Promise(resolve => setImmediate(resolve))

test('Pi auth protocol accepts an API key without emitting the secret', async () => {
  const { createPiAuthProtocol } = await bridgeModule()
  const events = []
  const pi = fakePi()
  const protocol = createPiAuthProtocol({ ...pi, emit: event => events.push(event) })

  await protocol.emitCatalogs()
  const login = protocol.handle({ type: 'auth_start', provider: 'anthropic', method: 'api_key' })
  await nextTurn()
  const prompt = events.find(event => event.type === 'auth_prompt')
  assert.equal(prompt.kind, 'secret')
  await protocol.handle({ type: 'auth_prompt_response', request_id: prompt.request_id, value: 'pi-secret-key' })
  await login

  assert.deepEqual(pi.credentials.get('anthropic'), { type: 'api_key', key: 'pi-secret-key' })
  assert.equal(events.some(event => event.type === 'auth_complete' && event.provider === 'anthropic'), true)
  assert.equal(JSON.stringify(events).includes('pi-secret-key'), false)

  await protocol.handle({ type: 'model_select', provider: 'anthropic', model: 'claude-sonnet' })
  await protocol.handle({ type: 'prompt', message: 'hello' })
  assert.equal(pi.session.selected.id, 'claude-sonnet')
  assert.deepEqual(pi.session.prompts, ['hello'])
})

test('Pi auth protocol reports subscription support from the provider catalog', async () => {
  const { createPiAuthProtocol } = await bridgeModule()
  const events = []
  const pi = fakePi()
  const protocol = createPiAuthProtocol({ ...pi, emit: event => events.push(event) })

  await protocol.emitCatalogs()
  const catalog = events.find(event => event.type === 'auth_catalog')
  const anthropic = catalog.providers.find(provider => provider.id === 'anthropic')
  const codex = catalog.providers.find(provider => provider.id === 'openai-codex')
  assert.deepEqual(anthropic.auth_methods, ['api_key'])
  assert.deepEqual(codex.auth_methods, ['api_key', 'subscription'])
})

test('Pi auth protocol selects a custom model id for an authenticated provider', async () => {
  const { createPiAuthProtocol } = await bridgeModule()
  const events = []
  const pi = fakePi()
  pi.credentials.set('anthropic', { type: 'api_key', key: 'secret' })
  const protocol = createPiAuthProtocol({ ...pi, emit: event => events.push(event) })

  await protocol.handle({
    type: 'model_select', provider: 'anthropic', model: 'claude-custom-latest',
  })

  assert.equal(pi.session.selected.provider, 'anthropic')
  assert.equal(pi.session.selected.id, 'claude-custom-latest')
  assert.equal(pi.session.selected.name, 'claude-custom-latest')
  assert.equal(
    events.findLast(event => event.type === 'model_catalog').models
      .some(model => model.id === 'claude-custom-latest' && model.selected),
    true,
  )
})

test('Pi auth protocol relays native OAuth events and prompt types', async () => {
  const { createPiAuthProtocol } = await bridgeModule()
  const events = []
  const pi = fakePi()
  const protocol = createPiAuthProtocol({ ...pi, emit: event => events.push(event) })

  const login = protocol.handle({ type: 'auth_start', provider: 'openai-codex', method: 'subscription' })
  const answerNext = async (kind, value) => {
    await nextTurn()
    const prompt = events.findLast(event => event.type === 'auth_prompt' && event.kind === kind && !event.answered)
    assert.ok(prompt, `missing ${kind} prompt`)
    prompt.answered = true
    await protocol.handle({ type: 'auth_prompt_response', request_id: prompt.request_id, value })
  }
  await answerNext('text', 'work-account')
  await answerNext('select', 'team-a')
  await answerNext('manual_code', 'manual-code')
  await login

  assert.equal(events.some(event => event.type === 'auth_event' && event.event === 'auth_url'), true)
  assert.equal(events.some(event => event.type === 'auth_event' && event.event === 'device_code'), true)
  assert.equal(events.some(event => event.type === 'auth_event' && event.event === 'progress'), true)
  assert.equal(events.some(event => event.type === 'auth_complete' && event.method === 'subscription'), true)
  assert.equal(JSON.stringify(events).includes('manual-code'), false)
})

test('Pi auth protocol logs out and rejects prompts without an authenticated model', async () => {
  const { createPiAuthProtocol } = await bridgeModule()
  const events = []
  const pi = fakePi()
  pi.credentials.set('anthropic', { type: 'api_key', key: 'secret' })
  const protocol = createPiAuthProtocol({ ...pi, emit: event => events.push(event) })

  await protocol.handle({ type: 'model_select', provider: 'anthropic', model: 'claude-sonnet' })
  await protocol.handle({ type: 'logout', provider: 'anthropic' })
  await protocol.handle({ type: 'prompt', message: 'must not run' })

  assert.equal(pi.credentials.has('anthropic'), false)
  assert.deepEqual(pi.session.prompts, [])
  assert.equal(events.some(event => event.type === 'auth_error' && event.code === 'auth_required'), true)
  assert.equal(JSON.stringify(events).includes('secret'), false)
})
