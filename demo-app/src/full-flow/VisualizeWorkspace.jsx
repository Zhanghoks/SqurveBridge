import ExperimentBoard from '../ExperimentBoard.jsx'
import { FlowEmpty, FlowPageHeading, FlowStatus } from './flowUi.jsx'

export default function VisualizeWorkspace({
  capabilities,
  api,
  postJson,
  liveEvaluation = false,
  focusedConfig,
  selectedMethods = [],
  sampleLimit,
  sampleMode,
  sampleSeed,
  archiveFocusRunId = '',
  onClearArchiveFocus,
  t,
}) {
  const initialMethods = selectedMethods.length
    ? selectedMethods.map(item => String(item).toLowerCase())
    : focusedConfig?.method
      ? [String(focusedConfig.method).toLowerCase()]
      : undefined

  return (
    <section id="visualize" className="flow-module flow-glass visualize-workspace" data-testid="visualize-workspace">
      <header className="flow-module-header">
        <div>
          <span>{t('process.visualize')}</span>
          <h2>{t('visualize.title')}</h2>
          <p>{t('visualize.description')}</p>
        </div>
        {archiveFocusRunId ? (
          <button type="button" className="flow-secondary-action" onClick={onClearArchiveFocus}>
            {t('visualize.clearArchiveFocus')}
          </button>
        ) : null}
      </header>

      <ExperimentBoard
        embedded
        viewOnly
        capabilities={capabilities}
        liveEvaluation={liveEvaluation}
        api={api}
        postJson={postJson}
        Status={FlowStatus}
        PageHeading={FlowPageHeading}
        Empty={FlowEmpty}
        initialDataset={focusedConfig?.dataset}
        initialSplit={focusedConfig?.split}
        initialMethods={initialMethods}
        initialSampleLimit={sampleLimit}
        initialSampleMode={sampleMode}
        initialSampleSeed={sampleSeed}
        archiveRunId={archiveFocusRunId}
      />
    </section>
  )
}
