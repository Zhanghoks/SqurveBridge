import assert from 'node:assert/strict'
import test from 'node:test'
import {
  hasLiveRunEvidence,
  resolveInspectArtifacts,
} from './sampleRunArtifacts.js'

test('resolveInspectArtifacts stays empty until live evidence exists', () => {
  assert.equal(hasLiveRunEvidence({ phase: 'ready', sql: '', trace: [], result: null }), false)
  assert.equal(resolveInspectArtifacts({ phase: 'ready' }).source, 'empty')

  const live = resolveInspectArtifacts({
    phase: 'completed',
    sql: 'SELECT 1',
    trace: [{ actor_name: 'X' }],
    result: { columns: ['n'], rows: [[1]], row_count: 1, elapsed_ms: 2 },
  })
  assert.equal(live.source, 'live')
  assert.equal(live.sql, 'SELECT 1')
  assert.deepEqual(live.metrics, { row_count: 1, elapsed_ms: 2 })
})
