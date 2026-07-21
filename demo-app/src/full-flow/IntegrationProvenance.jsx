import { useState } from 'react'
import { workflowStages } from './model.js'

export default function IntegrationProvenance({ focusedConfig, t }) {
  const [expanded, setExpanded] = useState(true)
  const stages = workflowStages(focusedConfig)
  const candidate = focusedConfig?.integration?.candidate || focusedConfig?.integration_candidate
  const manifest = focusedConfig?.integration?.manifest || focusedConfig?.integration_manifest
  const configPath = focusedConfig?.config_path || ''
  const hasStages = stages.length > 0
  const hasExtras = Boolean(candidate || manifest || configPath || hasStages)

  if (!hasExtras) {
    return (
      <section className="integration-provenance integration-provenance-empty">
        <p>{t('compose.provenanceEmpty')}</p>
      </section>
    )
  }

  return (
    <section className="integration-provenance" data-expanded={expanded ? 'true' : 'false'}>
      <button
        type="button"
        className="integration-provenance-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded(value => !value)}
      >
        <span>
          <small>{t('compose.provenanceEyebrow')}</small>
          <strong>{t('compose.behind')}</strong>
        </span>
        <em aria-hidden="true">{expanded ? '−' : '+'}</em>
      </button>

      <div hidden={!expanded} data-testid="integration-provenance" className="integration-provenance-body">
        {hasStages ? (
          <div className="integration-provenance-pipeline">
            <h4>{t('compose.integrationPipeline')}</h4>
            <ol>
              {stages.map((stage, index) => (
                <li key={`${stage.actor || stage.type || 'stage'}-${index}`}>
                  <span aria-hidden="true">{index + 1}</span>
                  <div>
                    <strong>{stage.actor || t('status.unavailable')}</strong>
                    <small>{stage.type || t('status.unavailable')}</small>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        <dl className="integration-provenance-facts">
          {configPath ? (
            <div>
              <dt>{t('compose.integrationConfig')}</dt>
              <dd><code title={configPath}>{configPath}</code></dd>
            </div>
          ) : null}
          {candidate ? (
            <div>
              <dt>{t('compose.integrationCandidate')}</dt>
              <dd>{candidate}</dd>
            </div>
          ) : null}
          {manifest ? (
            <div>
              <dt>{t('compose.integrationManifest')}</dt>
              <dd>{manifest}</dd>
            </div>
          ) : null}
          {!configPath && !candidate && !manifest && !hasStages ? (
            <div>
              <dt>{t('compose.integrationConfig')}</dt>
              <dd>{t('status.unavailable')}</dd>
            </div>
          ) : null}
        </dl>
      </div>
    </section>
  )
}
