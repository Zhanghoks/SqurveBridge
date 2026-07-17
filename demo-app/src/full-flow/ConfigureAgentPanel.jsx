import { lazy, Suspense, useRef, useState } from 'react'
import { normalizePublicGitHubUrl } from './model.js'

const AgentHarness = lazy(() => import('../AgentHarness.jsx'))

function FlowStatus({ tone = 'neutral', children }) {
  return <span className={`flow-status flow-status-${tone}`}><i aria-hidden="true" /><span>{children}</span></span>
}

const INTEGRATION_SKILLS = [
  ['candidate-reader', 'configure.agentSkillCandidate'],
  ['integration-pipeline', 'configure.agentSkillPipeline'],
  ['config-adapter', 'configure.agentSkillConfig'],
]

export default function ConfigureAgentPanel({ api, postJson, t, hostedReadOnly = true }) {
  const inputRef = useRef(null)
  const [candidateUrl, setCandidateUrl] = useState('')
  const [candidateError, setCandidateError] = useState('')
  const [candidatePhase, setCandidatePhase] = useState('idle')
  const [harnessTask, setHarnessTask] = useState(null)
  const [agentOpen, setAgentOpen] = useState(false)

  const normalized = normalizePublicGitHubUrl(candidateUrl)
  const githubReady = Boolean(normalized)

  const startCandidateReader = () => {
    if (!githubReady) {
      setCandidateError(t('configure.agentGithubRequired'))
      inputRef.current?.focus()
      return
    }
    setCandidateError('')
    setCandidatePhase('starting')
    setAgentOpen(true)
    setHarnessTask({
      id: `candidate-${Date.now()}`,
      command: `/skill:candidate-reader ${normalized}`,
    })
  }

  return (
    <section className="flow-agent-panel" data-testid="configure-agent-panel" aria-labelledby="configure-agent-title">
      <header className="flow-agent-header">
        <div>
          <span>{t('configure.agentEyebrow')}</span>
          <h3 id="configure-agent-title">{t(hostedReadOnly
            ? 'configure.agentHostedTitle'
            : 'configure.agentTitle')}</h3>
          <p>{t(hostedReadOnly
            ? 'configure.agentHostedDescription'
            : 'configure.agentDescription')}</p>
        </div>
        <FlowStatus tone={!hostedReadOnly && candidatePhase === 'running' ? 'running' : !hostedReadOnly && githubReady ? 'success' : 'neutral'}>
          {hostedReadOnly
            ? t('configure.agentHostedStatus')
            : candidatePhase === 'running'
            ? t('configure.agentStatusRunning')
            : githubReady
              ? t('configure.agentStatusReady')
              : t('configure.agentStatusIdle')}
        </FlowStatus>
      </header>

      {!hostedReadOnly && <div className="flow-agent-intake">
        <label className="flow-agent-field">
          <span>{t('configure.agentGithubLabel')}</span>
          <input
            ref={inputRef}
            type="url"
            value={candidateUrl}
            aria-invalid={Boolean(candidateError)}
            placeholder="https://github.com/owner/repository"
            onChange={event => {
              setCandidateUrl(event.target.value)
              setCandidateError('')
              setCandidatePhase('idle')
            }}
          />
          {candidateError && <small className="flow-agent-error">{candidateError}</small>}
        </label>
        <code>{githubReady ? `/skill:candidate-reader ${normalized}` : '/skill:candidate-reader <github-url>'}</code>
        <button type="button" className="flow-agent-primary" onClick={startCandidateReader}>
          {t('configure.agentStartReader')}
        </button>
      </div>}

      {!hostedReadOnly && <ul className="flow-agent-skill-list">
        {INTEGRATION_SKILLS.map(([name, key]) => (
          <li key={name}>
            <strong>{`/skill:${name}`}</strong>
            <span>{t(key)}</span>
          </li>
        ))}
      </ul>}

      {!agentOpen ? (
        <button
          type="button"
          className="flow-agent-open"
          onClick={() => setAgentOpen(true)}
        >
          {t('configure.agentOpenChat')}
        </button>
      ) : (
        <Suspense fallback={<div className="flow-agent-loading">{t('configure.agentLoading')}</div>}>
          <AgentHarness
            api={api}
            postJson={postJson}
            Status={FlowStatus}
            candidateUrl={!hostedReadOnly && githubReady ? normalized : ''}
            onCandidateReaderStart={hostedReadOnly ? undefined : startCandidateReader}
            onCandidateUrlRequired={() => {
              setCandidateError(t('configure.agentGithubRequired'))
              inputRef.current?.focus()
            }}
            queuedCommand={harnessTask}
            onQueuedCommandSent={id => {
              if (String(id).startsWith('candidate-')) setCandidatePhase('running')
            }}
          />
        </Suspense>
      )}
    </section>
  )
}
