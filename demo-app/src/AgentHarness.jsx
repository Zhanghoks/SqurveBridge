import { useEffect, useRef, useState } from 'react'
import PiAuthDialog from './PiAuthDialog.jsx'
import { appendUserMessage, applyPiEvent, createPiChatState, skillPrompt } from './piChat.js'
import { applyPiAuthEvent, createPiAuthState } from './piAuth.js'

const DEFAULT_SKILLS = ['candidate-reader', 'integration-pipeline', 'config-adapter', 'run', 'meta-evo']

const SKILL_GROUPS = [
  { id: 'integrate', labelKey: 'agent.skillGroup.integrate', detailKey: 'agent.skillGroup.integrateDetail' },
  { id: 'evaluate', labelKey: 'agent.skillGroup.evaluate', detailKey: 'agent.skillGroup.evaluateDetail' },
  { id: 'improve', labelKey: 'agent.skillGroup.improve', detailKey: 'agent.skillGroup.improveDetail' },
]

const SKILL_META = {
  'candidate-reader': {
    group: 'integrate',
    step: 1,
    titleKey: 'agent.skill.candidateReader',
    detailKey: 'configure.agentSkillCandidate',
  },
  'integration-pipeline': {
    group: 'integrate',
    step: 2,
    titleKey: 'agent.skill.integrationPipeline',
    detailKey: 'configure.agentSkillPipeline',
  },
  'config-adapter': {
    group: 'integrate',
    step: 3,
    titleKey: 'agent.skill.configAdapter',
    detailKey: 'configure.agentSkillConfig',
  },
  run: {
    group: 'evaluate',
    step: 4,
    titleKey: 'agent.skill.run',
    detailKey: 'agent.skill.runDetail',
  },
  'meta-evo': {
    group: 'improve',
    step: 5,
    titleKey: 'agent.skill.metaEvo',
    detailKey: 'agent.skill.metaEvoDetail',
  },
}

const HOSTED_SUGGESTIONS = [
  { id: 'explain', labelKey: 'agent.suggest.explain', prompt: 'Explain what this SqurveBridge bundle contains and how the published methods relate to each other.' },
  { id: 'config', labelKey: 'agent.suggest.config', prompt: 'Walk me through one reproduce configuration in this bundle and what each Actor stage does.' },
  { id: 'evidence', labelKey: 'agent.suggest.evidence', prompt: 'Where should I look for published evidence or evaluation artifacts in this repository?' },
]

const LOCAL_SUGGESTIONS = [
  { id: 'candidate', labelKey: 'agent.suggest.candidate', skill: 'candidate-reader' },
  { id: 'pipeline', labelKey: 'agent.suggest.pipeline', skill: 'integration-pipeline' },
  { id: 'config', labelKey: 'agent.suggest.writeConfig', skill: 'config-adapter' },
]

