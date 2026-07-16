import { useCallback, useEffect, useState } from 'react'

const INITIAL_EVIDENCE = {
  loading: true,
  comparison: null,
  archive: [],
  selectedRun: null,
  error: '',
}

export function useEvidence(api) {
  const [state, setState] = useState(INITIAL_EVIDENCE)
  const refresh = useCallback(async () => {
    setState(current => ({ ...current, loading: true, error: '' }))
    try {
      if (typeof api !== 'function') {
        throw new Error('Evidence API is unavailable.')
      }
      const [comparisonResult, archiveResult] = await Promise.allSettled([
        api('/api/comparisons/latest/results'),
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
      const selectedRun = comparison.runs?.[0] || archive.runs?.[0] || null
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
  }, [api])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { ...state, refresh }
}
