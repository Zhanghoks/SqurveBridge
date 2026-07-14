export function deploymentTarget(capabilities) {
  return capabilities?.deployment?.target || 'local'
}

export function featureEnabled(capabilities, name) {
  const features = capabilities?.deployment?.features
  return features ? features[name] === true : true
}

export function studioSurface(capabilities) {
  return deploymentTarget(capabilities) === 'hf-space' ? 'live-sql' : 'workspace'
}
