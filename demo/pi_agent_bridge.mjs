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

export async function runBridge(argv = process.argv.slice(2)) {
  const config = parseBridgeArgs(argv)
  const sdkPath = path.join(config.cwd, 'pi', 'packages', 'coding-agent', 'dist', 'index.js')
  let sdk
  try {
    sdk = await import(pathToFileURL(sdkPath).href)
  } catch (error) {
    throw new Error(`Embedded Pi is not built. Run npm ci --ignore-scripts && npm run build in ${path.join(config.cwd, 'pi')}: ${error.message}`)
  }

  const authStorage = sdk.AuthStorage.create()
  const modelRegistry = sdk.ModelRegistry.create(authStorage, path.join(config.cwd, 'config', 'pi_models.json'))
  const resourceLoader = new sdk.DefaultResourceLoader(resourceLoaderOptions(config))
  await resourceLoader.reload()

  let model
  if (config.provider && config.model) model = modelRegistry.find(config.provider, config.model)
  if (!model) model = modelRegistry.getAvailable()[0]
  if (!model) throw new Error(`Pi model is unavailable: ${config.provider || '<auto>'}/${config.model || '<auto>'}`)

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
    provider: model.provider,
    model: model.id,
    skills: skills.map(skill => skill.name),
    diagnostics: diagnostics.map(item => item.message),
  })

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
      if (command.type === 'prompt') {
        writeEvent({ type: 'prompt_accepted' })
        await session.prompt(String(command.message || ''))
      } else if (command.type === 'abort') {
        await session.abort()
        writeEvent({ type: 'aborted' })
      } else {
        throw new Error(`Unsupported Pi bridge command: ${command.type}`)
      }
    } catch (error) {
      writeEvent({ type: 'command_error', message: error.message })
    }
  }

  await new Promise(resolve => process.stdin.on('end', resolve))
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
