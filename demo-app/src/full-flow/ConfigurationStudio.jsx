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

      <div className="flow-configuration-layout studio-explain-layout">
        <div className="catalog-workspaces" data-testid="catalog-workspaces">
          <section className="catalog-workspace" aria-labelledby="catalog-methods-title">
            <header>
              <h3 id="catalog-methods-title">{t('configure.methods')}</h3>
              <p>{t('catalog.methodsHint')}</p>
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

          <section className="catalog-workspace" aria-labelledby="catalog-databases-title">
            <header>
              <h3 id="catalog-databases-title">{t('configure.databases')}</h3>
              <p>{t('catalog.databasesHint')}</p>
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

        <aside className="studio-guide" data-testid="studio-guide">
          <span>{t('configure.guideEyebrow')}</span>
          <strong>{t('configure.guideTitle')}</strong>
          <ol>
            <li>{t('configure.guideStepBrowse')}</li>
            <li>{t('configure.guideStepFlashcard')}</li>
            <li>{t('configure.guideStepCompose')}</li>
          </ol>
          <p>{t('configure.composeHint')}</p>
        </aside>
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
