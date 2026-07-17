import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DATABASES,
  METHODS,
  buildConnections,
  buildReadyKeys,
  configKey,
  ensureConnection,
  hasConnection,
  resolveFocusedConfig,
  toggleConnection,
  toggleDatabaseConnections,
  toggleMethodConnections,
  workflowStages,
  normalizePublicGitHubUrl,
} from './model.js'

test('exports the complete 8 by 8 matrix catalog', () => {
  assert.equal(METHODS.length, 8)
  assert.equal(DATABASES.length, 8)
  assert.equal(new Set(METHODS).size, 8)
  assert.equal(new Set(DATABASES).size, 8)
})

test('normalizes reproduce configs into runnable matrix keys', () => {
  assert.equal(configKey('GPT Baseline', 'EHRSQL_2024'), 'ehrsql-2024/gpt-baseline')
  assert.deepEqual([...buildReadyKeys([
    { method: 'DINSQL', dataset: 'Spider' },
    { method: 'E-SQL', dataset: 'BIRD' },
  ])], ['spider/dinsql', 'bird/e-sql'])
})

test('builds additive many-to-many connections', () => {
  assert.deepEqual(
    buildConnections(['C3SQL', 'DINSQL'], ['Spider', 'BIRD']).map(item => item.key),
    ['spider/c3sql', 'bird/c3sql', 'spider/dinsql', 'bird/dinsql'],
  )
})

test('toggles arbitrary connections without forcing the cartesian product', () => {
  const initial = [{ method: 'C3SQL', database: 'Spider' }]
  const next = toggleConnection(initial, 'DINSQL', 'BIRD')
  assert.equal(hasConnection(next, 'C3SQL', 'Spider'), true)
  assert.equal(hasConnection(next, 'DINSQL', 'BIRD'), true)
  assert.equal(hasConnection(next, 'C3SQL', 'BIRD'), false)
  assert.deepEqual(toggleConnection(next, 'DINSQL', 'BIRD'), initial)
  assert.deepEqual(toggleConnection(initial, 'C3SQL', 'Spider'), initial)
  assert.deepEqual(
    ensureConnection(initial, 'DINSQL', 'BIRD').map(item => configKey(item.method, item.database)),
    ['spider/c3sql', 'bird/dinsql'],
  )
})

test('expands method and database toggles across the current counterpart set', () => {
  const withMethod = toggleMethodConnections([{ method: 'C3SQL', database: 'Spider' }], 'DINSQL')
  assert.deepEqual(
    withMethod.map(item => configKey(item.method, item.database)),
    ['spider/c3sql', 'spider/dinsql'],
  )
  const withDatabase = toggleDatabaseConnections(withMethod, 'BIRD')
  assert.deepEqual(
    withDatabase.map(item => configKey(item.method, item.database)),
    ['spider/c3sql', 'spider/dinsql', 'bird/c3sql', 'bird/dinsql'],
  )
})

test('resolves the focused configuration by normalized pair', () => {
  const expected = { method: 'DINSQL', dataset: 'Spider' }
  assert.equal(resolveFocusedConfig([expected], 'dinsql', 'SPIDER'), expected)
  assert.equal(resolveFocusedConfig([expected], 'C3SQL', 'Spider'), null)
})

test('resolves actor workflow from a focused config', () => {
  const config = {
    method: 'c3sql',
    dataset: 'spider',
    config_path: 'reproduce/configs/spider/c3sql.json',
    stages: [{ id: 'reduce', type: 'ReduceTask', actor: 'C3SQLReducer' }],
  }
  assert.deepEqual(workflowStages(config), [{
    id: 'reduce',
    type: 'ReduceTask',
    actor: 'C3SQLReducer',
  }])
})

test('normalizes only plain public GitHub repository URLs', () => {
  assert.equal(
    normalizePublicGitHubUrl(' https://github.com/example/repository.git '),
    'https://github.com/example/repository',
  )
  const credentialUrl = ['https://user:secret', 'github.com/example/repository'].join('@')
  for (const value of [
    'http://github.com/example/repository',
    credentialUrl,
    'https://github.com/example/repository?token=secret',
    'https://github.com/example/repository#readme',
    'https://github.com/example/repository/issues',
    'https://github.com/example/repository;run',
  ]) {
    assert.equal(normalizePublicGitHubUrl(value), '')
  }
})
