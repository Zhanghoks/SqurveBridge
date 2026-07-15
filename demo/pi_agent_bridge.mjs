import path from 'node:path'
import { realpath } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'

export function parseBridgeArgs(argv) {
  const values = {}
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || value === undefined) throw new Error(`Invalid Pi bridge argument: ${key || '<empty>'}`)
    values[key.slice(2)] = value
  }
  const tools = JSON.parse(values.tools || '[]')
  if (!values.cwd || !Array.isArray(tools) || tools.some(tool => typeof tool !== 'string')) {
    throw new Error('Pi bridge requires --cwd and a JSON array in --tools')
  }
  return {
    cwd: values.cwd,
    profile: values.profile || 'local-full',
    tools,
    provider: values.provider || null,
    model: values.model || null,
  }
}

export function eventToWire(event) {
  if (event.type === 'message_update') {
    const delta = event.assistantMessageEvent
    if (delta?.type === 'text_delta') return { type: 'text_delta', delta: delta.delta }
    if (delta?.type === 'thinking_delta') return { type: 'thinking_delta', delta: delta.delta }
    return null
  }
  if (event.type === 'tool_execution_start') {
    return {
      type: 'tool_start',
      tool_call_id: event.toolCallId,
      tool_name: event.toolName,
      args: event.args,
    }
  }
  if (event.type === 'tool_execution_update') {
    return {
      type: 'tool_update',
      tool_call_id: event.toolCallId,
      tool_name: event.toolName,
      partial_result: event.partialResult,
    }
  }
  if (event.type === 'tool_execution_end') {
    return {
      type: 'tool_end',
      tool_call_id: event.toolCallId,
      tool_name: event.toolName,
      is_error: event.isError,
      result: event.result,
    }
  }
  if (['agent_start', 'agent_end', 'agent_settled', 'turn_start', 'turn_end'].includes(event.type)) {
    return { type: event.type }
  }
  return null
}

