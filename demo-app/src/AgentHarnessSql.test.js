import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from './testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen } = await import('@testing-library/react')
const userEvent = (await import('@testing-library/user-event')).default
const unregister = register()

const { MessageBody } = await import('./AgentHarness.jsx')

const t = key => ({
  'agent.sendToWorkspace': 'Send to Query workspace',
  'agent.sqlCopy': 'Copy',
  'agent.sqlCopied': 'Copied',
  'agent.sqlStreaming': 'Receiving SQL…',
}[key] || key)

test.afterEach(cleanup)
test.after(() => {
  unregister()
  closeDom()
})

test('renders assistant sql blocks with copy and adopt actions', async () => {
  const adopted = []
  render(React.createElement(MessageBody, {
    message: {
      role: 'assistant',
      content: 'Try this:\n```sql\nSELECT name FROM singer\n```\nIt lists singers.',
    },
    onAdoptSql: sql => adopted.push(sql),
    t,
  }))

  assert.ok(screen.getByTestId('pi-sql-block'))
  assert.match(screen.getByTestId('pi-sql-block').textContent, /SELECT name FROM singer/)
  assert.ok(screen.getByText('Try this:'))
  assert.ok(screen.getByText('It lists singers.'))

  await userEvent.setup().click(screen.getByRole('button', { name: 'Send to Query workspace' }))
  assert.deepEqual(adopted, ['SELECT name FROM singer'])
})

test('keeps streaming sql blocks action-free and plain messages untouched', () => {
  render(React.createElement(MessageBody, {
    message: { role: 'assistant', content: 'Generating…\n```sql\nSELECT count(*' },
    onAdoptSql: () => {},
    t,
  }))
  assert.match(screen.getByTestId('pi-sql-block').textContent, /SELECT count\(\*/)
  assert.ok(screen.getByText('Receiving SQL…'))
  assert.equal(screen.queryByRole('button', { name: 'Send to Query workspace' }), null)
  cleanup()

  render(React.createElement(MessageBody, {
    message: { role: 'assistant', content: 'No SQL here.' },
    t,
  }))
  assert.equal(screen.queryByTestId('pi-sql-block'), null)
  assert.ok(screen.getByText('No SQL here.'))
})

test('does not offer workspace adoption for user-authored sql', () => {
  render(React.createElement(MessageBody, {
    message: { role: 'user', content: '```sql\nSELECT 1\n```' },
    onAdoptSql: () => {},
    t,
  }))
  assert.ok(screen.getByTestId('pi-sql-block'))
  assert.equal(screen.queryByRole('button', { name: 'Send to Query workspace' }), null)
  assert.ok(screen.getByRole('button', { name: 'Copy' }))
})
