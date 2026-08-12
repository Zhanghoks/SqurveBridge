export const PROCESS_STEPS = ['configure', 'compose', 'query', 'board', 'evidence']

const LEGACY_STEP_MAP = {
  run: 'board',
  diagnose: 'board',
  improve: 'board',
  inspect: 'evidence',
  visualize: 'evidence',
  archive: 'evidence',
}

export function resolveProcessStep(hashOrId, fallback = PROCESS_STEPS[0]) {
  const value = String(hashOrId || '').replace(/^#/, '')
  const mapped = LEGACY_STEP_MAP[value] || value
  return PROCESS_STEPS.includes(mapped) ? mapped : fallback
}
