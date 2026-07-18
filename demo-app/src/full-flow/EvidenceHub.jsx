import { useState } from 'react'
import Archive from '../Archive.jsx'
import ExperimentBoard from '../ExperimentBoard.jsx'
import { FlowEmpty, FlowPageHeading, FlowStatus } from './flowUi.jsx'

export default function EvidenceHub({
  pageId,
  initialTab = 'visualize',
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
  onNavigate,
  onOpenInVisualize,
}) {
  const [tab, setTab] = useState(archiveFocusRunId ? 'visualize' : initialTab)
  const sectionId = pageId || initialTab
  const titleKey = initialTab === 'archive' ? 'archive.title' : 'visualize.title'
  const descriptionKey = initialTab === 'archive' ? 'archive.description' : 'visualize.description'
  const initialMethods = selectedMethods.length
    ? selectedMethods.map(item => String(item).toLowerCase())
    : focusedConfig?.method
      ? [String(focusedConfig.method).toLowerCase()]
      : undefined
  const openRun = runId => {
    setTab('visualize')
    onOpenInVisualize?.(runId)
    onNavigate?.('visualize')
    window.dispatchEvent(new window.CustomEvent('squrve:archive-focus', { detail: runId }))
  }

  return (
    <section
      id={sectionId}
      className={`flow-module flow-glass evidence-hub ${
        tab === 'archive' ? 'archive-workspace-flow' : 'visualize-workspace'
      }`}
      data-testid={tab === 'archive' ? 'archive-workspace' : 'visualize-workspace'}
    >
      <header className="flow-module-header">
        <div>
          <span>{t(`process.${initialTab}`)}</span>
          <h2>{t(titleKey)}</h2>
          <p>{t(descriptionKey)}</p>
        </div>
        {archiveFocusRunId && tab === 'visualize' ? (
          <button type="button" className="flow-secondary-action" onClick={onClearArchiveFocus}>
            {t('visualize.clearArchiveFocus')}
          </button>
        ) : null}
        <div className="evidence-hub-tabs" role="tablist" aria-label={t(titleKey)}>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'visualize'}
            className={tab === 'visualize' ? 'active' : ''}
            onClick={() => { setTab('visualize'); onNavigate?.('visualize') }}
          >
            {t('process.visualize')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'archive'}
            className={tab === 'archive' ? 'active' : ''}
            onClick={() => { setTab('archive'); onNavigate?.('archive') }}
          >
            {t('process.archive')}
          </button>
        </div>
      </header>
      {tab === 'archive' ? (
        <Archive
          embedded
          allowFileContent={capabilities?.deployment?.target !== 'hf-space'}
          api={api}
          Status={FlowStatus}
          PageHeading={FlowPageHeading}
          Empty={FlowEmpty}
          onOpenInVisualize={openRun}
          t={t}
        />
      ) : (
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
      )}
    </section>
  )
}
