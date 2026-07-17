# SqurveBridge Full-Flow Bilingual Demo Design

## Purpose

Redesign the hosted SqurveBridge Demo so a first-time visitor can understand and operate the verified system flow without reading repository documentation.

The primary story is:

```text
Configure
→ Compose
→ Run
→ Inspect
→ Diagnose
→ Improve
```

The Demo must present SqurveBridge as a configuration-driven, composable and evidence-backed Text-to-SQL workspace. It must not describe the current runtime as an already-trained autonomous workflow-selection system.

## Product boundaries

- The public product identity is SqurveBridge, built on the Squrve runtime.
- The hosted Demo uses real SQL generation and execution endpoints.
- Evaluation, diagnosis and bounded-improvement views may display only persisted artifacts or API data with explicit provenance.
- Every runnable Method × Database edge maps to an explicit canonical file under `reproduce/configs/<database>/<method>.json`.
- Private candidate repositories, private roadmap text, credentials, identities and submission-related information must not enter the UI.
- The first screen must not expose the previous SQL Studio, Experiment Board and Archive as three unrelated applications.

## Information architecture

The Demo is a multi-page workspace with a sticky left process rail:

```text
01 Configure
02 Compose
03 Run
04 Inspect
05 Diagnose
06 Improve
```

Clicking a rail item switches the main stage to that page. Hash routes (`#compose`, `#run`, …) stay in sync for deep links. The stage footer provides Previous / Next. On narrow viewports the rail becomes a horizontal strip above the stage.

### 01 Configure / 配置工作台

This is the first and visually dominant module.

Inputs:

- session SQL provider and custom model;
- one or more methods;
- one or more databases;
- focused Method × Database connection;
- sample size;
- sampling mode;
- random seed when applicable.

Summary:

- selected connection count;
- runnable connection count;
- focused config path;
- database asset state;
- LLM connection state;
- compact Actor workflow preview.

The configuration module uses a catalog workspace layout:

- left: method flashcard tiles;
- right: database flashcard tiles;
- aside: focused connection summary and Actor workflow.

Clicking a tile opens a modal flashcard with three narrative sections — **what it is**, **origin**, and **introduction** — plus recorded pipeline/source metadata. Selection remains a separate control on the tile (and inside the flashcard footer) so browsing does not force selection.

`Configure SQL API` opens the existing session-scoped authentication dialog. Secrets are never rendered back into the page.

### 02 Compose / 组件编排

This module explains how methods, databases and Actors relate.

Left side:

- eight method nodes;
- eight database nodes;
- many-to-many SVG connection graph;
- edge interaction: click empty curve to connect, click another selected curve to inspect, click the active curve again to remove;
- hover tooltip naming the hovered pair;
- dim idle curves when any connection is selected; brighten only the focused edge.

Right side (workflow inspector):

- connection switcher list with prev/next when multiple pairs are selected;
- remove control per connection;
- active connection label;
- Actor DAG for the focused config;
- integration provenance drawer.

The connection graph answers “which combinations exist.” The switcher answers “which pair am I inspecting.” The Actor DAG answers “how this focused combination runs.”

### Integration provenance drawer

A collapsed `Behind this configuration` drawer lives inside Compose. It visualizes:

```text
Candidate source
→ Integration manifest
→ Native Actors
→ Task registration
→ Reproduce config
```

It does not expose candidate source code or private paths. The drawer explains the native-integration model without competing with the main run flow.

### 03 Run / 执行工作台

This module restores the useful behavior of the original SQL Studio.

Content:

- natural-language question;
- dataset/schema summary;
- suggested questions when available;
- final config preview;
- focused method/database;
- sampling summary;
- primary `Run Reproduce` action.

Running state uses a horizontal stage rail:

```text
Loading data
→ Building workflow
→ Generating SQL
→ Executing SQL
→ Evaluating
```

The rail shows status and elapsed time. Full logs remain hidden until Inspect.

The hosted interactive query continues using the real `/api/query` and `/api/execute` endpoints. Batch evaluation actions must be shown only when the deployment capabilities permit them.

### 04 Inspect / 结果检查

This module is hidden or compact before a run and expands when results exist.

Tabs:

- Generated SQL;
- Result Table;
- Actor Trace;
- Metrics;
- Logs.

The Actor Trace tab shows each stage’s Actor, status, elapsed time and artifact/output reference. It does not expose hidden reasoning.

The Metrics tab may show EX, EM, SF1, VES, component metrics, tokens and latency only when present in the selected result or persisted score bundle.

### 05 Diagnose / 弱点诊断

This module consumes persisted evaluation evidence.

Content:

- top error roots;
- metrics by hardness;
- SQL-component weakness;
- scenario slices;
- Actor/stage metrics;
- token and latency cost;
- failed sample list.

Selecting a weakness filters the sample list and highlights the associated Actor stage when that attribution exists.

If no score bundle is available, render an evidence-required empty state. Do not synthesize metrics.

### 06 Improve / 有界改进

This module presents the artifact-backed bounded loop:

```text
Baseline
→ Weakness Profile
→ Candidate Change
→ Smoke
→ Bounded Evaluation
→ Confirmation
→ Human Review
```

Each stage displays only recorded state and artifact references. Review outcomes are `accept`, `continue` or `rollback`.

The module must not imply silent source modification, guaranteed improvement or autonomous merging.

## Bilingual behavior

The UI supports Simplified Chinese and English from one component tree.

Files:

