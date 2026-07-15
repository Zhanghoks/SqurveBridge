export const createPiAuthState = () => ({
  providers: [],
  models: [],
  selectedModel: null,
  prompt: null,
  events: [],
  status: 'idle',
  error: '',
})

export function applyPiAuthEvent(state, event) {
  if (event.type === 'auth_catalog') {
    return { ...state, providers: event.providers || [] }
  }
  if (event.type === 'auth_status') {
    const statuses = new Map((event.providers || []).map(provider => [provider.id, provider]))
    return {
      ...state,
      providers: state.providers.map(provider => ({ ...provider, ...(statuses.get(provider.id) || {}) })),
    }
  }
  if (event.type === 'auth_prompt') {
    return { ...state, status: 'prompting', prompt: event, error: '' }
  }
  if (event.type === 'auth_event') {
    return { ...state, status: 'authenticating', events: [...state.events.slice(-19), event], error: '' }
  }
  if (event.type === 'model_catalog') {
    const models = event.models || []
    return { ...state, models, selectedModel: models.find(model => model.selected) || null }
  }
  if (event.type === 'auth_complete') {
    const resetInteraction = event.status === 'logged_out' || event.status === 'cancelled'
    return {
      ...state,
      status: event.status === 'authenticated' ? 'authenticated' : 'idle',
      prompt: null,
      events: resetInteraction ? [] : state.events,
      selectedModel: event.status === 'logged_out' ? null : state.selectedModel,
      error: '',
    }
  }
  if (event.type === 'auth_error') {
    return { ...state, status: 'error', prompt: null, error: event.message || 'Pi authentication failed.' }
  }
  if (event.type === 'exit') return createPiAuthState()
  return state
}

export const commandForPrompt = (prompt, value) => ({
  type: 'auth_prompt_response',
  request_id: prompt.request_id,
  value,
})
