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
  'diagnose.empty': 'A persisted score bundle is required.',
  'diagnose.errorRoots': 'Top Error Roots',
  'diagnose.hardness': 'Hardness',
  'diagnose.components': 'SQL Components',
  'diagnose.stages': 'Actor Stages',
  'diagnose.latency': 'Cost and Latency',
  'diagnose.samples': 'Samples',
  'improve.title': 'Bounded Improvement',
  'improve.empty': 'A persisted improvement record is required.',
  'improve.baseline': 'Baseline',
  'improve.weakness': 'Weakness Profile',
  'improve.candidate': 'Candidate Change',
  'improve.smoke': 'Smoke',
  'improve.bounded': 'Bounded Evaluation',
  'improve.confirmation': 'Confirmation',
  'improve.review': 'Human Review',
}

function EvidenceHarness({ api }) {
  const evidence = useEvidence(api)
  const t = key => labels[key] || key
  return React.createElement(React.Fragment, null,
    React.createElement(DiagnosisWorkspace, { evidence, t }),
    React.createElement(ImprovementWorkspace, { evidence, t }),
  )
}

function renderEvidence({ api }) {
  return render(React.createElement(EvidenceHarness, { api }))
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
          db_id: 'concert_singer',
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

test('renders improvement only from explicit weakness and evolution records', async () => {
  const api = async path => path.includes('comparisons')
    ? {
      runs: [{
        weakness: { summary: 'schema linking' },
        evolution: {
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
