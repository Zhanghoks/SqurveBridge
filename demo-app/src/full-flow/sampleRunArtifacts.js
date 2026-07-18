export const hasLiveRunEvidence = runState => Boolean(
  runState
  && (runState.sql || runState.result || runState.trace?.length || runState.phase === 'failed'),
)

export const resolveInspectArtifacts = runState => {
  const state = runState || {}
  return {
    ...state,
    question: state.question || state.context?.question || null,
    source: hasLiveRunEvidence(state) ? 'live' : 'empty',
    metrics: state.metrics || (state.result
      ? {
        row_count: state.result.row_count,
        elapsed_ms: state.result.elapsed_ms,
      }
      : null),
    logs: state.logs || null,
  }
}
