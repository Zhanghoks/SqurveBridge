import Archive from '../Archive.jsx'
import { FlowEmpty, FlowPageHeading, FlowStatus } from './flowUi.jsx'

export default function ArchiveWorkspace({ api, onOpenInVisualize, t }) {
  return (
    <section id="archive" className="flow-module flow-glass archive-workspace-flow" data-testid="archive-workspace">
      <header className="flow-module-header">
        <div>
          <span>{t('process.archive')}</span>
          <h2>{t('archive.title')}</h2>
          <p>{t('archive.description')}</p>
        </div>
      </header>
      <Archive
        embedded
        api={api}
        Status={FlowStatus}
        PageHeading={FlowPageHeading}
        Empty={FlowEmpty}
        onOpenInVisualize={onOpenInVisualize}
        t={t}
      />
    </section>
  )
}
