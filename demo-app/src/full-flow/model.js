export const METHODS = ['C3SQL', 'DINSQL', 'FinSQL', 'RESDSQL', 'E-SQL', 'SEDE', 'UNISAR', 'GPT Baseline']
export const DATABASES = ['Spider', 'BIRD', 'BookSQL', 'BULL-EN', 'BULL-CN', 'EHRSQL-2024', 'AmbiDB', 'Spider2']

const slug = value => String(value || '')
  .trim()
  .toLowerCase()
  .replace(/[_\s]+/g, '-')
  .replace(/[^a-z0-9-]/g, '')

export const configKey = (method, database) => `${slug(database)}/${slug(method)}`
export const buildReadyKeys = configs => new Set((configs || []).map(item => configKey(item.method, item.dataset)))
export const buildConnections = (methods, databases) => methods.flatMap(
  method => databases.map(database => ({ method, database, key: configKey(method, database) })),
)
export const resolveFocusedConfig = (configs, method, database) =>
  (configs || []).find(item => configKey(item.method, item.dataset) === configKey(method, database)) || null
export const workflowStages = config => (config?.stages || []).map(stage => ({
  id: stage.id,
  type: stage.type,
  actor: stage.actor,
}))
