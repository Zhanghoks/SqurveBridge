import { useState } from 'react'
import CatalogCard from './CatalogCard.jsx'
import FlashcardDialog from './FlashcardDialog.jsx'
import { DATABASE_CATALOG, METHOD_CATALOG } from './catalog.js'

export default function ConfigurationStudio({
  hostedReadOnly = true,
  t,
}) {
  const [flashcard, setFlashcard] = useState(null)

  return (
    <section
      id="configure"
      className="flow-module flow-glass configuration-studio configuration-studio-compact"
    >
      <header className="flow-module-header">
        <div>
          <span>{t('process.configure')}</span>
          <h2>{t('configure.title')}</h2>
          <p>{t(hostedReadOnly ? 'configure.hostedDescription' : 'configure.description')}</p>
        </div>
      </header>

      <aside className="studio-guide studio-guide-inline" data-testid="studio-guide">
        <div className="studio-guide-copy">
          <span>{t('configure.guideEyebrow')}</span>
          <strong>{t('configure.guideTitle')}</strong>
        </div>
        <ol>
          <li>{t('configure.guideStepBrowse')}</li>
          <li>{t('configure.guideStepFlashcard')}</li>
          <li>{t('configure.guideStepCompose')}</li>
        </ol>
        <p>{t('configure.composeHint')}</p>
      </aside>

      <div className="catalog-workspaces catalog-workspaces-stack" data-testid="catalog-workspaces">
        <section
          className="catalog-workspace catalog-workspace-methods"
          aria-labelledby="catalog-methods-title"
        >
          <header>
            <h3 id="catalog-methods-title">{t('configure.methods')}</h3>
            <p>{t('configure.methodsLead')}</p>
          </header>
          <div className="catalog-card-list">
            {METHOD_CATALOG.map(entry => (
              <CatalogCard
                key={entry.name}
                name={entry.name}
                teaser={t(`catalog.method.${entry.slug}.teaser`)}
                openLabel={t('catalog.openMethodFlashcard', { name: entry.name })}
                onOpenFlashcard={() => setFlashcard({ kind: 'method', entry })}
              />
            ))}
          </div>
        </section>

        <section
          className="catalog-workspace catalog-workspace-databases"
          aria-labelledby="catalog-databases-title"
        >
          <header>
            <h3 id="catalog-databases-title">{t('configure.databases')}</h3>
            <p>{t('configure.databasesLead')}</p>
          </header>
          <div className="catalog-card-list">
            {DATABASE_CATALOG.map(entry => (
              <CatalogCard
                key={entry.name}
                name={entry.name}
                teaser={t(`catalog.database.${entry.slug}.teaser`)}
                openLabel={t('catalog.openDatabaseFlashcard', { name: entry.name })}
                onOpenFlashcard={() => setFlashcard({ kind: 'database', entry })}
              />
            ))}
          </div>
        </section>
      </div>

      <FlashcardDialog
        open={Boolean(flashcard)}
        kind={flashcard?.kind}
        entry={flashcard?.entry}
        t={t}
        onClose={() => setFlashcard(null)}
      />
    </section>
  )
}
