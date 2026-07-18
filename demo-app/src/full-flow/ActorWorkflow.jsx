import { workflowStages } from './model.js'

export default function ActorWorkflow({ focusedConfig, t, testId = 'actor-workflow' }) {
  const stages = workflowStages(focusedConfig)

  return (
    <div className="flow-actor-workflow" data-testid={testId}>
      <h3>{t('compose.actorWorkflow')}</h3>
      {stages.length ? (
        <ol>
          {stages.map((stage, index) => (
            <li key={stage.id || `${stage.type || 'stage'}-${index}`}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div className="flow-actor-step-body">
                {stage.id ? <code>{stage.id}</code> : null}
                {stage.type ? <small>{stage.type}</small> : null}
                {stage.actor ? <strong>{stage.actor}</strong> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p>{t('compose.noWorkflow')}</p>
      )}
    </div>
  )
}