const FALLBACK = {
  'agent.connectModel': 'Connect a model',
  'agent.switchModel': 'Switch model',
  'agent.needModel': 'Connect a model to start',
  'agent.unavailable': 'Pi build unavailable',
  'agent.working': 'Pi is working',
  'agent.ready': 'Ready',
  'agent.connected': 'Connected',
  'agent.stopResponse': 'Stop response',
  'agent.endSession': 'End session',
  'agent.send': 'Send',
  'agent.placeholder': 'Type / for skills',
  'agent.placeholderNeedModel': 'Type / for skills — connect a model to send',
  'agent.emptyHosted': 'Ask about the published bundle, configs, or evidence.',
  'agent.emptyLocal': 'Ask Pi to inspect, integrate, reproduce, or evaluate.',
  'agent.emptyHint': 'Suggestions below get you started. Skills stay available when you need them.',
  'agent.greetingMorning': 'Good morning',
  'agent.greetingAfternoon': 'Good afternoon',
  'agent.greetingEvening': 'Good evening',
  'agent.you': 'You',
  'agent.pi': 'Pi',
  'agent.reasoning': 'Reasoning',
  'agent.toolArgs': 'Arguments',
  'agent.suggest.explain': 'Explain this bundle',
  'agent.suggest.config': 'Walk through a config',
  'agent.suggest.evidence': 'Find published evidence',
  'agent.suggest.candidate': 'Read a GitHub candidate',
  'agent.suggest.pipeline': 'Rebuild into Actors',
  'agent.suggest.writeConfig': 'Write a reproduce config',
  'agent.skills': 'Skills',
  'agent.closeSkills': 'Close',
  'agent.skillsHint': 'Run a project Skill. Steps follow integrate → evaluate → improve.',
  'agent.skillGroup.integrate': 'Integrate',
  'agent.skillGroup.integrateDetail': 'Bring an external method into SqurveBridge',
  'agent.skillGroup.evaluate': 'Evaluate',
  'agent.skillGroup.evaluateDetail': 'Run or inspect a reproduce evaluation',
  'agent.skillGroup.improve': 'Improve',
  'agent.skillGroup.improveDetail': 'Diagnose bottlenecks and propose safe changes',
  'agent.skill.candidateReader': 'Read candidate',
  'agent.skill.integrationPipeline': 'Rebuild Actors',
  'agent.skill.configAdapter': 'Write config',
  'agent.skill.run': 'Run evaluation',
  'agent.skill.metaEvo': 'Meta evolution',
  'agent.skill.runDetail': 'Launch or inspect an evaluation run through the project Skill.',
  'agent.skill.metaEvoDetail': 'Diagnose bottlenecks and propose safe component improvements.',
  'configure.agentSkillCandidate': 'Read a public GitHub candidate and draft an integration manifest.',
  'configure.agentSkillPipeline': 'Rebuild the candidate into Squrve-native Actor workflows.',
  'configure.agentSkillConfig': 'Emit a reproduce config that appears in the Studio catalog.',
  'agent.title': 'Pi Agent',
  'agent.subtitle': 'Chat with the SqurveBridge backend',
  'agent.idleDetail': 'Ask below to get started',
}

function label(t, key) {
  if (typeof t === 'function') {
    const value = t(key)
    if (value && value !== key) return value
  }
  return FALLBACK[key] || key
}

function greetingKey(date = new Date()) {
  const hour = date.getHours()
  if (hour < 12) return 'agent.greetingMorning'
  if (hour < 18) return 'agent.greetingAfternoon'
  return 'agent.greetingEvening'
}

