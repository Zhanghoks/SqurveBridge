import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DATABASES,
  METHODS,
  buildConnections,
  buildReadyKeys,
  configKey,
  resolveFocusedConfig,
  workflowStages,
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
