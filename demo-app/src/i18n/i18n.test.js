import assert from 'node:assert/strict'
import test from 'node:test'

import { detectLocale, translate } from './index.js'
import enUS from './en-US.js'
import zhCN from './zh-CN.js'

test('detects Chinese only for zh browser locales and honors stored locale', () => {
  assert.equal(detectLocale('zh-CN', null), 'zh-CN')
  assert.equal(detectLocale('en-US', null), 'en-US')
  assert.equal(detectLocale('en-US', 'zh-CN'), 'zh-CN')
})

test('translates parameters and falls back to English', () => {
  assert.equal(translate('zh-CN', 'header.configCount', { count: 64 }), '64 个规范配置')
  assert.equal(translate('zh-CN', 'missing.key'), 'missing.key')
  assert.equal(translate('invalid', 'process.configure'), 'Configure')
})

test('keeps staging and accessibility keys shared across both dictionaries', () => {
  for (const key of [
    'process.ariaLabel',
    'run.stagingEmpty',
    'diagnose.persistedEmpty',
    'improve.persistedEmpty',
    'boot.loading',
    'boot.error',
  ]) {
    assert.ok(Object.hasOwn(enUS, key), `missing English key ${key}`)
    assert.ok(Object.hasOwn(zhCN, key), `missing Chinese key ${key}`)
  }
  assert.deepEqual(Object.keys(enUS).sort(), Object.keys(zhCN).sort())
})
