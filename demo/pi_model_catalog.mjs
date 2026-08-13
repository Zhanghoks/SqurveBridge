// Read model IDs straight from the embedded Pi SDK's builtin catalog.
//
// The SDK ships the provider/model tables with the package, so this resolves
// offline and without credentials: no API key is read and no request is made.
// Python calls this once (demo/model_catalog.py) instead of carrying its own
// copy of provider model IDs that goes stale on every upstream release.
import { pathToFileURL } from 'node:url'

export async function collectSdkModels(sdk, providerIds) {
  const runtime = await sdk.ModelRuntime.create({
    modelsPath: null,
    refreshOnCreate: false,
  })
  const catalog = {}
  for (const providerId of providerIds) {
    const models = runtime.getModels(providerId).map(model => model.id)
    // Only report providers the SDK actually knows; an empty list would
    // otherwise look like "this provider has no models".
    if (models.length) catalog[providerId] = models
  }
  return catalog
}

export async function runCatalog(argv = process.argv.slice(2)) {
  if (!argv.length) throw new Error('Pi model catalog requires at least one provider id')
  const sdk = await import('@earendil-works/pi-coding-agent')
  const catalog = await collectSdkModels(sdk, argv)
  process.stdout.write(`${JSON.stringify(catalog)}\n`)
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isEntrypoint) {
  runCatalog().catch(error => {
    process.stderr.write(`${error.message}\n`)
    process.exitCode = 1
  })
}
