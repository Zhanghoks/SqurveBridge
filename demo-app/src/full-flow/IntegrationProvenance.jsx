import { useState } from 'react'
import { workflowStages } from './model.js'

const joinPresent = values => values.filter(Boolean).join(' · ')

export default function IntegrationProvenance({ focusedConfig, t }) {
  const [expanded, setExpanded] = useState(false)
  const stages = workflowStages(focusedConfig)
  const actors = joinPresent(stages.map(stage => stage.actor))
  const tasks = joinPresent(stages.map(stage => stage.type))
  const candidate = focusedConfig?.integration?.candidate || focusedConfig?.integration_candidate
  const manifest = focusedConfig?.integration?.manifest || focusedConfig?.integration_manifest

  return <div className="integration-provenance">
    <button
      type="button"
      aria-expanded={expanded}
      onClick={() => setExpanded(value => !value)}
    >
      {t('compose.behind')}
    </button>
    <div hidden={!expanded} data-testid="integration-provenance">
      <dl>
        <div>
          <dt>{t('compose.integrationCandidate')}</dt>
          <dd>{candidate || t('status.unavailable')}</dd>
        </div>
        <div>
          <dt>{t('compose.integrationManifest')}</dt>
          <dd>{manifest || t('status.unavailable')}</dd>
        </div>
        <div>
          <dt>{t('compose.integrationActors')}</dt>
          <dd>{actors || t('status.unavailable')}</dd>
        </div>
        <div>
          <dt>{t('compose.integrationTasks')}</dt>
          <dd>{tasks || t('status.unavailable')}</dd>
        </div>
        <div>
          <dt>{t('compose.integrationConfig')}</dt>
          <dd>{focusedConfig?.config_path || t('status.unavailable')}</dd>
        </div>
      </dl>
    </div>
  </div>
}
