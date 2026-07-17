import assert from 'node:assert/strict'
import test from 'node:test'
import { register as registerLoader } from 'node:module'
import React from 'react'
import { register } from 'tsx/esm/api'
import { installTestDom } from '../testDom.js'

const closeDom = installTestDom()
globalThis.React = React
const { cleanup, render, screen } = await import('@testing-library/react')
registerLoader('../cssTestLoader.mjs', import.meta.url)
const unregister = register()

const { default: DiagnosisWorkspace } = await import('./DiagnosisWorkspace.jsx')
const { default: ImprovementWorkspace } = await import('./ImprovementWorkspace.jsx')
const { useEvidence } = await import('./useEvidence.js')

const labels = {
  'diagnose.title': 'Weakness Diagnosis',
  'diagnose.loading': 'Loading persisted diagnosis evidence.',
  'diagnose.loadError': 'Diagnosis evidence could not be loaded.',
  'diagnose.empty': 'A persisted score bundle is required.',
  'diagnose.errorRoots': 'Top Error Roots',
  'diagnose.hardness': 'Hardness',
  'diagnose.components': 'SQL Components',
  'diagnose.stages': 'Actor Stages',
  'diagnose.latency': 'Cost and Latency',
  'diagnose.samples': 'Samples',
  'improve.title': 'Bounded Improvement',
  'improve.loading': 'Loading persisted improvement evidence.',
  'improve.loadError': 'Improvement evidence could not be loaded.',
  'improve.empty': 'A persisted improvement record is required.',
  'improve.baseline': 'Baseline',
  'improve.weakness': 'Weakness Profile',
  'improve.candidate': 'Candidate Change',
  'improve.smoke': 'Smoke',
  'improve.bounded': 'Bounded Evaluation',
  'improve.confirmation': 'Confirmation',
  'improve.review': 'Human Review',
}

function EvidenceHarness({ api, selection }) {
  const evidence = useEvidence(api, selection)
  const t = key => labels[key] || key
  return React.createElement(React.Fragment, null,
    React.createElement(DiagnosisWorkspace, { evidence, t }),
    React.createElement(ImprovementWorkspace, { evidence, t }),
  )
}

function renderEvidence({ api, selection }) {
  return render(React.createElement(EvidenceHarness, { api, selection }))
}

test.afterEach(cleanup)

test.after(() => {
  unregister()
  closeDom()
})

test('does not synthesize diagnosis or improvement without artifacts', async () => {
  renderEvidence({ api: async () => ({ runs: [] }) })

  assert.ok(await screen.findByText('A persisted score bundle is required.'))
  assert.ok(screen.getByText('A persisted improvement record is required.'))
  assert.equal(screen.queryByText('schema linking'), null)
})

test('distinguishes loading from a real artifact-empty response', async () => {
  let resolveRequest
  const pending = new Promise(resolve => {
    resolveRequest = resolve
  })
  renderEvidence({ api: () => pending })

  assert.ok(screen.getByText('Loading persisted diagnosis evidence.'))
  assert.ok(screen.getByText('Loading persisted improvement evidence.'))
  assert.equal(screen.queryByText('A persisted score bundle is required.'), null)

  resolveRequest({ runs: [] })
  assert.ok(await screen.findByText('A persisted score bundle is required.'))
})

test('shows load failure when both evidence sources fail or api is missing', async () => {
  const first = renderEvidence({ api: async () => { throw new Error('offline') } })
  assert.ok(await screen.findByText('Diagnosis evidence could not be loaded.'))
  assert.ok(screen.getByText('Improvement evidence could not be loaded.'))
  assert.equal(screen.queryByText('A persisted score bundle is required.'), null)
  first.unmount()

  renderEvidence({})
  assert.ok(await screen.findByText('Diagnosis evidence could not be loaded.'))
  assert.ok(screen.getByText('Improvement evidence could not be loaded.'))
})

test('uses the available evidence source when the other source fails', async () => {
  const api = async path => {
    if (path.includes('comparisons')) throw new Error('comparison unavailable')
    return {
      runs: [{
        errors: { execution_error: 1 },
      }],
    }
  }

  renderEvidence({ api })

  assert.ok(await screen.findByText('Top Error Roots'))
  assert.equal(screen.queryByText('Diagnosis evidence could not be loaded.'), null)
})

test('renders only persisted diagnostic fields from the selected comparison run', async () => {
  const api = async path => path.includes('comparisons')
    ? {
      runs: [{
        errors: { execution_error: 2 },
        by_hardness: { hard: { ex: 0.5 } },
        by_sql_feature: { group_by: { ex: 0.25 } },
        stage_metrics: { SchemaLinking: { sl_recall: 0.8 } },
        latency: { p95_s: 1.2 },
        samples: [{
          instance_id: 'dev_1',
          db_id: 'synthetic_inventory',
          hardness: 'hard',
          ex: 0,
          error_root: 'execution_error',
          error_sub: 'missing_column',
          sl_recall: 0.5,
          act_elapsed_s: 0.9,
        }],
        question: 'private question',
      }],
    }
    : { runs: [] }

  renderEvidence({ api })

  assert.ok(await screen.findByText('Top Error Roots'))
  const diagnosis = document.querySelector('#diagnose').textContent
  for (const value of ['execution_error', 'hard', 'group_by', 'SchemaLinking', '1.2', 'dev_1']) {
    assert.match(diagnosis, new RegExp(value))
  }
  assert.doesNotMatch(diagnosis, /private question/)
})

test('renders improvement only from backend weakness_profile and evolution_record fields', async () => {
  const api = async path => path.includes('comparisons')
    ? {
      runs: [{
        weakness_profile: { summary: 'schema linking' },
        evolution_record: {
          baseline: { artifact: 'scores.json' },
          candidate_change: { status: 'recorded' },
          smoke: { status: 'passed' },
          hidden_stage: { status: 'invented' },
        },
      }],
    }
    : { runs: [] }

  renderEvidence({ api })

  assert.ok(await screen.findByText('Weakness Profile'))
  const improvement = document.querySelector('#improve').textContent
  for (const value of ['Baseline', 'Weakness Profile', 'Candidate Change', 'Smoke', 'schema linking']) {
    assert.match(improvement, new RegExp(value))
  }
  assert.doesNotMatch(improvement, /hidden_stage|invented/)
})

test('requests focused persisted evidence and labels archive fallback as independent history', async () => {
  const requested = []
  const api = async path => {
    requested.push(path)
    if (path.includes('comparisons')) return { runs: [] }
    return { runs: [{
      run_id: 'archive-7',
      method: 'dinsql',
      dataset: 'bird',
      split: 'dev',
      source: 'evidence',
      errors: { execution_error: 1 },
    }] }
  }
  renderEvidence({
    api,
    selection: { method: 'dinsql', dataset: 'bird', split: 'dev', sampleMode: 'slice', sampleLimit: 20 },
  })
  assert.ok(await screen.findByText('evidence.historicalArchive'))
  assert.match(requested[0], /methods=dinsql/)
  assert.match(requested[0], /dataset=bird/)
  assert.match(document.querySelector('#diagnose').textContent, /archive-7.*dinsql.*bird/s)
  assert.ok(screen.getAllByText('evidence.independent').length >= 1)
})
