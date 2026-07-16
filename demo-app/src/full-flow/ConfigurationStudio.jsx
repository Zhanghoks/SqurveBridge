import { DATABASES, METHODS } from './model.js'
import ActorWorkflow from './ActorWorkflow.jsx'

export default function ConfigurationStudio({
  selectedMethods,
  selectedDatabases,
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
  t,
}) {
  const selectedConnections = selectedMethods.length * selectedDatabases.length
  const matches = (config, method, database) =>
    String(config.method).toLowerCase().replaceAll('_', '-') === method.toLowerCase().replaceAll(' ', '-')
    && String(config.dataset).toLowerCase() === database.toLowerCase()
  const configBacked = selectedMethods.flatMap(method =>
    selectedDatabases.filter(database => configs.some(config => matches(config, method, database))),
  ).length
  const liveDatabaseIds = new Set(databases.map(database => String(database.id).toLowerCase()))
  const liveRunnable = sqlAuth?.configured
    ? selectedMethods.flatMap(method => selectedDatabases.filter(database =>
      liveDatabaseIds.has(database.toLowerCase()) && configs.some(config => matches(config, method, database)),
    )).length
    : 0
  return <section id="configure" className="flow-module flow-glass configuration-studio">
    <header className="flow-module-header">
      <div>
        <span>{t('process.configure')}</span>
        <h2>{t('configure.title')}</h2>
        <p>{t('configure.description')}</p>
      </div>
    </header>

    <div className="flow-configuration-layout">
      <div className="configuration-grid">
        <fieldset>
          <legend>{t('configure.model')}</legend>
          <p>{sqlAuth?.configured
            ? `${sqlAuth.provider || ''}${sqlAuth.model ? ` · ${sqlAuth.model}` : ''}`
            : t('status.unavailable')}</p>
        </fieldset>

        <fieldset className="configuration-methods">
          <legend>{t('configure.methods')}</legend>
          <div>
            {METHODS.map(method => <button
              key={method}
              type="button"
              aria-label={t('configure.selectMethod', { name: method })}
              aria-pressed={selectedMethods.includes(method)}
              className={`${selectedMethods.includes(method) ? 'selected' : ''}${focusedMethod === method ? ' focused' : ''}`}
              onClick={() => onToggleMethod(method)}
            >
              {method}
            </button>)}
          </div>
        </fieldset>

        <fieldset className="configuration-databases">
          <legend>{t('configure.databases')}</legend>
          <div>
            {DATABASES.map(database => <button
              key={database}
              type="button"
              aria-label={t('configure.selectDatabase', { name: database })}
              aria-pressed={selectedDatabases.includes(database)}
              className={`${selectedDatabases.includes(database) ? 'selected' : ''}${focusedDatabase === database ? ' focused' : ''}`}
              onClick={() => onToggleDatabase(database)}
            >
              {database}
            </button>)}
          </div>
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

      <aside className="focused-configuration" data-testid="focused-configuration">
        <span>{t('configure.focused')}</span>
        <strong>{focusedMethod} → {focusedDatabase}</strong>
        <dl>
          <div>
            <dt>{t('configure.selectedConnections')}</dt>
            <dd>{selectedConnections}</dd>
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
            <dd>{liveDatabaseIds.has(focusedDatabase.toLowerCase()) ? t('status.ready') : t('status.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('configure.sqlAuth')}</dt>
            <dd>{sqlAuth?.configured ? t('status.ready') : t('status.unavailable')}</dd>
          </div>
        </dl>
        {focusedConfig
          ? <code>{focusedConfig.config_path}</code>
          : <small>{t('status.unavailable')}</small>}
        <ActorWorkflow
          focusedConfig={focusedConfig}
          t={t}
          testId="configuration-actor-workflow"
        />
      </aside>
    </div>
  </section>
}
