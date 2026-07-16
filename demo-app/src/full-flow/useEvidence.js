import { useCallback, useEffect, useState } from 'react'

const INITIAL_EVIDENCE = {
  loading: true,
  comparison: null,
  archive: [],
  selectedRun: null,
  error: '',
}

const queryString = selection => {
  const params = new URLSearchParams()
  if (selection?.method) params.set('methods', selection.method)
  if (selection?.dataset) params.set('dataset', selection.dataset)
  if (selection?.split) params.set('split', selection.split)
  if (selection?.sampleMode) params.set('sample_mode', selection.sampleMode)
  if (selection?.sampleLimit) params.set('sample_limit', String(selection.sampleLimit))
  if (selection?.sampleMode === 'random' && selection?.sampleSeed != null) params.set('sample_seed', String(selection.sampleSeed))
  return params.toString()
}

export function useEvidence(api, selection = {}) {
  const [state, setState] = useState(INITIAL_EVIDENCE)
  const refresh = useCallback(async () => {
    setState(current => ({ ...current, loading: true, error: '' }))
    try {
      if (typeof api !== 'function') {
        throw new Error('Evidence API is unavailable.')
      }
      const [comparisonResult, archiveResult] = await Promise.allSettled([
        api(`/api/comparisons/latest/results?${queryString(selection)}`),
        api('/api/archive'),
      ])
      if (comparisonResult.status === 'rejected' && archiveResult.status === 'rejected') {
        throw new Error('Persisted evidence could not be loaded.')
      }
      const comparison = comparisonResult.status === 'fulfilled'
        ? comparisonResult.value
        : { runs: [] }
      const archive = archiveResult.status === 'fulfilled'
        ? archiveResult.value
        : { runs: [] }
      const comparisonRun = comparison.runs?.[0]
      const archiveRun = archive.runs?.[0]
      const selectedRun = comparisonRun
        ? { ...comparisonRun, evidence_origin: 'persisted-comparison' }
        : archiveRun
          ? { ...archiveRun, evidence_origin: 'historical-archive', source: archiveRun.source || 'archive' }
          : null
      setState({
        loading: false,
        comparison,
        archive: archive.runs || [],
        selectedRun,
        error: '',
      })
    } catch (error) {
      setState({
        loading: false,
        comparison: null,
        archive: [],
        selectedRun: null,
        error: error.message || 'Persisted evidence could not be loaded.',
      })
    }
  }, [api, selection?.method, selection?.dataset, selection?.split, selection?.sampleMode, selection?.sampleLimit, selection?.sampleSeed])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { ...state, refresh }
}
