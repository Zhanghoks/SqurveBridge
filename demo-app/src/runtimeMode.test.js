import test from 'node:test'
import assert from 'node:assert/strict'
import { deploymentTarget, featureEnabled } from './runtimeMode.js'

test('defaults to the complete local Demo App', () => {
  assert.equal(deploymentTarget(null), 'local')
  assert.equal(featureEnabled(null, 'agent_terminals'), true)
})

test('uses hosted features returned by Flask', () => {
  const capabilities = {
    deployment: {
      target: 'hf-space',
      features: { live_sql: true, agent_terminals: false, live_evaluation: false },
    },
  }
  assert.equal(deploymentTarget(capabilities), 'hf-space')
  assert.equal(featureEnabled(capabilities, 'live_sql'), true)
  assert.equal(featureEnabled(capabilities, 'agent_terminals'), false)
})
