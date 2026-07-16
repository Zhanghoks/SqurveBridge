import ActorWorkflow from './ActorWorkflow.jsx'
import IntegrationProvenance from './IntegrationProvenance.jsx'
import {
  DATABASES,
  METHODS,
  buildConnections,
  buildReadyKeys,
  configKey,
} from './model.js'

const pointY = index => 42 + index * 48

export default function ConnectionComposer({
  selectedMethods,
  selectedDatabases,
  focusedMethod,
  focusedDatabase,
  onFocusConnection,
  configs,
  focusedConfig,
  t,
}) {
  const readyKeys = buildReadyKeys(configs)
  const focusedKey = configKey(focusedMethod, focusedDatabase)
  const connections = buildConnections(selectedMethods, selectedDatabases)

  return <section id="compose" className="flow-module flow-glass connection-composer">
    <header className="flow-module-header">
      <div>
        <span>{t('process.compose')}</span>
        <h2>{t('compose.title')}</h2>
        <p>{t('compose.description')}</p>
      </div>
    </header>

    <div className="flow-compose-grid">
      <div className="connection-matrix">
        <h3>{t('compose.matrixLabel')}</h3>
        <div className="connection-axis" aria-hidden="true">
          <span>{t('compose.methods')}</span>
          <span>{t('compose.databases')}</span>
        </div>
        <div className="flow-connection-graph">
          <ol className="flow-graph-nodes flow-method-nodes" aria-hidden="true">
            {METHODS.map(method => <li key={method}>{method}</li>)}
          </ol>
          <svg
            viewBox="0 0 1000 420"
            preserveAspectRatio="none"
            role="img"
            aria-labelledby="flow-matrix-title flow-matrix-description"
          >
            <title id="flow-matrix-title">{t('compose.matrixTitle')}</title>
            <desc id="flow-matrix-description">{t('compose.matrixDescription')}</desc>
            {METHODS.flatMap((method, methodIndex) => DATABASES.map((database, databaseIndex) => {
              const key = configKey(method, database)
              const selected = selectedMethods.includes(method) && selectedDatabases.includes(database)
              return <path
                key={key}
                className={[
                  readyKeys.has(key) ? 'ready' : 'unavailable',
                  selected ? 'selected' : '',
                  focusedKey === key ? 'focused' : '',
                ].filter(Boolean).join(' ')}
                d={`M 0 ${pointY(methodIndex)} C 330 ${pointY(methodIndex)}, 670 ${pointY(databaseIndex)}, 1000 ${pointY(databaseIndex)}`}
              />
            }))}
          </svg>
          <ol className="flow-graph-nodes flow-database-nodes" aria-hidden="true">
            {DATABASES.map(database => <li key={database}>{database}</li>)}
          </ol>
        </div>
      </div>
      <ActorWorkflow focusedConfig={focusedConfig} t={t} />
    </div>

    <div className="selected-connections">
      {connections.map(connection => <button
        key={connection.key}
        type="button"
        aria-label={t('compose.focusConnection', {
          method: connection.method,
          database: connection.database,
        })}
        aria-pressed={focusedKey === connection.key}
        className={readyKeys.has(connection.key) ? 'ready' : 'unavailable'}
        onClick={() => onFocusConnection(connection.method, connection.database)}
      >
        <strong>{connection.method}</strong>
        <span aria-hidden="true">→</span>
        <strong>{connection.database}</strong>
      </button>)}
    </div>

    <IntegrationProvenance focusedConfig={focusedConfig} t={t} />
  </section>
}
