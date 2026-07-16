import assert from 'node:assert/strict'
import test from 'node:test'

import { detectLocale, translate } from './index.js'

test('detects Chinese only for zh browser locales and honors stored locale', () => {
  assert.equal(detectLocale('zh-CN', null), 'zh-CN')
  assert.equal(detectLocale('en-US', null), 'en-US')
  assert.equal(detectLocale('en-US', 'zh-CN'), 'zh-CN')
})

test('translates parameters and falls back to English', () => {
  assert.equal(translate('zh-CN', 'header.configCount', { count: 64 }), '64 个可运行配置')
  assert.equal(translate('zh-CN', 'missing.key'), 'missing.key')
  assert.equal(translate('invalid', 'process.configure'), 'Configure')
})