```text
demo-app/src/i18n/index.js
demo-app/src/i18n/en-US.js
demo-app/src/i18n/zh-CN.js
```

Behavior:

- first visit uses Chinese when `navigator.language` starts with `zh`, otherwise English;
- a `中文 / EN` switch is always available in the header;
- the selected locale is persisted in `localStorage`;
- `<html lang>` updates with the selected locale;
- UI labels, help text, empty states, errors and ARIA labels use translation keys;
- Method names, database ids, Actor classes, config paths, SQL, metric abbreviations and raw logs remain unchanged;
- missing translation keys fall back to English.

The layout must be tested with longer Chinese copy and must not rely on fixed text widths.

## Visual system

Direction: `Claude-aligned Graphite Research Workspace`.

Inspired by Claude Code / high-end developer tooling (not neon SaaS glass):

- layered charcoal canvas (`#141416` → `#1a1a1c`), never pure black void;
- solid raised panels (`#212124` / `#26262a`) with hairline borders;
- warm Claude accent (`#da7756`) for focus, selection and primary actions;
- muted text hierarchy (`#e8e8ea` / `#8a8a93` / `#5c5c66`);
- monospace reserved for technical metadata; Inter for UI chrome;
- glass/blur only on sticky/overlay shells, modest blur — content panes stay opaque for readability;
- no purple neon, no bright daylight wash, no decorative orbs.

Color semantics:

- warm Claude orange: selection, focus and primary actions;
- green: runnable configuration or completed execution;
- amber: downloading, waiting or human review;
- red: failure;
- muted gray: unavailable or inactive.

Product emphasis:

- brand wordmark and “Dynamic Text-to-SQL orchestration” subtitle are hero-level in the header;
- sticky process rail reads as a continuous Configure → Improve ribbon;
- Compose elevates the Method × Database matrix and Actor workflow as the primary visual idea.

Typography:

- Inter/system sans for UI;
- system monospace for Actor classes, SQL, config paths and run ids;
- strong module numbering and section hierarchy;
- no decorative serif typography.

Motion:

- 120–180ms transitions;
- connection focus and section activation only;
- no parallax or continuous decorative animation;
- respect `prefers-reduced-motion`.

## Component boundaries

`MatrixStudio.jsx` must be split into focused units:

```text
FullFlowDemo.jsx
DemoHeader.jsx
ProcessRail.jsx
ConfigurationStudio.jsx
ConnectionComposer.jsx
ActorWorkflow.jsx
RunWorkspace.jsx
ResultWorkspace.jsx
DiagnosisWorkspace.jsx
ImprovementWorkspace.jsx
IntegrationProvenance.jsx
```

Shared state belongs in `FullFlowDemo`:

- locale;
- selected methods and databases;
- focused connection;
- SQL authentication state;
- sampling settings;
- run state;
- selected result/artifact.

Pure catalog and selection helpers move to a separate module so they can be tested without rendering the complete page.

## Data flow

On load:

1. fetch health, capabilities, databases and SQL-auth status;
2. derive the runnable 8 × 8 matrix from `reproduce_configs`;
3. initialize a valid focused connection;
4. render evidence-backed modules only when their data exists.

On selection:

1. method/database selection updates the many-to-many connection set;
2. focused connection resolves its config record;
3. Actor Workflow and config summary update;
4. no network request is required.

On interactive run:

1. validate SQL authentication, focused config and question;
2. call `/api/query`;
3. call `/api/execute` with the returned SQL;
4. display SQL, result and trace;
5. keep evaluation claims separate unless a score bundle exists.

## Error handling

- Missing SQL credential: keep the question and selection, open configuration.
- Missing config: show unavailable state and disable run.
- Missing benchmark asset: show installation/cache requirement, not a generic failure.
- Provider rejection: display a sanitized session error.
- Query failure: keep configuration and question for retry.
- Missing artifact: render an evidence-required empty state.
- Unsupported hosted mutation: explain that the action requires a local checkout.

## Responsive behavior

Desktop:

- full module layout;
- connection graph and Actor DAG side by side;
- sticky horizontal process rail.

Tablet:

- narrower graph columns;
- configuration and run panels stack when required.

Mobile:

- method and database selectors replace the simultaneous 8 × 8 graph;
- focused connection diagram remains visible;
- process rail becomes horizontally scrollable;
- all controls maintain a 40px minimum target.

## Accessibility

- semantic sections and headings;
- keyboard-operable process rail, selectors, tabs and dialogs;
- `aria-pressed` for method/database selection;
- accessible SVG title and description;
- visible focus styles;
- status text never relies on color alone;
- WCAG AA contrast for both glass and opaque surfaces.

## Testing and verification

Frontend tests must cover:

- Chinese and English rendering;
- locale detection, switching and persistence;
- hosted page renders the six modules in order;
- additive many-to-many selection;
- focused connection and Actor DAG updates;
- unavailable config cannot run;
- SQL authentication dialog remains session-scoped;
- query/execute success and error states;
- result tabs;
- missing-artifact empty states.

Verification:

```bash
npm test --prefix demo-app
npm run build --prefix demo-app
python -m unittest discover -s tests -p 'test_*.py' -v
python tools/anonymity_scan.py
python tools/security_scan.py
git diff --check
```

## Explicit exclusions

- No public submission, venue, deadline, review or acceptance information.
- No private roadmap copy.
- No hidden-reasoning display.
- No fabricated metrics, logs, artifacts or improvement states.
- No duplicated Chinese and English component implementations.
- No restoration of the old three-page sidebar as the primary hosted experience.
