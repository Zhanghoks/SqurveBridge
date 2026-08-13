import { memo, useCallback, useMemo, useState } from 'react'
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

// Memoized so hover-driven parent renders skip the (potentially heavy)
// workflow/provenance panels whose props stay stable while hovering.
const MemoActorWorkflow = memo(ActorWorkflow)
const MemoIntegrationProvenance = memo(IntegrationProvenance)

const ConnectionSwitcher = memo(function ConnectionSwitcher({
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
})

// One curve (hit area + visible stroke). Memoized so hovering a node only
// re-renders the handful of edges whose highlight state actually changes,
// instead of all method × database pairs on every mouse event.
const GraphEdge = memo(function GraphEdge({
  method,
  database,
  methodIndex,
  databaseIndex,
  selected,
  focused,
  ready,
  nodeHover,
  label,
  onActivate,
  onHoverEdge,
}) {
  const path = `M 0 ${pointY(methodIndex)} C 330 ${pointY(methodIndex)}, 670 ${pointY(databaseIndex)}, 1000 ${pointY(databaseIndex)}`
  const className = [
    ready ? 'ready' : 'unavailable',
    selected ? 'selected' : '',
    focused ? 'focused' : '',
    nodeHover ? 'node-hover' : '',
  ].filter(Boolean).join(' ')
  return <g className="flow-connection-hit">
    <path
      className="flow-connection-hitarea"
      d={path}
      onClick={() => onActivate(method, database)}
      onMouseEnter={() => onHoverEdge(method, database)}
      onMouseLeave={() => onHoverEdge(null)}
      onFocus={() => onHoverEdge(method, database)}
      onBlur={() => onHoverEdge(null)}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onActivate(method, database)
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={label}
      aria-pressed={selected}
    />
    <path
      className={className}
      d={path}
      pathLength="1"
      pointerEvents="none"
    />
  </g>
})

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
  const readyKeys = useMemo(() => buildReadyKeys(configs), [configs])
  const focusedKey = configKey(focusedMethod, focusedDatabase)
  const connections = useMemo(() => selectedConnections || [], [selectedConnections])
  const focusedIndex = Math.max(0, connections.findIndex(item => item.key === focusedKey))
  const [hovered, setHovered] = useState(null)
  const [hoveredNode, setHoveredNode] = useState(null)

  const nodeTouchesHoveredEdge = name =>
    Boolean(hovered && (hovered.method === name || hovered.database === name))
  const nodeLinkedToHoveredNode = (name, side) => {
    if (!hoveredNode || hoveredNode.side === side) return false
    return connections.some(connection => (side === 'method'
      ? connection.method === name && connection.database === hoveredNode.name
      : connection.database === name && connection.method === hoveredNode.name))
  }

  const handleEdgeActivate = useCallback((method, database) => {
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
  }, [connections, focusedKey, onToggleConnection, onFocusConnection])

  const handleEdgeHover = useCallback((method, database) => {
    setHovered(method ? { method, database } : null)
  }, [])

  const edgeTouchesHoveredNode = edge =>
    Boolean(hoveredNode && (hoveredNode.side === 'method'
      ? edge.method === hoveredNode.name
      : edge.database === hoveredNode.name))

  // Paint order: plain < selected < focused. Hover no longer reorders the
  // DOM, so hovering never restarts CSS transitions or moves SVG nodes.
  const orderedEdges = useMemo(() => {
    const paintRank = edge => {
      if (edge.key === focusedKey) return 2
      if (edge.selected) return 1
      return 0
    }
    return METHODS.flatMap((method, methodIndex) =>
      DATABASES.map((database, databaseIndex) => ({
        method,
        database,
        methodIndex,
        databaseIndex,
        key: configKey(method, database),
        selected: hasConnection(connections, method, database),
      })),
    ).sort((left, right) => paintRank(left) - paintRank(right))
  }, [connections, focusedKey])

  const hoveredSelected = hovered
    ? hasConnection(connections, hovered.method, hovered.database)
    : false
  const hoveredFocused = hovered
    ? configKey(hovered.method, hovered.database) === focusedKey
    : false

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
        <div
          className="flow-connection-graph"
          data-has-selection={connections.length > 0 ? 'true' : 'false'}
          data-node-hover={hoveredNode ? 'true' : 'false'}
        >
          <ol className="flow-graph-nodes flow-method-nodes">
            {METHODS.map(method => <li key={method}>
              <button
                type="button"
                aria-label={t('compose.selectMethod', { name: method })}
                aria-pressed={selectedMethods.includes(method)}
                className={[
                  selectedMethods.includes(method) ? 'selected' : '',
                  focusedMethod === method ? 'focused' : '',
                  nodeTouchesHoveredEdge(method) ? 'edge-peer' : '',
                  nodeLinkedToHoveredNode(method, 'method') ? 'peer-linked' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => onToggleMethod(method)}
                onMouseEnter={() => setHoveredNode({ side: 'method', name: method })}
                onMouseLeave={() => setHoveredNode(null)}
                onFocus={() => setHoveredNode({ side: 'method', name: method })}
                onBlur={() => setHoveredNode(null)}
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
              <defs>
                {/* userSpaceOnUse keeps gradients visible on horizontal paths
                    whose bounding box would otherwise collapse to zero height. */}
                <linearGradient id="flow-edge-selected-gradient" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1000" y2="0">
                  <stop offset="0" stopColor="#a5794b" />
                  <stop offset=".5" stopColor="#e6c391" />
                  <stop offset="1" stopColor="#a5794b" />
                </linearGradient>
                <linearGradient id="flow-edge-focused-gradient" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1000" y2="0">
                  <stop offset="0" stopColor="#d4a574" />
                  <stop offset=".5" stopColor="#f6e0bd" />
                  <stop offset="1" stopColor="#d4a574" />
                </linearGradient>
              </defs>
              {orderedEdges.map(edge => (
                <GraphEdge
                  key={edge.key}
                  method={edge.method}
                  database={edge.database}
                  methodIndex={edge.methodIndex}
                  databaseIndex={edge.databaseIndex}
                  selected={edge.selected}
                  focused={edge.key === focusedKey}
                  ready={readyKeys.has(edge.key)}
                  nodeHover={edgeTouchesHoveredNode(edge)}
                  label={t('compose.toggleConnection', {
                    method: edge.method,
                    database: edge.database,
                  })}
                  onActivate={handleEdgeActivate}
                  onHoverEdge={handleEdgeHover}
                />
              ))}
            </svg>
            {hovered ? (
              <div className="flow-connection-tooltip" role="status">
                <strong>{hovered.method}</strong>
                <span aria-hidden="true">→</span>
                <strong>{hovered.database}</strong>
                <em>
                  {hoveredFocused
                    ? t('compose.tooltipFocused')
                    : hoveredSelected
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
                  nodeTouchesHoveredEdge(database) ? 'edge-peer' : '',
                  nodeLinkedToHoveredNode(database, 'database') ? 'peer-linked' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => onToggleDatabase(database)}
                onMouseEnter={() => setHoveredNode({ side: 'database', name: database })}
                onMouseLeave={() => setHoveredNode(null)}
                onFocus={() => setHoveredNode({ side: 'database', name: database })}
                onBlur={() => setHoveredNode(null)}
              >
                {database}
              </button>
            </li>)}
          </ol>
        </div>
        <div className="connection-graph-legend">
          <span className="legend-item is-selected">{t('compose.legendSelected')}</span>
          <span className="legend-item is-focused">{t('compose.legendFocused')}</span>
          <span className="legend-item is-browsable">{t('compose.legendBrowsable')}</span>
          <p>{t('compose.graphTip')}</p>
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
        <MemoActorWorkflow focusedConfig={focusedConfig} t={t} />
        <MemoIntegrationProvenance focusedConfig={focusedConfig} t={t} />
      </aside>
    </div>
  </section>
}
