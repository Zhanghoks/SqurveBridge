import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const AGENTS = [
  { id: 'codex', name: 'Codex' },
  { id: 'claude', name: 'Claude Code' },
]
const SKILLS = ['/candidate-reader', '/integration-pipeline', '/config-adapter', '/run', '/meta-evo']
const commandForAgent = (command, agent) => agent === 'codex' && command.startsWith('/') ? `$${command.slice(1)}` : command

export default function AgentHarness({ api, postJson, Status, candidateUrl = '', onCandidateReaderStart, onCandidateUrlRequired, queuedCommand = null, onQueuedCommandSent }) {
  const hostsRef = useRef({})
  const terminalsRef = useRef({})
  const sessionsRef = useRef({})
  const socketsRef = useRef({})
  const handledCommandRef = useRef('')
  const dispatchingCommandRef = useRef('')
  const activeAgentRef = useRef('codex')
  const [catalog, setCatalog] = useState(null)
  const [activeAgent, setActiveAgent] = useState('codex')
  const [sessions, setSessions] = useState({})
  const [phase, setPhase] = useState({ codex: 'stopped', claude: 'stopped' })
  const [error, setError] = useState('')

  const syncSessions = next => {
    sessionsRef.current = next
    setSessions(next)
  }

  const connectSocket = (agent, session) => {
    const existing = socketsRef.current[agent]
    if (existing?.readyState === WebSocket.OPEN) return Promise.resolve(existing)
    if (existing?.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        existing.addEventListener('open', () => resolve(existing), { once: true })
        existing.addEventListener('error', () => reject(new Error(`${agent} terminal connection failed.`)), { once: true })
      })
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/terminals/${session.session_id}/ws`)
    socketsRef.current[agent] = socket
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'output' && message.data) terminalsRef.current[agent]?.terminal.write(message.data)
        if (message.type === 'ready') {
          syncSessions({ ...sessionsRef.current, [agent]: { ...session, ...message, running: true } })
          setPhase(current => ({ ...current, [agent]: 'running' }))
        }
        if (message.type === 'exit') {
          syncSessions({ ...sessionsRef.current, [agent]: { ...session, ...message, running: false } })
          setPhase(current => ({ ...current, [agent]: `exited · ${message.exit_code}` }))
        }
      } catch { setError(`${agent} terminal returned an invalid message.`) }
    }
    socket.onclose = () => {
      if (socketsRef.current[agent] === socket) socketsRef.current[agent] = null
      if (sessionsRef.current[agent]?.running) {
        setPhase(current => ({ ...current, [agent]: 'reconnecting' }))
        setTimeout(() => {
          const current = sessionsRef.current[agent]
          if (current?.running && !socketsRef.current[agent]) connectSocket(agent, current).catch(err => setError(err.message))
        }, 500)
      }
    }
    return new Promise((resolve, reject) => {
      socket.addEventListener('open', () => resolve(socket), { once: true })
      socket.addEventListener('error', () => reject(new Error(`${agent} terminal connection failed.`)), { once: true })
    })
  }

  useEffect(() => {
    let disposed = false
    const disposables = []
    const observers = []

    for (const agent of AGENTS) {
      const terminal = new Terminal({
        cursorBlink: true,
        convertEol: false,
        fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        fontSize: 13,
        lineHeight: 1.22,
        scrollback: 10000,
        screenReaderMode: true,
        theme: {
          background: '#101310', foreground: '#d9dfd8', cursor: '#83d9a2', selectionBackground: '#31533d',
          black: '#171b17', red: '#e4776d', green: '#83d9a2', yellow: '#e0ad61', blue: '#72bddb', magenta: '#c995d8', cyan: '#81cbd1', white: '#d9dfd8',
          brightBlack: '#657066', brightRed: '#f09288', brightGreen: '#a0e7b8', brightYellow: '#efc47f', brightBlue: '#96d6ed', brightMagenta: '#dfafe9', brightCyan: '#a4e2e6', brightWhite: '#f1f4f0',
        },
      })
      const fit = new FitAddon()
      terminal.loadAddon(fit)
      terminal.open(hostsRef.current[agent.id])
      terminal.writeln(`\x1b[38;2;131;217;162m${agent.name} interactive terminal\x1b[0m`)
      terminal.writeln('Session stopped. Start the terminal to begin.\r\n')
      terminalsRef.current[agent.id] = { terminal, fit }

      disposables.push(terminal.onData(data => {
        if (!sessionsRef.current[agent.id]?.running) return
        const socket = socketsRef.current[agent.id]
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'input', data }))
      }))

      const observer = new ResizeObserver(() => {
        if (activeAgentRef.current !== agent.id || !hostsRef.current[agent.id]?.offsetWidth) return
        fit.fit()
        const socket = socketsRef.current[agent.id]
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }))
      })
      observer.observe(hostsRef.current[agent.id])
      observers.push(observer)
    }

    api('/api/terminals').then(data => {
      if (disposed) return
      setCatalog(data)
      const restored = Object.fromEntries(data.agents.filter(item => item.session).map(item => [item.id, item.session]))
      syncSessions(restored)
      setPhase(current => ({ ...current, ...Object.fromEntries(Object.keys(restored).map(id => [id, 'running'])) }))
      Object.entries(restored).forEach(([id, session]) => {
        terminalsRef.current[id]?.terminal.reset()
        terminalsRef.current[id]?.terminal.clear()
        terminalsRef.current[id]?.terminal.write('\x1b[2J\x1b[H')
        connectSocket(id, session).catch(err => setError(err.message))
      })
      const preferred = data.agents.find(item => item.id === 'codex' && item.available) || data.agents.find(item => item.available)
      if (preferred) setActiveAgent(preferred.id)
    }).catch(err => setError(err.message))

    return () => {
      disposed = true
      observers.forEach(observer => observer.disconnect())
      disposables.forEach(disposable => disposable.dispose())
      const activeSessions = Object.values(sessionsRef.current)
      sessionsRef.current = {}
      Object.values(socketsRef.current).forEach(socket => socket?.close())
      Object.values(terminalsRef.current).forEach(({ terminal }) => terminal.dispose())
      activeSessions.forEach(session => {
        if (session?.running) fetch(`/api/terminals/${session.session_id}/stop`, { method: 'POST', keepalive: true }).catch(() => {})
      })
      terminalsRef.current = {}
    }
  }, [])

  useEffect(() => {
    activeAgentRef.current = activeAgent
    const timer = setTimeout(() => {
      const entry = terminalsRef.current[activeAgent]
      if (!entry) return
      entry.fit.fit()
      entry.terminal.focus()
      const session = sessionsRef.current[activeAgent]
      const socket = socketsRef.current[activeAgent]
      if (session?.running && socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'resize', cols: entry.terminal.cols, rows: entry.terminal.rows }))
    }, 0)
    return () => clearTimeout(timer)
  }, [activeAgent])

  const start = async agent => {
    const existing = sessionsRef.current[agent]
    if (existing?.running) return existing
    const entry = terminalsRef.current[agent]
    if (!entry) return null
    setError('')
    setPhase(current => ({ ...current, [agent]: 'starting' }))
    entry.fit.fit()
    entry.terminal.reset()
    entry.terminal.clear()
    entry.terminal.write('\x1b[2J\x1b[H')
    try {
      const data = await postJson('/api/terminals', { agent, cols: entry.terminal.cols || 110, rows: entry.terminal.rows || 34 })
      syncSessions({ ...sessionsRef.current, [agent]: data })
      await connectSocket(agent, data)
      setPhase(current => ({ ...current, [agent]: 'running' }))
      return data
    } catch (err) {
      setError(err.message)
      setPhase(current => ({ ...current, [agent]: 'start failed' }))
      return null
    }
  }

  const stop = async agent => {
    const session = sessionsRef.current[agent]
    if (!session?.session_id) return
    try {
      const data = await postJson(`/api/terminals/${session.session_id}/stop`, {})
      syncSessions({ ...sessionsRef.current, [agent]: data })
      socketsRef.current[agent]?.close()
      setPhase(current => ({ ...current, [agent]: 'stopped' }))
    } catch (err) { setError(err.message) }
  }

  const sendCommand = async (command, submit, taskId = '') => {
    const agent = activeAgentRef.current
    const normalized = commandForAgent(command, agent)
    let session = sessionsRef.current[agent]
    const newlyStarted = !session?.running
    if (newlyStarted) session = await start(agent)
    if (!session?.running) return
    if (newlyStarted) await new Promise(resolve => setTimeout(resolve, 1000))
    const socket = await connectSocket(agent, session)
    socket.send(JSON.stringify({ type: 'input', data: `${normalized}${submit ? '\r' : ' '}` }))
    terminalsRef.current[agent]?.terminal.focus()
    if (taskId) {
      handledCommandRef.current = taskId
      dispatchingCommandRef.current = ''
      onQueuedCommandSent?.(taskId, session)
    }
  }

  useEffect(() => {
    if (!queuedCommand?.id || handledCommandRef.current === queuedCommand.id || dispatchingCommandRef.current === queuedCommand.id) return
    dispatchingCommandRef.current = queuedCommand.id
    sendCommand(queuedCommand.command, true, queuedCommand.id).catch(err => {
      dispatchingCommandRef.current = ''
      setError(err.message)
    })
  }, [queuedCommand?.id])

  const useSkill = skill => {
    if (skill === '/candidate-reader') {
      if (!candidateUrl) { onCandidateUrlRequired?.(); return }
      onCandidateReaderStart?.()
      return
    }
    sendCommand(skill, false).catch(err => setError(err.message))
  }

  const selectedInfo = catalog?.agents?.find(item => item.id === activeAgent)
  const selectedSession = sessions[activeAgent]
  const selectedPhase = phase[activeAgent]

  return <section className="tool-panel agent-harness">
    <div className="agent-harness-head"><div><strong>Agent Harness · Interactive terminals</strong><span>{catalog?.cwd || 'Checking local agents'}</span></div><div><Status tone={error ? 'danger' : selectedSession?.running ? 'running' : selectedPhase?.startsWith('exited') ? 'warning' : 'neutral'}>{selectedSession?.running ? `${selectedInfo?.name || activeAgent} running` : selectedPhase}</Status>{selectedSession?.running ? <button className="button agent-cancel" onClick={() => stop(activeAgent)}>Stop</button> : <button className="button primary" disabled={!selectedInfo?.available} onClick={() => start(activeAgent)}>Start {selectedInfo?.name || activeAgent}</button>}</div></div>
    <div className="agent-picker" role="tablist" aria-label="Interactive coding agent terminal">
      {(catalog?.agents || AGENTS).map(item => <button key={item.id} id={`agent-tab-${item.id}`} role="tab" aria-selected={activeAgent === item.id} aria-controls={`agent-panel-${item.id}`} className={activeAgent === item.id ? 'active' : ''} disabled={item.available === false} onClick={() => setActiveAgent(item.id)}><span>{item.name}</span><small>{sessions[item.id]?.running ? 'connected' : item.available === false ? 'not installed' : phase[item.id]}</small></button>)}
    </div>
    <div className="harness-shortcuts">{SKILLS.map(skill => <button key={skill} className={skill === '/candidate-reader' && !candidateUrl ? 'needs-input' : ''} onClick={() => useSkill(skill)}>{commandForAgent(skill, activeAgent)}</button>)}</div>
    <div className="agent-terminal-stage">{AGENTS.map(item => <div key={item.id} id={`agent-panel-${item.id}`} role="tabpanel" aria-labelledby={`agent-tab-${item.id}`} className="agent-terminal-panel" hidden={activeAgent !== item.id} onClick={() => terminalsRef.current[item.id]?.terminal.focus()}><div ref={node => { hostsRef.current[item.id] = node }} className="agent-terminal-host" aria-label={`${item.name} interactive terminal`} /></div>)}</div>
    {error && <p className="error-banner">{error}</p>}
  </section>
}
