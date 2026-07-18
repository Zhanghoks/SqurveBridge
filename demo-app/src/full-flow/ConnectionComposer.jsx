import { useState } from 'react'
import ActorWorkflow from './ActorWorkflow.jsx'
import IntegrationProvenance from './IntegrationProvenance.jsx'
import {
  DATABASES,
  METHODS,
  buildReadyKeys,
  configKey,
  hasConnection,
} from './model.js'

const pointY = index => 36 + index * 52

function ConnectionSwitcher({
  connections,
  focusedKey,
  readyKeys,
  focusedIndex,
  t,
  onFocusConnection,
  onRemoveConnection,
}) {
  if (!connections.length) {
    return <p className="compose-switcher-empty">{t('compose.noConnections')}</p>
  }

  return (
    <div className="compose-connection-switcher" data-testid="compose-connection-switcher">
      <div className="compose-switcher-toolbar">
        <span>{t('compose.viewingWorkflow')}</span>
        <div className="compose-switcher-nav">
          <button
            type="button"
            aria-label={t('compose.prevConnection')}
            disabled={connections.length < 2}
            onClick={() => {
              const previous = connections[(focusedIndex - 1 + connections.length) % connections.length]
              onFocusConnection(previous.method, previous.database)
            }}
          >
            ‹
          </button>
          <strong>
            {t('compose.connectionIndex', {
              current: focusedIndex + 1,
              total: connections.length,
            })}
          </strong>
          <button
            type="button"
            aria-label={t('compose.nextConnection')}
            disabled={connections.length < 2}
            onClick={() => {
              const next = connections[(focusedIndex + 1) % connections.length]
              onFocusConnection(next.method, next.database)
            }}
          >
            ›
          </button>
        </div>
      </div>
      <div className="compose-switcher-list" role="listbox" aria-label={t('compose.selectedConnections')}>
        {connections.map(connection => {
          const active = focusedKey === connection.key
          const ready = readyKeys.has(connection.key)
          return (
            <div
              key={connection.key}
              className={[
                'compose-switcher-item',
                active ? 'active' : '',
                ready ? 'ready' : 'unavailable',
              ].filter(Boolean).join(' ')}
              role="option"
              aria-selected={active}
            >
              <button
                type="button"
                className="compose-switcher-focus"
                aria-label={t('compose.focusConnection', {
                  method: connection.method,
                  database: connection.database,
                })}
                aria-pressed={active}
                onClick={() => onFocusConnection(connection.method, connection.database)}
              >
                <strong>{connection.method}</strong>
                <span aria-hidden="true"> → </span>
                <strong>{connection.database}</strong>
                {!ready && <em>{t('compose.browsable')}</em>}
              </button>
              <button
                type="button"
                className="compose-switcher-remove"
                aria-label={t('compose.removeConnection', {
                  method: connection.method,
                  database: connection.database,
                })}
                onClick={() => onRemoveConnection(connection.method, connection.database)}
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ConnectionComposer({
  selectedMethods,
  selectedDatabases,
  selectedConnections,
  focusedMethod,
  focusedDatabase,
  onToggleMethod,
  onToggleDatabase,
  onToggleConnection,
  onFocusConnection,
  configs,
  focusedConfig,
  t,
}) {
  const readyKeys = buildReadyKeys(configs)
  const focusedKey = configKey(focusedMethod, focusedDatabase)
  const connections = selectedConnections || []
  const focusedIndex = Math.max(0, connections.findIndex(item => item.key === focusedKey))
  const [hovered, setHovered] = useState(null)

  const handleEdgeActivate = (method, database) => {
    const selected = hasConnection(connections, method, database)
    const key = configKey(method, database)
    if (!selected) {
      onToggleConnection(method, database)
      return
    }
    if (focusedKey === key) {
      onToggleConnection(method, database)
      return
    }
    onFocusConnection(method, database)
  }

  const orderedEdges = METHODS.flatMap((method, methodIndex) =>
    DATABASES.map((database, databaseIndex) => ({
      method,
      database,
      methodIndex,
      databaseIndex,
      key: configKey(method, database),
      selected: hasConnection(connections, method, database),
    })),
  ).sort((left, right) => {
    const leftFocused = left.key === focusedKey ? 1 : 0
    const rightFocused = right.key === focusedKey ? 1 : 0
    if (leftFocused !== rightFocused) return leftFocused - rightFocused
    const leftSelected = left.selected ? 1 : 0
    const rightSelected = right.selected ? 1 : 0
    return leftSelected - rightSelected
  })

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
        <div className="connection-matrix-header">
          <h3>{t('compose.matrixLabel')}</h3>
          <p>{t('compose.matrixHint')}</p>
        </div>
        <div className="connection-axis" aria-hidden="true">
          <span>{t('compose.methods')}</span>
          <span>{t('compose.databases')}</span>
        </div>
        <div className="flow-connection-graph" data-has-selection={connections.length > 0 ? 'true' : 'false'}>
          <ol className="flow-graph-nodes flow-method-nodes">
            {METHODS.map(method => <li key={method}>
              <button
                type="button"
                aria-label={t('compose.selectMethod', { name: method })}
                aria-pressed={selectedMethods.includes(method)}
                className={[
                  selectedMethods.includes(method) ? 'selected' : '',
                  focusedMethod === method ? 'focused' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => onToggleMethod(method)}
              >
                {method}
              </button>
            </li>)}
          </ol>
          <div className="flow-connection-canvas">
            <svg
              viewBox="0 0 1000 440"
              preserveAspectRatio="none"
              role="group"
              aria-labelledby="flow-matrix-title flow-matrix-description"
            >
              <title id="flow-matrix-title">{t('compose.matrixTitle')}</title>
              <desc id="flow-matrix-description">{t('compose.matrixDescription')}</desc>
              {orderedEdges.map(({ method, database, methodIndex, databaseIndex, key, selected }) => {
                const path = `M 0 ${pointY(methodIndex)} C 330 ${pointY(methodIndex)}, 670 ${pointY(databaseIndex)}, 1000 ${pointY(databaseIndex)}`
                const focused = focusedKey === key
                const className = [
                  readyKeys.has(key) ? 'ready' : 'unavailable',
                  selected ? 'selected' : '',
                  focused ? 'focused' : '',
                ].filter(Boolean).join(' ')
                return <g key={key} className="flow-connection-hit">
                  <path
                    className="flow-connection-hitarea"
                    d={path}
                    onClick={() => handleEdgeActivate(method, database)}
                    onMouseEnter={() => setHovered({ method, database, selected, focused })}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered({ method, database, selected, focused })}
                    onBlur={() => setHovered(null)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        handleEdgeActivate(method, database)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    aria-label={t('compose.toggleConnection', {
                      method,
                      database,
                    })}
                    aria-pressed={selected}
                  />
                  <path
                    className={className}
                    d={path}
                    pointerEvents="none"
                  />
                </g>
              })}
            </svg>
            {hovered ? (
              <div className="flow-connection-tooltip" role="status">
                <strong>{hovered.method}</strong>
                <span aria-hidden="true">→</span>
                <strong>{hovered.database}</strong>
                <em>
                  {hovered.focused
                    ? t('compose.tooltipFocused')
                    : hovered.selected
                      ? t('compose.tooltipFocus')
                      : t('compose.tooltipConnect')}
                </em>
              </div>
            ) : null}
          </div>
          <ol className="flow-graph-nodes flow-database-nodes">
            {DATABASES.map(database => <li key={database}>
              <button
                type="button"
                aria-label={t('compose.selectDatabase', { name: database })}
                aria-pressed={selectedDatabases.includes(database)}
                className={[
                  selectedDatabases.includes(database) ? 'selected' : '',
                  focusedDatabase === database ? 'focused' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => onToggleDatabase(database)}
              >
                {database}
              </button>
            </li>)}
          </ol>
        </div>
      </div>

      <aside className="compose-workflow-panel" data-testid="compose-workflow-panel">
        <ConnectionSwitcher
          connections={connections}
          focusedKey={focusedKey}
          readyKeys={readyKeys}
          focusedIndex={focusedIndex}
          t={t}
          onFocusConnection={onFocusConnection}
          onRemoveConnection={onToggleConnection}
        />
        <ActorWorkflow focusedConfig={focusedConfig} t={t} />
        <IntegrationProvenance focusedConfig={focusedConfig} t={t} />
      </aside>
    </div>
  </section>
}
