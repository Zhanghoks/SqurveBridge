/** Official provider → model IDs shown in Configure LLM / SQL auth pickers. */
export const OFFICIAL_LLM_MODELS = Object.freeze({
  qwen: Object.freeze(['qwen-turbo', 'qwen-plus', 'qwen-max', 'deepseek-v4-flash']),
  deepseek: Object.freeze(['deepseek-chat', 'deepseek-reasoner']),
  zhipu: Object.freeze(['glm-4-plus', 'glm-4-flash']),
  openai: Object.freeze(['gpt-4o-mini', 'gpt-4.1-mini']),
  claude: Object.freeze(['claude-3-5-sonnet-latest']),
  gemini: Object.freeze(['gemini-2.0-flash']),
})

export function officialModelsFor(providerId) {
  return OFFICIAL_LLM_MODELS[providerId] || []
}
