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
      const [comparison, archive] = await Promise.all([
        api('/api/comparisons/latest/results').catch(() => ({ runs: [] })),
        api('/api/archive').catch(() => ({ runs: [] })),
      ])
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
        error: error.message,
      })
    }
  }, [api])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { ...state, refresh }
}
