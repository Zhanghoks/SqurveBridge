# Orchestrator Boundary

`tools/mcts/orchestrator.py` and `.agents/tools/mcts/orchestrator.py` are thin wrappers only.

Rules:

- Wrapper target: `reproduce.evolve.mcts.orchestrator.main`
- Wrapper length target: 20 lines or fewer
- No MCTS selection, expansion, rollout, scoring, journal mutation, or artifact writing in wrappers
- The real engine lives in `reproduce/evolve/mcts/orchestrator.py`
- `run_search()` owns one search stage.
- `run_bounded_funnel()` coordinates smoke/bounded/full stage calls through the evolution state machine; it must not silently restart from smoke when `evolve-state.json` proves a later safe resume point.
- Deterministic support logic lives in `reproduce/evolve/`

This prevents a double-orchestrator split between agent tools and reproduce metrics.
