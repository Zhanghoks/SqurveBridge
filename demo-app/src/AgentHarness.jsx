import { useEffect, useRef, useState } from 'react'
import PiAuthDialog from './PiAuthDialog.jsx'
import { appendUserMessage, applyPiEvent, createPiChatState, skillPrompt } from './piChat.js'
import { applyPiAuthEvent, createPiAuthState } from './piAuth.js'

const DEFAULT_SKILLS = ['candidate-reader', 'integration-pipeline', 'config-adapter', 'run', 'meta-evo']

export default function AgentHarness({ api, postJson, Status, candidateUrl = '', onCandidateReaderStart, onCandidateUrlRequired, queuedCommand = null, onQueuedCommandSent }) {
  const socketRef = useRef(null)
  const sessionRef = useRef(null)
  const handledCommandRef = useRef('')
  const endRef = useRef(null)
  const [catalog, setCatalog] = useState(null)
  const [chat, setChat] = useState(createPiChatState)
  const [auth, setAuth] = useState(createPiAuthState)
  const [authOpen, setAuthOpen] = useState(false)
  const [draft, setDraft] = useState('')

  const receive = event => {
    try {
      const payload = JSON.parse(event.data)
      setChat(current => applyPiEvent(current, payload))
      setAuth(current => applyPiAuthEvent(current, payload))
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
    if (name === 'candidate-reader') {
      if (!candidateUrl) { onCandidateUrlRequired?.(); return }
      onCandidateReaderStart?.()
      return
    }
    sendMessage(skillPrompt(name)).catch(error => setChat(current => ({ ...current, error: error.message })))
  }

  useEffect(() => {
    let active = true
    api('/api/agent').then(data => {
      if (!active) return
      setCatalog(data)
      setChat(current => ({ ...current, profile: data.profile || '', provider: data.provider || '', model: data.model || '', skills: data.skills || [] }))
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

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' }) }, [chat.messages, chat.tools])

  const skills = chat.skills.length ? chat.skills.filter(name => DEFAULT_SKILLS.includes(name)) : DEFAULT_SKILLS
  const running = ['starting', 'thinking', 'ready'].includes(chat.status) && Boolean(sessionRef.current)
  const busy = chat.status === 'thinking'
  const authenticated = Boolean(auth.selectedModel)
  const modelLabel = authenticated ? `${auth.selectedModel.provider}/${auth.selectedModel.id}` : ''

  return <section className="tool-panel agent-harness pi-chat">
    <div className="agent-harness-head">
      <div><strong>Pi Agent · Native SqurveBridge backend</strong><span>{modelLabel || (catalog?.available ? 'Authentication required' : 'Embedded Pi build required')} · {chat.profile || 'checking profile'}</span></div>
      <div><Status tone={chat.error || auth.error ? 'danger' : busy ? 'running' : authenticated ? 'success' : 'neutral'}>{busy ? 'Pi working' : authenticated ? 'authenticated' : chat.status}</Status>{busy && <button className="button agent-cancel" onClick={abort}>Stop response</button>}<button className="button primary" disabled={catalog?.available === false} onClick={openAuth}>{authenticated ? 'Switch model' : 'Login to Pi'}</button>{running && <button className="button secondary" onClick={stop}>End session</button>}</div>
    </div>
    <div className="harness-shortcuts">{skills.map(name => <button key={name} className={name === 'candidate-reader' && !candidateUrl ? 'needs-input' : ''} onClick={() => useSkill(name)}>{`/skill:${name}`}</button>)}</div>
    <div className="pi-chat-log" aria-live="polite">
      {!chat.messages.length && <div className="pi-chat-empty"><b>{chat.profile === 'hosted-readonly' ? 'Ask Pi to explain the repository or inspect published evidence.' : 'Ask Pi to inspect, integrate, reproduce, or evaluate.'}</b><span>Project Skills are loaded directly from <code>skills/</code>. Public sessions can only read bundled project files; trusted local sessions can edit and run commands.</span></div>}
      {chat.messages.map((message, index) => <article key={`${message.role}-${index}`} className={`pi-message ${message.role}`}><header>{message.role === 'user' ? 'You' : 'Pi'}</header>{message.thinking && <details><summary>Reasoning</summary><pre>{message.thinking}</pre></details>}<p>{message.content || (message.streaming ? '…' : '')}</p></article>)}
      {chat.tools.slice(-8).map(tool => <div key={tool.id} className={`pi-tool ${tool.status}`}><span>{tool.name}</span><code>{JSON.stringify(tool.args)}</code><Status tone={tool.isError ? 'danger' : tool.status === 'running' ? 'running' : 'success'}>{tool.status}</Status></div>)}
      <div ref={endRef} />
    </div>
    <form className="pi-chat-composer" onSubmit={event => { event.preventDefault(); sendMessage(draft).catch(error => setChat(current => ({ ...current, error: error.message }))) }}>
      <textarea value={draft} disabled={!authenticated || busy} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(draft).catch(error => setChat(current => ({ ...current, error: error.message }))) } }} placeholder="Message Pi or use a Skill…" rows="3" />
      <button className="button primary" disabled={!authenticated || !draft.trim() || busy} type="submit">Send</button>
    </form>
    {chat.error && <p className="error-banner">{chat.error}</p>}
    <PiAuthDialog open={authOpen} state={auth} send={sendCommand} onClose={() => setAuthOpen(false)} />
  </section>
}
