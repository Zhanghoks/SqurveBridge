import { workflowStages } from './model.js'

export default function ActorWorkflow({ focusedConfig, t }) {
  const stages = workflowStages(focusedConfig)

  return <div className="actor-workflow" data-testid="actor-workflow">
    <h3>{t('compose.actorWorkflow')}</h3>
    {stages.length
      ? <ol>
        {stages.map((stage, index) => <li key={stage.id || `${stage.type || 'stage'}-${index}`}>
          <span>{stage.id || String(index + 1)}</span>
          {stage.type && <small>{stage.type}</small>}
          {stage.actor && <strong>{stage.actor}</strong>}
        </li>)}
      </ol>
      : <p>{t('compose.noWorkflow')}</p>}
  </div>
}
