import { useState } from 'react'
import CatalogCard from './CatalogCard.jsx'
import ConfigureAgentPanel from './ConfigureAgentPanel.jsx'
import FlashcardDialog from './FlashcardDialog.jsx'
import { DATABASE_CATALOG, METHOD_CATALOG } from './catalog.js'

export default function ConfigurationStudio({
  selectedMethods,
  selectedDatabases,
  selectedConnections,
  focusedMethod,
  focusedDatabase,
  focusedConfig,
  configs,
  databases,
  onToggleMethod,
  onToggleDatabase,
  sampleLimit,
  sampleMode,
  sampleSeed,
  onSampleLimitChange,
  onSampleModeChange,
  onSampleSeedChange,
  sqlAuth,
  api,
  postJson,
  hostedReadOnly = true,
  t,
}) {
  const [flashcard, setFlashcard] = useState(null)
  const connections = selectedConnections || []
  const matches = (config, method, database) =>
    String(config.method).toLowerCase().replaceAll('_', '-') === method.toLowerCase().replaceAll(' ', '-')
    && String(config.dataset).toLowerCase() === database.toLowerCase()
  const configBacked = connections.filter(({ method, database }) =>
    configs.some(config => matches(config, method, database)),
  ).length
  const liveDatabaseIds = new Set(databases.map(database => String(database.id).toLowerCase()))
  const hasLiveDatabase = database => liveDatabaseIds.has(database.toLowerCase())
    || databases.some(item => String(item.benchmark || '').toLowerCase() === database.toLowerCase())
  const liveRunnable = sqlAuth?.configured
    ? connections.filter(({ method, database }) =>
      hasLiveDatabase(database) && configs.some(config => matches(config, method, database)),
    ).length
    : 0

  return <section id="configure" className="flow-module flow-glass configuration-studio">
    <header className="flow-module-header">
      <div>
        <span>{t('process.configure')}</span>
        <h2>{t('configure.title')}</h2>
        <p>{t(hostedReadOnly ? 'configure.hostedDescription' : 'configure.description')}</p>
      </div>
    </header>

    <div className="configure-controls-row">
      <fieldset>
        <legend>{t('configure.model')}</legend>
        <p>{sqlAuth?.configured
          ? `${sqlAuth.provider || ''}${sqlAuth.model ? ` · ${sqlAuth.model}` : ''}`
          : t('status.unavailable')}</p>
      </fieldset>
      <fieldset className="configuration-sampling">
        <legend>{t('configure.sampling')}</legend>
        <label>
          {t('configure.sampleLimit')}
          <input
            type="number"
            min="1"
            value={sampleLimit}
            onChange={event => onSampleLimitChange(Number(event.target.value))}
          />
        </label>
        <label>
          {t('configure.sampleMode')}
          <select value={sampleMode} onChange={event => onSampleModeChange(event.target.value)}>
            <option value="slice">{t('configure.sampleSlice')}</option>
            <option value="random">{t('configure.sampleRandom')}</option>
          </select>
        </label>
        <label>
          {t('configure.sampleSeed')}
          <input
            type="number"
            value={sampleSeed}
            onChange={event => onSampleSeedChange(Number(event.target.value))}
          />
        </label>
      </fieldset>
    </div>

    <div className="flow-configuration-layout">
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
                selected={selectedMethods.includes(entry.name)}
                focused={focusedMethod === entry.name}
                selectLabel={t('configure.selectMethod', { name: entry.name })}
                openLabel={t('catalog.openMethodFlashcard', { name: entry.name })}
                onToggleSelect={() => onToggleMethod(entry.name)}
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
                selected={selectedDatabases.includes(entry.name)}
                focused={focusedDatabase === entry.name}
                selectLabel={t('configure.selectDatabase', { name: entry.name })}
                openLabel={t('catalog.openDatabaseFlashcard', { name: entry.name })}
                onToggleSelect={() => onToggleDatabase(entry.name)}
                onOpenFlashcard={() => setFlashcard({ kind: 'database', entry })}
              />
            ))}
          </div>
        </section>
      </div>

      <aside className="focused-configuration" data-testid="focused-configuration">
        <span>{t('configure.focused')}</span>
        <strong>{focusedMethod} → {focusedDatabase}</strong>
        <dl>
          <div>
            <dt>{t('configure.selectedConnections')}</dt>
            <dd>{connections.length}</dd>
          </div>
          <div>
            <dt>{t('configure.configBacked')}</dt>
            <dd>{configBacked}</dd>
          </div>
          <div>
            <dt>{t('configure.liveRunnable')}</dt>
            <dd>{liveRunnable}</dd>
          </div>
          <div>
            <dt>{t('configure.databaseAsset')}</dt>
            <dd>{hasLiveDatabase(focusedDatabase) ? t('status.ready') : t('status.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('configure.sqlAuth')}</dt>
            <dd>{sqlAuth?.configured ? t('status.ready') : t('status.unavailable')}</dd>
          </div>
        </dl>
        {focusedConfig
          ? <code>{focusedConfig.config_path}</code>
          : <small>{t('status.unavailable')}</small>}
        <p className="configure-compose-hint">{t('configure.composeHint')}</p>
      </aside>
    </div>

    {api && postJson && <ConfigureAgentPanel
      api={api}
      postJson={postJson}
      hostedReadOnly={hostedReadOnly}
      t={t}
    />}

    <FlashcardDialog
      open={Boolean(flashcard)}
      kind={flashcard?.kind}
      entry={flashcard?.entry}
      selected={flashcard
        ? (flashcard.kind === 'method'
          ? selectedMethods.includes(flashcard.entry.name)
          : selectedDatabases.includes(flashcard.entry.name))
        : false}
      t={t}
      onClose={() => setFlashcard(null)}
      onToggleSelect={name => {
        if (flashcard?.kind === 'method') onToggleMethod(name)
        else onToggleDatabase(name)
      }}
    />
  </section>
}
