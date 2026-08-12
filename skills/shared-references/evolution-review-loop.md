# Evolution Review Loop Contract

The review loop is how Meta-Evo iterates *review -> revise -> re-review until
good enough* before spending evaluation budget or human attention. The agent
protocol lives in `skills/evolve-review/SKILL.md`; the deterministic ledger
and verdict rule live in `reproduce/evolve/review.py` with the thin CLI
`tools/evolve_review.py`. Neither side may duplicate the other.

## Where the Loop Sits in Meta-Evo

| Gate | Target | When |
|---|---|---|
| Candidate gate | `change-plan` + `patch` per node | after CANDIDATE GENERATION, **before** smoke evaluation |
| Profile gate | `weakness-profile` | after WEAKNESS, before candidate generation |
| Report gate | `comparison-report` / `evaluator-report` | before USER REVIEW |
| Harness gate | `skill-doc` | when the loop is used to improve the harness itself |

Evaluation budget (smoke/bounded/full) may only be spent on candidates whose
review verdict is `approve`. Human review receives only reports whose review
verdict is `approve`, plus anything `escalate`d.

## Ledger

`review-state.json` is the only fact source for a review. It records:

- `rounds`: every completed review pass, its reviewer identity, and the
  finding ids that pass introduced.
- `findings`: id, severity (`blocker`/`major`/`minor`/`nit`), category,
  location, summary, recommendation, status (`open`/`resolved`/`waived`),
  opening/closing round, resolution text.
- `status` / `verdict`: `in_review`+`revise`, `approved`, or `escalated`.

Skeleton: `templates/evolution/review-state.json`. When the review belongs to
an evolution run, every CLI mutation also appends to `process-events.jsonl`
and the artifact manifest via `--evolve-dir`.

## Verdict Rule (implemented once, in `review.py`)

- `revise`: open blocker/major findings remain and rounds are left.
- `approve`: no open blocker/major findings **and** the latest completed
  round introduced zero new blocker/major findings (a clean re-review after
  the last fix; `clean_rounds_required`, default 1). Minor/nit findings never
  block approval but stay on record.
- `escalate`: `max_rounds` (default 5) exhausted while blocking findings are
  open. Escalation stops the loop and hands the target plus open findings to
  the human gate.

Waiving a blocker/major finding requires an explicit human decision
(`--human-approved`); the ledger records `waived_by_human`.

## Phase Recording

When all candidate reviews reach `approve`, the run records the
`candidates_reviewed` phase; when the report review passes, it records
`report_reviewed` (`reproduce/evolve/state_machine.py`). Gate discovery is
deterministic: `review.collect_review_gates` scans the run directory and
`review.candidate_gate_blockers` lists nodes that are unreviewed or not yet
approved — a missing ledger blocks the funnel just like an open blocker.

## Reviewer Independence

A review round must be an adversarial pass, not the author grading itself in
the same breath: use a fresh subagent (preferred) or a separate pass that
re-reads the target from disk against the rubric. Zero-finding rounds must
document per-rubric evidence in `round-<n>-notes.md`.

## Anti-Goals

- No second verdict implementation in skills or tools.
- No "reviewed in chat" claims without a recorded round.
- No unbounded loops: the ceiling is `max_rounds`, then a human decides.
