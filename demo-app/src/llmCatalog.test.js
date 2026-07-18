import assert from 'node:assert/strict'
import test from 'node:test'

import { OFFICIAL_LLM_MODELS, officialModelsFor } from './llmCatalog.js'

test('official catalog excludes custom active model ids', () => {
  assert.deepEqual(officialModelsFor('qwen'), [
    'qwen-turbo',
    'qwen-plus',
    'qwen-max',
    'deepseek-v4-flash',
  ])
  assert.equal(officialModelsFor('qwen').includes('qwen3-custom-latest'), false)
  assert.deepEqual(Object.keys(OFFICIAL_LLM_MODELS).sort(), [
    'claude',
    'deepseek',
    'gemini',
    'openai',
    'qwen',
    'zhipu',
  ])
})
