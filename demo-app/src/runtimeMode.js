export function deploymentTarget(capabilities) {
  return capabilities?.deployment?.target || 'local'
}

export function featureEnabled(capabilities, name) {
  const features = capabilities?.deployment?.features
  return features ? features[name] === true : true
}
