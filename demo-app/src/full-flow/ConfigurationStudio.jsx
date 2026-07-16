import { DATABASES, METHODS } from './model.js'

export default function ConfigurationStudio({
  selectedMethods,
  selectedDatabases,
  focusedMethod,
  focusedDatabase,
  focusedConfig,
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
  return <section id="configure" className="flow-module configuration-studio">
    <header className="flow-module-header">
      <div>
        <span>{t('process.configure')}</span>
        <h2>{t('configure.title')}</h2>
        <p>{t('configure.description')}</p>
      </div>
    </header>

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

    <div className="focused-configuration" data-testid="focused-configuration">
      <span>{t('configure.focused')}</span>
      <strong>{focusedMethod} → {focusedDatabase}</strong>
      {focusedConfig
        ? <code>{focusedConfig.config_path}</code>
        : <small>{t('status.unavailable')}</small>}
    </div>
  </section>
}