function writeEvent(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`)
}

export function resourceLoaderOptions(config) {
  return {
    cwd: config.cwd,
    agentDir: path.join(config.cwd, 'tmp', 'pi-agent'),
    additionalSkillPaths: [path.join(config.cwd, 'skills')],
    noSkills: true,
    noExtensions: true,
    appendSystemPrompt: [
      `You are the embedded Pi backend for SqurveBridge. Runtime profile: ${config.profile}.`,
      config.profile === 'hosted-readonly'
        ? 'This is a public read-only demo. Never claim to write files or execute commands.'
        : 'This is a trusted local coding session. Follow repository AGENTS.md and skill contracts.',
    ],
  }
}

function isWithin(root, candidate) {
  const relative = path.relative(root, candidate)
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))
}

export async function assertConfinedPath(root, requested = '.') {
  const canonicalRoot = await realpath(root)
  const absolute = path.resolve(root, requested || '.')
  if (!isWithin(root, absolute)) throw new Error('Requested path is outside the SqurveBridge project.')
  let canonicalCandidate
  try {
    canonicalCandidate = await realpath(absolute)
  } catch (error) {
    if (error?.code === 'ENOENT') return absolute
    throw error
  }
  if (!isWithin(canonicalRoot, canonicalCandidate)) {
    throw new Error('Requested path is outside the SqurveBridge project.')
  }
  return absolute
}

export function createHostedTools(sdk, config) {
  const factories = {
    read: sdk.createReadTool,
    grep: sdk.createGrepTool,
    find: sdk.createFindTool,
    ls: sdk.createLsTool,
  }
  return config.tools.map(name => {
    const factory = factories[name]
    if (!factory) throw new Error(`Hosted Pi tool is not read-only: ${name}`)
    const tool = factory(config.cwd)
    return {
      ...tool,
      async execute(toolCallId, params, signal, onUpdate, context) {
        await assertConfinedPath(config.cwd, params?.path || '.')
        return tool.execute(toolCallId, params, signal, onUpdate, context)
      },
    }
  })
}

export function createBridgeStores(sdk, config) {
  if (config.profile === 'hosted-readonly') {
    const authStorage = sdk.AuthStorage.inMemory()
    return {
      authStorage,
      modelRegistry: sdk.ModelRegistry.inMemory(authStorage),
      settingsManager: sdk.SettingsManager.inMemory(),
    }
  }
  const authStorage = sdk.AuthStorage.create()
  return {
    authStorage,
    modelRegistry: sdk.ModelRegistry.create(authStorage, path.join(config.cwd, 'config', 'pi_models.json')),
    settingsManager: null,
  }
}

class AuthCancelledError extends Error {}

export function createPiAuthProtocol({ authStorage, modelRegistry, session, emit, initialModel = null }) {
  let activeModel = initialModel
  let pendingPrompt = null
  let promptSequence = 0
  let authAbortController = null
  let authRunning = false

  const oauthProviders = () => new Map(authStorage.getOAuthProviders().map(provider => [provider.id, provider]))
  const providerIds = () => [...new Set(modelRegistry.getAll().map(model => model.provider))]

  function providerCatalog() {
    const oauth = oauthProviders()
    return providerIds().sort().map(provider => {
      const credential = authStorage.get(provider)
      const methods = ['api_key']
      if (oauth.has(provider)) methods.push('subscription')
      return {
        id: provider,
        name: modelRegistry.getProviderDisplayName(provider),
        auth_methods: methods,
        configured: Boolean(modelRegistry.getProviderAuthStatus(provider).configured),
        credential_type: credential?.type || null,
      }
    })
  }

  function modelCatalog() {
    return modelRegistry.getAll().map(model => ({
      provider: model.provider,
      id: model.id,
      name: model.name || model.id,
      configured: Boolean(modelRegistry.hasConfiguredAuth(model)),
      selected: activeModel?.provider === model.provider && activeModel?.id === model.id,
    }))
  }

  function emitCatalogs() {
    const providers = providerCatalog()
    emit({ type: 'auth_catalog', providers })
    emit({
      type: 'auth_status',
      providers: providers.map(({ id, configured, credential_type }) => ({ id, configured, credential_type })),
    })
    emit({ type: 'model_catalog', models: modelCatalog() })
  }

  function askBrowser(kind, prompt) {
    if (pendingPrompt) throw new Error('Pi authentication already has a pending prompt')
    const requestId = `auth-${++promptSequence}`
    emit({
      type: 'auth_prompt',
      request_id: requestId,
      kind,
      message: prompt.message,
      placeholder: prompt.placeholder || null,
      options: prompt.options || null,
    })
    return new Promise((resolve, reject) => {
      pendingPrompt = { requestId, resolve, reject }
    })
  }

  async function loginWithApiKey(provider) {
    const name = modelRegistry.getProviderDisplayName(provider)
    const key = await askBrowser('secret', {
      message: `Enter API key for ${name}`,
      placeholder: 'API key',
    })
    if (!String(key).trim()) throw new Error('API key is required')
    authStorage.set(provider, { type: 'api_key', key: String(key).trim() })
  }

  async function loginWithSubscription(provider) {
    const oauth = oauthProviders()
    if (!oauth.has(provider)) throw new Error('Subscription login is unavailable for this provider')
    authAbortController = new AbortController()
    await authStorage.login(provider, {
      signal: authAbortController.signal,
      onAuth(info) {
        emit({
          type: 'auth_event',
          event: 'auth_url',
          url: info.url,
          instructions: info.instructions || null,
        })
      },
      onDeviceCode(info) {
        emit({
          type: 'auth_event',
          event: 'device_code',
          user_code: info.userCode,
          verification_uri: info.verificationUri,
          interval_seconds: info.intervalSeconds || null,
          expires_in_seconds: info.expiresInSeconds || null,
        })
      },
      onPrompt(prompt) {
        return askBrowser('text', prompt)
      },
      onProgress(message) {
        emit({ type: 'auth_event', event: 'progress', message })
      },
      onManualCodeInput() {
        return askBrowser('manual_code', {
          message: 'Paste the authorization code or callback URL',
          placeholder: 'Authorization code',
        })
      },
      onSelect(prompt) {
        return askBrowser('select', prompt)
      },
    })
  }

  async function startAuth(command) {
    if (authRunning) {
      emit({ type: 'auth_error', code: 'auth_in_progress', message: 'A Pi login is already in progress.' })
      return
    }
    const provider = String(command.provider || '')
    const method = String(command.method || '')
    if (!providerIds().includes(provider)) {
      emit({ type: 'auth_error', code: 'unsupported_provider', message: 'The selected Pi provider is unsupported.' })
      return
    }
    authRunning = true
    try {
      if (method === 'api_key') await loginWithApiKey(provider)
      else if (method === 'subscription') await loginWithSubscription(provider)
      else throw new Error('Unsupported Pi authentication method')
      modelRegistry.refresh()
      emitCatalogs()
      emit({ type: 'auth_complete', provider, method, status: 'authenticated' })
    } catch (error) {
      if (error instanceof AuthCancelledError || authAbortController?.signal.aborted) {
        authStorage.logout(provider)
        modelRegistry.refresh()
        emitCatalogs()
        emit({ type: 'auth_complete', provider, method, status: 'cancelled' })
      } else {
        emit({ type: 'auth_error', code: 'authentication_failed', message: 'Pi authentication failed.' })
      }
    } finally {
      authAbortController = null
      authRunning = false
    }
  }

  async function handle(command) {
    if (command.type === 'auth_start') {
      await startAuth(command)
      return
    }
    if (command.type === 'auth_prompt_response') {
      if (!pendingPrompt || command.request_id !== pendingPrompt.requestId) {
        emit({ type: 'auth_error', code: 'invalid_auth_prompt', message: 'The Pi login prompt is no longer active.' })
        return
      }
      const { resolve } = pendingPrompt
      pendingPrompt = null
      resolve(String(command.value ?? ''))
      return
    }
    if (command.type === 'auth_cancel') {
      authAbortController?.abort()
      if (pendingPrompt) {
        const { reject } = pendingPrompt
        pendingPrompt = null
        reject(new AuthCancelledError('Pi authentication cancelled'))
      }
      return
    }
    if (command.type === 'model_select') {
      const provider = String(command.provider || '')
      const modelId = String(command.model || '')
      const model = modelRegistry.find(provider, modelId)
      if (!model) {
        emit({ type: 'auth_error', code: 'unsupported_model', message: 'The selected Pi model is unsupported.' })
        return
      }
      if (!modelRegistry.hasConfiguredAuth(model)) {
        emit({ type: 'auth_error', code: 'auth_required', message: 'Authenticate this Pi provider before selecting its model.' })
        return
      }
      await session.setModel(model)
      activeModel = model
      emit({ type: 'model_catalog', models: modelCatalog() })
      return
    }
    if (command.type === 'logout') {
      const provider = String(command.provider || '')
      authStorage.logout(provider)
      modelRegistry.refresh()
      if (activeModel?.provider === provider) activeModel = null
      emitCatalogs()
      emit({ type: 'auth_complete', provider, method: 'logout', status: 'logged_out' })
      return
    }
    if (command.type === 'prompt') {
      if (!activeModel || !modelRegistry.hasConfiguredAuth(activeModel)) {
        emit({ type: 'auth_error', code: 'auth_required', message: 'Select an authenticated Pi model before chatting.' })
        return
      }
      emit({ type: 'prompt_accepted' })
      await session.prompt(String(command.message || ''))
      return
    }
    if (command.type === 'abort') {
      await session.abort()
      emit({ type: 'aborted' })
      return
    }
    throw new Error(`Unsupported Pi bridge command: ${command.type}`)
  }

  function dispose() {
    authAbortController?.abort()
    if (pendingPrompt) {
      pendingPrompt.reject(new AuthCancelledError('Pi bridge stopped'))
      pendingPrompt = null
    }
  }

  return { emitCatalogs, handle, dispose }
}

export async function runBridge(argv = process.argv.slice(2)) {
  const config = parseBridgeArgs(argv)
  const sdkPath = path.join(config.cwd, 'pi', 'packages', 'coding-agent', 'dist', 'index.js')
  let sdk
  try {
    sdk = await import(pathToFileURL(sdkPath).href)
  } catch (error) {
    throw new Error(`Embedded Pi is not built. Run npm ci --ignore-scripts && npm run build in ${path.join(config.cwd, 'pi')}: ${error.message}`)
  }

  const { authStorage, modelRegistry, settingsManager } = createBridgeStores(sdk, config)
  const resourceLoader = new sdk.DefaultResourceLoader(resourceLoaderOptions(config))
  await resourceLoader.reload()

  let model = null
  if (config.profile !== 'hosted-readonly') {
    if (config.provider && config.model) model = modelRegistry.find(config.provider, config.model)
    if (!model) model = modelRegistry.getAvailable()[0]
    if (!model) throw new Error(`Pi model is unavailable: ${config.provider || '<auto>'}/${config.model || '<auto>'}`)
  }

  const hostedTools = config.profile === 'hosted-readonly' ? createHostedTools(sdk, config) : null
  const { session } = await sdk.createAgentSession({
    cwd: config.cwd,
    model,
    tools: config.tools,
    noTools: hostedTools ? 'builtin' : undefined,
    customTools: hostedTools || undefined,
    resourceLoader,
    authStorage,
    modelRegistry,
    settingsManager: settingsManager || undefined,
    sessionManager: sdk.SessionManager.inMemory(config.cwd),
  })
  const unsubscribe = session.subscribe(event => {
    const wire = eventToWire(event)
    if (wire) writeEvent(wire)
  })
  const { skills, diagnostics } = resourceLoader.getSkills()
  writeEvent({
    type: 'ready',
    backend: 'pi',
    profile: config.profile,
    provider: model?.provider || null,
    model: model?.id || null,
    skills: skills.map(skill => skill.name),
    diagnostics: diagnostics.map(item => item.message),
  })
  const protocol = createPiAuthProtocol({
    authStorage,
    modelRegistry,
    session,
    emit: writeEvent,
    initialModel: model,
  })
  protocol.emitCatalogs()

  let buffer = ''
  process.stdin.setEncoding('utf8')
  process.stdin.on('data', chunk => {
    buffer += chunk
    while (buffer.includes('\n')) {
      const newline = buffer.indexOf('\n')
      const raw = buffer.slice(0, newline)
      buffer = buffer.slice(newline + 1)
      if (!raw.trim()) continue
      void handleCommand(raw)
    }
  })

  async function handleCommand(raw) {
    let command
    try {
      command = JSON.parse(raw)
      await protocol.handle(command)
    } catch (error) {
      writeEvent({ type: 'command_error', message: error.message })
    }
  }

  await new Promise(resolve => process.stdin.on('end', resolve))
  protocol.dispose()
  unsubscribe()
  session.dispose()
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isEntrypoint) {
  runBridge().catch(error => {
    writeEvent({ type: 'bridge_error', message: error.message })
    process.exitCode = 1
  })
}