export default function AgentHarness({
  api,
  postJson,
  Status,
  candidateUrl = '',
  onCandidateReaderStart,
  onCandidateUrlRequired,
  queuedCommand = null,
  onQueuedCommandSent,
  embedded = false,
  shell = false,
  autoOpenAuth = false,
  onRequestNewChat,
  t,
}) {
  const socketRef = useRef(null)
  const sessionRef = useRef(null)
  const handledCommandRef = useRef('')
  const autoAuthStartedRef = useRef(false)
  const autoAuthResolvedRef = useRef(false)
  const selectedModelKeyRef = useRef('')
  const endRef = useRef(null)
  const [catalog, setCatalog] = useState(null)
  const [chat, setChat] = useState(createPiChatState)
  const [auth, setAuth] = useState(createPiAuthState)
  const [authOpen, setAuthOpen] = useState(false)
  const [authCatalogReady, setAuthCatalogReady] = useState(false)
  const [draft, setDraft] = useState('')
  const [skillsOpen, setSkillsOpen] = useState(false)

  const receive = event => {
    try {
      const payload = JSON.parse(event.data)
      setChat(current => applyPiEvent(current, payload))
      setAuth(current => applyPiAuthEvent(current, payload))
      if (payload.type === 'auth_catalog' || payload.type === 'model_catalog') {
        setAuthCatalogReady(true)
      }
      if (payload.type === 'model_catalog') {
        const selected = payload.models?.find(model => model.selected)
        if (selected) setChat(current => ({ ...current, provider: selected.provider, model: selected.id }))
      }
    } catch {
      setChat(current => ({ ...current, status: 'error', error: 'Pi returned an invalid event.' }))
    }
  }

  const connect = session => {
    const existing = socketRef.current
    if (existing?.readyState === WebSocket.OPEN) return Promise.resolve(existing)
    if (existing?.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('open', () => resolve(existing), { once: true })
        existing.addEventListener('error', () => reject(new Error('Pi chat connection failed.')), { once: true })
      })
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/agent/sessions/${session.session_id}/ws`)
    socketRef.current = socket
    socket.onmessage = receive
    socket.onclose = () => {
      if (socketRef.current === socket) {
        socketRef.current = null
        setChat(current => current.status === 'stopped' ? current : { ...current, status: 'stopped' })
        setAuth(createPiAuthState())
        setAuthOpen(false)
      }
    }
    return new Promise((resolve, reject) => {
      socket.addEventListener('open', () => resolve(socket), { once: true })
      socket.addEventListener('error', () => reject(new Error('Pi chat connection failed.')), { once: true })
    })
  }

  const start = async () => {
    if (sessionRef.current?.running && socketRef.current?.readyState === WebSocket.OPEN) return sessionRef.current
    setChat(current => ({ ...current, status: 'starting', error: '' }))
    try {
      const session = await postJson('/api/agent/sessions', {})
      sessionRef.current = session
      await connect(session)
      return session
    } catch (error) {
      setChat(current => ({ ...current, status: 'error', error: error.message }))
      return null
    }
  }

  const sendCommand = command => {
    const socket = socketRef.current
    if (socket?.readyState !== WebSocket.OPEN) throw new Error('Pi chat connection is not ready.')
    socket.send(JSON.stringify(command))
  }

  const openAuth = async () => {
    let session = sessionRef.current
    if (!session?.running || socketRef.current?.readyState !== WebSocket.OPEN) session = await start()
    if (!session) return
    setAuthOpen(true)
  }

  const sendMessage = async (message, taskId = '') => {
    const normalized = message.trim()
    if (!normalized) return
    if (!auth.selectedModel) {
      await openAuth()
      return
    }
    let session = sessionRef.current
    if (!session?.running || socketRef.current?.readyState !== WebSocket.OPEN) session = await start()
    if (!session) return
    const socket = await connect(session)
    setChat(current => appendUserMessage(current, normalized))
    socket.send(JSON.stringify({ type: 'prompt', message: normalized }))
    setDraft('')
    if (taskId) {
      handledCommandRef.current = taskId
      onQueuedCommandSent?.(taskId, session)
    }
  }

  const stop = async () => {
    const session = sessionRef.current
    if (!session?.session_id) return
    try {
      await postJson(`/api/agent/sessions/${session.session_id}/stop`, {})
    } finally {
      sessionRef.current = null
      socketRef.current?.close()
      setChat(current => ({ ...current, status: 'stopped' }))
      setAuth(createPiAuthState())
      setAuthOpen(false)
    }
  }

  const abort = () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'abort' }))
  }

  const useSkill = name => {
    if (name === 'candidate-reader' && (candidateUrl || onCandidateUrlRequired || onCandidateReaderStart)) {
      if (!candidateUrl) {
        onCandidateUrlRequired?.()
        return
      }
      if (onCandidateReaderStart) {
        onCandidateReaderStart()
        return
      }
    }
    sendMessage(skillPrompt(name)).catch(error => setChat(current => ({ ...current, error: error.message })))
  }

  const runSuggestion = suggestion => {
    if (suggestion.skill) {
      useSkill(suggestion.skill)
      return
    }
    sendMessage(suggestion.prompt).catch(error => setChat(current => ({ ...current, error: error.message })))
  }

  useEffect(() => {
    let active = true
    api('/api/agent').then(data => {
      if (!active) return
      const catalogData = data && typeof data === 'object' ? data : { available: false }
      setCatalog(catalogData)
      setChat(current => ({
        ...current,
        profile: catalogData.profile || '',
        provider: catalogData.provider || '',
        model: catalogData.model || '',
        skills: Array.isArray(catalogData.skills) ? catalogData.skills : [],
      }))
    }).catch(error => setChat(current => ({ ...current, status: 'error', error: error.message })))
    return () => {
      active = false
      const session = sessionRef.current
      socketRef.current?.close()
      if (session?.running) fetch(`/api/agent/sessions/${session.session_id}/stop`, { method: 'POST', keepalive: true }).catch(() => {})
    }
  }, [api])

  useEffect(() => {
    if (!queuedCommand?.id || handledCommandRef.current === queuedCommand.id) return
    sendMessage(queuedCommand.command, queuedCommand.id).catch(error => setChat(current => ({ ...current, error: error.message })))
  }, [queuedCommand?.id, auth.selectedModel?.provider, auth.selectedModel?.id])

  useEffect(() => {
    if (!autoOpenAuth || autoAuthStartedRef.current || !catalog || catalog.available === false) return
    if (auth.selectedModel) {
      autoAuthStartedRef.current = true
      autoAuthResolvedRef.current = true
      return
    }
    autoAuthStartedRef.current = true
    start().catch(error => setChat(current => ({ ...current, error: error.message })))
  }, [autoOpenAuth, catalog, auth.selectedModel])

  useEffect(() => {
    if (!autoOpenAuth || !autoAuthStartedRef.current || autoAuthResolvedRef.current || !authCatalogReady) return
    autoAuthResolvedRef.current = true
    if (auth.selectedModel) {
      setAuthOpen(false)
      return
    }
    const configured = auth.models.find(model => model.configured)
    if (configured) {
      try {
        sendCommand({
          type: 'model_select',
          provider: configured.provider,
          model: configured.id,
        })
        setAuthOpen(false)
      } catch {
        setAuthOpen(true)
      }
      return
    }
    setAuthOpen(true)
  }, [autoOpenAuth, authCatalogReady, auth.selectedModel, auth.models])

  useEffect(() => {
    const key = auth.selectedModel
      ? `${auth.selectedModel.provider}/${auth.selectedModel.id}`
      : ''
    const previous = selectedModelKeyRef.current
    selectedModelKeyRef.current = key
    if (key && key !== previous) setAuthOpen(false)
  }, [auth.selectedModel])

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' }) }, [chat.messages, chat.tools])

  const hosted = chat.profile === 'hosted-readonly'
  const skills = chat.skills.length
    ? chat.skills.filter(name => DEFAULT_SKILLS.includes(name))
    : DEFAULT_SKILLS
  const running = ['starting', 'thinking', 'ready'].includes(chat.status) && Boolean(sessionRef.current)
  const busy = chat.status === 'thinking'
  const authenticated = Boolean(auth.selectedModel)
  const modelLabel = authenticated ? `${auth.selectedModel.provider}/${auth.selectedModel.id}` : ''
  const statusTone = chat.error || auth.error ? 'danger' : busy ? 'running' : authenticated ? 'success' : 'neutral'
  const statusLabel = busy
    ? label(t, 'agent.working')
    : authenticated
      ? label(t, 'agent.connected')
      : catalog?.available === false
        ? label(t, 'agent.unavailable')
        : label(t, 'agent.needModel')
  const sessionDetail = authenticated
    ? modelLabel
    : catalog?.available === false
      ? label(t, 'agent.unavailable')
      : embedded
        ? label(t, 'agent.idleDetail')
        : label(t, 'agent.subtitle')
  const suggestions = hosted ? HOSTED_SUGGESTIONS : LOCAL_SUGGESTIONS
  const composerDisabled = busy || catalog?.available === false
  const sendDisabled = composerDisabled || !draft.trim()

  const catchSend = promise => promise.catch(error => setChat(current => ({ ...current, error: error.message })))

  const resetChat = async () => {
    await stop()
    setChat(current => ({
      ...createPiChatState(),
      profile: current.profile,
      provider: current.provider,
      model: current.model,
      skills: current.skills,
    }))
    setDraft('')
    onRequestNewChat?.()
  }

  const isEmpty = chat.messages.length === 0
  const shellClass = [
    'tool-panel agent-harness pi-chat',
    embedded ? 'agent-harness-embedded' : '',
    shell ? 'agent-harness-shell' : '',
    shell && isEmpty ? 'is-empty' : '',
  ].filter(Boolean).join(' ')

  const toolbar = shell && !isEmpty ? (
    <div className="agent-shell-toolbar">
      <span className="agent-shell-backend" data-testid="agent-pi-status">
        {label(t, 'shell.piBackend')}
        {catalog?.available === false ? ` · ${label(t, 'agent.unavailable')}` : ''}
        {authenticated ? ` · ${modelLabel}` : ''}
      </span>
      <Status tone={statusTone}>{statusLabel}</Status>
      {busy && <button type="button" onClick={abort}>{label(t, 'agent.stopResponse')}</button>}
      <button type="button" onClick={() => { resetChat().catch(() => {}) }}>{label(t, 'shell.newChat')}</button>
      {running && <button type="button" onClick={stop}>{label(t, 'agent.endSession')}</button>}
    </div>
  ) : null

  const skillEntries = skills.map(name => ({
    name,
    meta: SKILL_META[name] || { group: 'integrate', step: 0, titleKey: name, detailKey: name },
  }))
  const skillGroups = SKILL_GROUPS.map(group => ({
    ...group,
    items: skillEntries.filter(item => item.meta.group === group.id),
  })).filter(group => group.items.length > 0)

  const shortcuts = skills.length > 0 ? (
    <div className="harness-shortcuts pi-skills-list" role="list">
      {skillGroups.map(group => (
        <section key={group.id} className="pi-skills-group" aria-labelledby={`pi-skills-${group.id}`}>
          <header className="pi-skills-group-head">
            <h3 id={`pi-skills-${group.id}`}>{label(t, group.labelKey)}</h3>
            <span>{label(t, group.detailKey)}</span>
          </header>
          <div className="pi-skills-group-items">
            {group.items.map(({ name, meta }) => (
              <button
                key={name}
                type="button"
                role="listitem"
                className={[
                  'pi-skills-item',
                  name === 'candidate-reader' && candidateUrl === '' && onCandidateUrlRequired ? 'needs-input' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => {
                  setSkillsOpen(false)
                  useSkill(name)
                }}
              >
                <span className="pi-skills-step" aria-hidden="true">{meta.step || '·'}</span>
                <span className="pi-skills-copy">
                  <strong>{meta.titleKey === name ? name : label(t, meta.titleKey)}</strong>
                  <span>{meta.detailKey === name ? `/skill:${name}` : label(t, meta.detailKey)}</span>
                  <code>{`/skill:${name}`}</code>
                </span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  ) : null

  const suggestionRow = (
    <div className="pi-chat-suggestion-row" role="list">
      {suggestions.map(item => (
        <button
          key={item.id}
          type="button"
          role="listitem"
          disabled={composerDisabled}
          onClick={() => runSuggestion(item)}
        >
          {label(t, item.labelKey)}
        </button>
      ))}
    </div>
  )

  const chatLog = (
    <div className="pi-chat-log" aria-live="polite">
      {chat.messages.length > 0 && <div className="pi-chat-date">{label(t, 'agent.today')}</div>}
      {!chat.messages.length && <div className="pi-chat-empty">
        {shell ? (
          <>
            <h2 className="pi-chat-greeting">
              {label(t, greetingKey())}
            </h2>
            <span>{hosted ? label(t, 'agent.emptyHosted') : label(t, 'agent.emptyLocal')}</span>
          </>
        ) : (
          <>
            <b>{hosted ? label(t, 'agent.emptyHosted') : label(t, 'agent.emptyLocal')}</b>
            <span>{label(t, 'agent.emptyHint')}</span>
            <div className="pi-chat-suggestions">
              {suggestions.map(item => <button key={item.id} type="button" disabled={composerDisabled} onClick={() => runSuggestion(item)}>
                {label(t, item.labelKey)}
              </button>)}
            </div>
          </>
        )}
      </div>}
      {chat.messages.map((message, index) => <article key={`${message.role}-${index}`} className={`pi-message ${message.role}`}>
        <header>
          <span>{message.role === 'user' ? label(t, 'agent.you') : 'π'}</span>
          {message.role === 'assistant' && <b>{message.streaming ? label(t, 'agent.working') : label(t, 'agent.pi')}</b>}
        </header>
        <div>
          {message.thinking && <details><summary>{label(t, 'agent.reasoning')}</summary><pre>{message.thinking}</pre></details>}
          <p>{message.content || (message.streaming ? '…' : '')}</p>
        </div>
      </article>)}
      {chat.tools.slice(-8).map(tool => <div key={tool.id} className={`pi-tool ${tool.status}`}>
        <div className="pi-tool-mark" aria-hidden="true">/</div>
        <span><strong>{tool.name}</strong><small>{label(t, 'agent.activity')}</small></span>
        <Status tone={tool.isError ? 'danger' : tool.status === 'running' ? 'running' : 'success'}>{tool.status}</Status>
        {tool.args && Object.keys(tool.args).length > 0 && <details className="pi-tool-args">
          <summary>{label(t, 'agent.toolArgs')}</summary>
          <code>{JSON.stringify(tool.args)}</code>
        </details>}
      </div>)}
      <div ref={endRef} />
    </div>
  )

  const composer = (
    <form className="pi-chat-composer" onSubmit={event => { event.preventDefault(); catchSend(sendMessage(draft)) }}>
      {shell ? <div className="pi-chat-composer-inner">
        {skillsOpen && skills.length > 0 && (
          <div className="pi-composer-skills" data-testid="agent-skills-menu" role="dialog" aria-label={label(t, 'agent.skills')}>
            <div className="pi-composer-skills-head">
              <div>
                <b>{label(t, 'agent.skills')}</b>
                <span>{label(t, 'agent.skillsHint')}</span>
              </div>
              <button type="button" onClick={() => setSkillsOpen(false)}>{label(t, 'agent.closeSkills')}</button>
            </div>
            {shortcuts}
          </div>
        )}
        <div className="pi-chat-composer-field">
          <textarea
            value={draft}
            disabled={composerDisabled}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Escape' && skillsOpen) {
                event.preventDefault()
                setSkillsOpen(false)
                return
              }
              if (event.key === '/' && !event.nativeEvent.isComposing && !draft && skills.length > 0) {
                event.preventDefault()
                setSkillsOpen(true)
                return
              }
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                catchSend(sendMessage(draft))
              }
            }}
            placeholder={label(t, authenticated ? 'agent.placeholder' : 'agent.placeholderNeedModel')}
            rows="2"
            aria-label={label(t, 'agent.placeholder')}
          />
          <div className="pi-chat-composer-actions">
            <button className="pi-chat-send" disabled={sendDisabled} type="submit" aria-label={label(t, 'agent.send')}>
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" />
              </svg>
            </button>
          </div>
          <div className="pi-chat-composer-tools">
            {skills.length > 0 ? (
              <button type="button" aria-expanded={skillsOpen} onClick={() => setSkillsOpen(value => !value)}>
                / {label(t, 'agent.skills')}
              </button>
            ) : <span />}
            <button
              type="button"
              className="pi-chat-model-pill"
              disabled={catalog?.available === false}
              onClick={openAuth}
            >
              {authenticated ? modelLabel : label(t, 'agent.connectModel')}
            </button>
          </div>
        </div>
        {isEmpty && suggestionRow}
        <div className="pi-chat-footnote">{label(t, 'shell.chatFootnote')}</div>
      </div> : <>
        <textarea
          value={draft}
          disabled={composerDisabled}
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              catchSend(sendMessage(draft))
            }
          }}
          placeholder={authenticated ? label(t, 'agent.placeholder') : label(t, 'agent.placeholderNeedModel')}
          rows="3"
        />
        <button className="button primary" disabled={sendDisabled} type="submit">{label(t, 'agent.send')}</button>
      </>}
    </form>
  )

  return <section className={shellClass} data-testid={shell ? 'agent-shell-chat' : undefined}>
    {!shell && <div className={`agent-harness-head${embedded ? ' agent-harness-head-compact' : ''}`}>
      <div>
        {!embedded && <strong>{label(t, 'agent.title')}</strong>}
        <span className="agent-session-detail">{sessionDetail}</span>
      </div>
      <div>
        <Status tone={statusTone}>{statusLabel}</Status>
        {busy && <button className="button agent-cancel" type="button" onClick={abort}>{label(t, 'agent.stopResponse')}</button>}
        <button className="button primary" type="button" disabled={catalog?.available === false} onClick={openAuth}>
          {authenticated ? label(t, 'agent.switchModel') : label(t, 'agent.connectModel')}
        </button>
        {running && <button className="button secondary" type="button" onClick={stop}>{label(t, 'agent.endSession')}</button>}
      </div>
    </div>}

    {shell ? (
      <>
        <div className="agent-shell-scroll" data-testid="agent-shell-scroll">
          {toolbar}
          {chatLog}
          <div className="agent-shell-scroll-spacer" aria-hidden="true" />
        </div>
        {composer}
      </>
    ) : (
      <>
        {shortcuts}
        {chatLog}
        {composer}
      </>
    )}
    {chat.error && <p className="error-banner">{chat.error}</p>}
    <PiAuthDialog open={authOpen} state={auth} send={sendCommand} onClose={() => setAuthOpen(false)} t={t} embedded={embedded || shell} />
  </section>
}
