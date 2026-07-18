import React, { useEffect, useMemo, useState } from 'react'
import { officialModelsFor } from './llmCatalog.js'

const jsonOptions = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export default function SqlAuthDialog({ open, api, status, onStatusChange, onClose }) {
  const providers = status?.providers || []
  const initialProvider = providers.find(item => item.id === status?.provider) || providers[0]
  const [search, setSearch] = useState('')
  const [provider, setProvider] = useState(initialProvider?.id || '')
  const [model, setModel] = useState(status?.model || initialProvider?.default_model || '')
  const [endpointId, setEndpointId] = useState(status?.endpoint_id || initialProvider?.default_endpoint_id || '')
  const [apiKey, setApiKey] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [currentStatus, setCurrentStatus] = useState(status || { configured: false, providers })
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    setCurrentStatus(status || { configured: false, providers })
    const selected = providers.find(item => item.id === (status?.provider || provider)) || providers[0]
    if (!selected) return
    setProvider(selected.id)
    setModel(status?.provider === selected.id && status?.model
      ? status.model
      : selected.default_model)
    setEndpointId(status?.provider === selected.id && status?.endpoint_id
      ? status.endpoint_id
      : selected.default_endpoint_id || '')
  }, [status, providers.map(item => `${item.id}:${item.models.join(',')}`).join('|')])

  const selectedProvider = providers.find(item => item.id === provider)
  const filteredProviders = useMemo(() => {
    const query = search.trim().toLowerCase()
    return query ? providers.filter(item => item.id.toLowerCase().includes(query)) : providers
  }, [providers, search])

  if (!open) return null

  const clearSecret = () => {
    setApiKey('')
    setRevealed(false)
  }

  const selectProvider = item => {
    setProvider(item.id)
    setModel(item.default_model)
    setEndpointId(item.default_endpoint_id || '')
    setMessage('')
    setError('')
  }

  const submit = async method => {
    setBusy(method)
    setMessage('')
    setError('')
    try {
      const data = await api(
        method === 'test' ? '/api/sql-auth/test' : '/api/sql-auth',
        jsonOptions(method === 'test' ? 'POST' : 'PUT', {
          provider,
          model,
          api_key: apiKey.trim(),
          endpoint_id: endpointId,
        }),
      )
      if (method === 'test') {
        setMessage(`Connection verified for ${data.provider}/${data.model}.`)
      } else {
        clearSecret()
        setCurrentStatus(data)
        onStatusChange(data)
        setMessage(`Using ${data.provider}/${data.model} for this session.`)
      }
    } catch (requestError) {
      setError(requestError.message || 'SQL authentication failed.')
    } finally {
      setBusy('')
    }
  }

  const disconnect = async () => {
    setBusy('disconnect')
    setMessage('')
    setError('')
    try {
      const data = await api('/api/sql-auth', jsonOptions('DELETE'))
      clearSecret()
      setCurrentStatus(data)
      onStatusChange(data)
      setMessage('SQL credential disconnected from this session.')
    } catch (requestError) {
      setError(requestError.message || 'Could not disconnect SQL authentication.')
    } finally {
      setBusy('')
    }
  }

  const close = () => {
    clearSecret()
    setSearch('')
    setMessage('')
    setError('')
    onClose()
  }

  return <div className="auth-dialog-backdrop" role="presentation">
    <section className="auth-dialog sql-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="sql-auth-title">
      <div className="auth-dialog-header">
        <div><span>Session credential</span><h2 id="sql-auth-title">Configure SQL API</h2></div>
        <button className="icon-button" type="button" aria-label="Close" onClick={close}>×</button>
      </div>
      <p className="auth-dialog-intro">Choose a Squrve provider and model. The key stays in server memory for this browser session only.</p>
      <div className="auth-dialog-grid">
        <div className="auth-provider-column">
          <label className="field"><span>Search providers</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search Squrve providers" /></label>
          <div className="auth-provider-list" aria-label="SQL providers">
            {filteredProviders.map(item => <button
              type="button"
              key={item.id}
              className={item.id === provider ? 'active' : ''}
              onClick={() => selectProvider(item)}
            ><strong>{item.id}</strong><small>API key</small></button>)}
          </div>
        </div>
        <form className="auth-credential-column" autoComplete="off" onSubmit={event => event.preventDefault()}>
          <div className="session-connection-state">
            <span>{currentStatus?.configured ? 'Connected' : 'Not connected'}</span>
            {currentStatus?.configured && <strong>{currentStatus.provider} / {currentStatus.model}</strong>}
          </div>
          <label className="field model-id-field"><span>Model</span><input aria-label="Model" value={model} onChange={event => setModel(event.target.value)} list="sql-model-suggestions" placeholder="Enter a model ID" autoComplete="off" spellCheck="false" /><datalist id="sql-model-suggestions">{officialModelsFor(provider).map(item => <option key={item} value={item} />)}</datalist><small>Choose a suggestion or enter any model ID supported by this provider.</small></label>
          {selectedProvider?.endpoints?.length > 0 && <label className="field"><span>API region</span><select aria-label="API region" value={endpointId} onChange={event => setEndpointId(event.target.value)}>{selectedProvider.endpoints.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><small>Choose the region where this API key was created.</small></label>}
          <label className="field api-key-field"><span>API key</span><div><input type={revealed ? 'text' : 'password'} autoComplete="new-password" spellCheck="false" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={`Paste ${provider || 'provider'} API key`} /><button type="button" aria-label={revealed ? 'Hide API key' : 'Show API key'} onClick={() => setRevealed(value => !value)}>{revealed ? 'Hide' : 'Show'}</button></div></label>
          <div className="auth-dialog-actions">
            <button className="button secondary" type="button" disabled={Boolean(busy) || !provider || !model || !apiKey.trim()} onClick={() => submit('test')}>{busy === 'test' ? 'Testing…' : 'Test connection'}</button>
            <button className="button primary" type="button" disabled={Boolean(busy) || !provider || !model || !apiKey.trim()} onClick={() => submit('save')}>{busy === 'save' ? 'Saving…' : 'Use for this session'}</button>
            {currentStatus?.configured && <button className="button danger" type="button" disabled={Boolean(busy)} onClick={disconnect}>{busy === 'disconnect' ? 'Disconnecting…' : 'Disconnect'}</button>}
            <button className="button" type="button" onClick={close}>Close</button>
          </div>
          {message && <p className="auth-dialog-message">{message}</p>}
          {error && <p className="error-banner" role="alert">{error}</p>}
        </form>
      </div>
    </section>
  </div>
}
