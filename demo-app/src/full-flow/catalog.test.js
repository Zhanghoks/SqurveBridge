import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DATABASE_CATALOG,
  METHOD_CATALOG,
  getDatabaseCatalogEntry,
  getMethodCatalogEntry,
} from './catalog.js'
import { DATABASES, METHODS } from './model.js'

test('catalog covers the complete method and database matrix names', () => {
  assert.deepEqual(METHOD_CATALOG.map(item => item.name), METHODS)
  assert.deepEqual(DATABASE_CATALOG.map(item => item.name), DATABASES)
  assert.equal(getMethodCatalogEntry('E-SQL')?.paperUrl, 'https://arxiv.org/abs/2409.16751')
  assert.equal(getDatabaseCatalogEntry('Spider')?.sourceUrl, 'https://github.com/taoyds/spider')
  assert.equal(getMethodCatalogEntry('C3SQL')?.sourceUrl, null)
})
