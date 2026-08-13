import assert from 'node:assert/strict'
import test from 'node:test'

import { OFFICIAL_LLM_MODELS, modelsForProvider, officialModelsFor } from './llmCatalog.js'

test('bundled catalog covers every configurable provider', () => {
  assert.deepEqual(Object.keys(OFFICIAL_LLM_MODELS).sort(), [
    'claude',
    'deepseek',
    'gemini',
    'openai',
    'qwen',
    'zhipu',
  ])
  assert.equal(officialModelsFor('qwen').includes('qwen3-custom-latest'), false)
  assert.deepEqual(officialModelsFor('nonexistent'), [])
})

test('prefers the model catalog the backend resolved from the Pi SDK', () => {
  const entry = { id: 'deepseek', models: ['deepseek-v4-flash', 'deepseek-v4-pro'] }
  assert.deepEqual(modelsForProvider(entry, 'deepseek'), ['deepseek-v4-flash', 'deepseek-v4-pro'])
})

test('falls back to the bundled catalog when the backend sends no models', () => {
  assert.deepEqual(modelsForProvider({ id: 'qwen', models: [] }, 'qwen'), officialModelsFor('qwen'))
  assert.deepEqual(modelsForProvider(undefined, 'qwen'), officialModelsFor('qwen'))
  assert.deepEqual(modelsForProvider({ id: 'qwen' }, undefined), officialModelsFor('qwen'))
})
