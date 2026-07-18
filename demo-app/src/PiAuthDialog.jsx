import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { commandForPrompt } from './piAuth.js'

const AUTH_FALLBACK = {
  'agent.authEyebrow': 'Model access',
  'agent.authTitle': 'Connect a model',
  'agent.authClose': 'Close',
  'agent.authFooter': 'Credentials stay in this session only.',
  'agent.authSearchLabel': 'Search providers',
  'agent.authSearchPlaceholder': 'Search model providers',
  'agent.authConfigured': 'Connected',
  'agent.authSelectProvider': 'Select a provider',
  'agent.authCredentialConfigured': 'Credential connected',
  'agent.authChooseMethod': 'Choose how to connect this provider',
  'agent.authDisconnect': 'Disconnect',
  'agent.authSubscription': 'Subscription',
  'agent.authAuthorizationUrl': 'Authorization link',
  'agent.authDeviceAuthorization': 'Device authorization',
  'agent.authProgress': 'Progress',
  'agent.authShow': 'Show',
  'agent.authHide': 'Hide',
  'agent.authContinue': 'Continue',
  'agent.authCancel': 'Cancel',
  'agent.authModel': 'Model',
  'agent.authModelHint': 'Choose an available model or enter a compatible model ID.',
  'agent.authSelected': 'Selected',
  'agent.authNoModels': 'No catalog models are available for this provider.',
  'agent.authCustomModel': 'Custom model ID',
  'agent.authCustomModelPlaceholder': 'e.g. model-name-latest',
  'agent.authUseModel': 'Use model',
  'agent.authCustomModelHint': 'The model must be compatible with this provider credential.',
}

function authLabel(t, key) {
  if (typeof t === 'function') {
    const value = t(key)
    if (value && value !== key) return value
  }
  return AUTH_FALLBACK[key] || key
}

export default function PiAuthDialog({ open, state, send, onClose, t, embedded = false }) {
  const [search, setSearch] = useState('')
  const [providerId, setProviderId] = useState(state.providers[0]?.id || '')
  const [input, setInput] = useState('')
  const [selectedOption, setSelectedOption] = useState('')
  const [customModel, setCustomModel] = useState('')
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (!state.providers.some(provider => provider.id === providerId)) {
      setProviderId(state.providers[0]?.id || '')
    }
  }, [state.providers.map(provider => provider.id).join('|'), providerId])

  useEffect(() => {
    setInput('')
    setSelectedOption('')
    setRevealed(false)
  }, [state.prompt?.request_id])

  const close = useCallback(() => {
    if (state.prompt || ['prompting', 'authenticating'].includes(state.status)) {
      send({ type: 'auth_cancel' })
      setInput('')
      setSelectedOption('')
      setRevealed(false)
    }
    setSearch('')
    setInput('')
    setSelectedOption('')
    setRevealed(false)
    onClose()
  }, [state.prompt, state.status, send, onClose])

  useEffect(() => {
    if (!open) return undefined
    const handleKeyDown = event => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, close])

  const filteredProviders = useMemo(() => {
    const query = search.trim().toLowerCase()
    return query
      ? state.providers.filter(provider => `${provider.id} ${provider.name}`.toLowerCase().includes(query))
      : state.providers
  }, [state.providers, search])
  const activeProviderId = state.providers.some(item => item.id === providerId) ? providerId : (state.providers[0]?.id || '')
  const provider = state.providers.find(item => item.id === activeProviderId)
  const models = state.models.filter(model => model.provider === activeProviderId && model.configured)

  if (!open) return null

  const begin = method => {
    setInput('')
    setSelectedOption('')
    send({ type: 'auth_start', provider: activeProviderId, method })
  }

  const answer = () => {
    const value = state.prompt?.kind === 'select' ? selectedOption : input
    if (!state.prompt || !value.trim()) return
    send(commandForPrompt(state.prompt, value.trim()))
    setInput('')
    setSelectedOption('')
    setRevealed(false)
  }

  const cancel = () => {
    send({ type: 'auth_cancel' })
    setInput('')
    setSelectedOption('')
    setRevealed(false)
  }

  const selectCustomModel = event => {
    event.preventDefault()
    const model = customModel.trim()
    if (!model) return
    send({ type: 'model_select', provider: activeProviderId, model })
    setCustomModel('')
  }

  return createPortal(<div className={`auth-dialog-backdrop${embedded ? ' flow-auth-dialog' : ''}`} role="presentation">
    <div className={embedded ? 'flow-demo pi-auth-flow-scope' : 'pi-auth-flow-scope'}>
      <section className="auth-dialog pi-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="pi-auth-title">
      <div className="auth-dialog-header pi-auth-header">
        <div><span>{authLabel(t, 'agent.authEyebrow')}</span><h2 id="pi-auth-title">{authLabel(t, 'agent.authTitle')}</h2></div>
        <button className="icon-button" type="button" aria-label={authLabel(t, 'agent.authClose')} onClick={close}>×</button>
      </div>
      <div className="pi-tui-frame">
        <aside className="pi-auth-providers">
          <label className="field"><span>{authLabel(t, 'agent.authSearchLabel')}</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder={authLabel(t, 'agent.authSearchPlaceholder')} /></label>
          <div className="pi-auth-provider-list">
            {filteredProviders.map(item => <button type="button" key={item.id} className={item.id === activeProviderId ? 'active' : ''} onClick={() => setProviderId(item.id)}>
              <span><strong>{item.name}</strong><code>{item.id}</code></span>
              <small>{item.configured ? authLabel(t, 'agent.authConfigured') : item.auth_methods.join(' · ')}</small>
            </button>)}
          </div>
        </aside>
        <main className="pi-auth-stage">
          <div className="pi-auth-stage-title"><div><span>{provider?.name || authLabel(t, 'agent.authSelectProvider')}</span><small>{provider?.configured ? authLabel(t, 'agent.authCredentialConfigured') : authLabel(t, 'agent.authChooseMethod')}</small></div>{provider?.configured && <button className="button danger compact" type="button" onClick={() => send({ type: 'logout', provider: activeProviderId })}>{authLabel(t, 'agent.authDisconnect')}</button>}</div>

          {provider && <div className="pi-auth-methods">
            {provider.auth_methods.includes('api_key') && <button className="button secondary" type="button" disabled={state.status === 'prompting'} onClick={() => begin('api_key')}>API key</button>}
            {provider.auth_methods.includes('subscription') && <button className="button secondary" type="button" disabled={state.status === 'prompting'} onClick={() => begin('subscription')}>{authLabel(t, 'agent.authSubscription')}</button>}
          </div>}

          {state.events.length > 0 && <div className="pi-auth-events" aria-live="polite">
            {state.events.map((event, index) => {
              if (event.event === 'auth_url') return <div key={index}><span>{authLabel(t, 'agent.authAuthorizationUrl')}</span><a href={event.url} target="_blank" rel="noreferrer">{event.url}</a>{event.instructions && <p>{event.instructions}</p>}</div>
              if (event.event === 'device_code') return <div key={index}><span>{authLabel(t, 'agent.authDeviceAuthorization')}</span><a href={event.verification_uri} target="_blank" rel="noreferrer">{event.verification_uri}</a><code>{event.user_code}</code></div>
              return <div key={index}><span>{authLabel(t, 'agent.authProgress')}</span><p>{event.message}</p></div>
            })}
          </div>}

          {state.prompt && <form className="pi-auth-prompt" autoComplete="off" onSubmit={event => { event.preventDefault(); answer() }}>
            <div className="pi-auth-prompt-field"><span id="pi-auth-prompt-label">{state.prompt.message}</span>
              {state.prompt.kind === 'select' ? <div className="pi-auth-options" role="radiogroup" aria-labelledby="pi-auth-prompt-label">{(state.prompt.options || []).map(option => <label key={option.id}><input type="radio" name="pi-auth-option" value={option.id} checked={selectedOption === option.id} onChange={() => setSelectedOption(option.id)} /> <span>{option.label}</span></label>)}</div> : <div className="pi-auth-input"><input aria-label={state.prompt.message} type={state.prompt.kind === 'secret' && !revealed ? 'password' : 'text'} autoComplete={state.prompt.kind === 'secret' ? 'new-password' : 'off'} value={input} onChange={event => setInput(event.target.value)} placeholder={state.prompt.placeholder || ''} />{state.prompt.kind === 'secret' && <button type="button" onClick={() => setRevealed(value => !value)}>{revealed ? authLabel(t, 'agent.authHide') : authLabel(t, 'agent.authShow')}</button>}</div>}
            </div>
            <div className="pi-auth-prompt-actions"><button className="button primary" type="submit" disabled={state.prompt.kind === 'select' ? !selectedOption : !input.trim()}>{authLabel(t, 'agent.authContinue')}</button><button className="button" type="button" onClick={cancel}>{authLabel(t, 'agent.authCancel')}</button></div>
          </form>}

          {provider?.configured && <div className="pi-model-picker"><div><span>{authLabel(t, 'agent.authModel')}</span><small>{authLabel(t, 'agent.authModelHint')}</small></div>{models.length ? <div>{models.map(model => <button type="button" key={model.id} className={model.selected ? 'active' : ''} onClick={() => send({ type: 'model_select', provider: model.provider, model: model.id })}><strong>{model.name}</strong><code>{model.id}</code>{model.selected && <small>{authLabel(t, 'agent.authSelected')}</small>}</button>)}</div> : <p>{authLabel(t, 'agent.authNoModels')}</p>}<form className="pi-custom-model" onSubmit={selectCustomModel}><label htmlFor="pi-custom-model-id">{authLabel(t, 'agent.authCustomModel')}</label><div><input id="pi-custom-model-id" value={customModel} onChange={event => setCustomModel(event.target.value)} placeholder={authLabel(t, 'agent.authCustomModelPlaceholder')} autoComplete="off" /><button className="button secondary" type="submit" disabled={!customModel.trim()}>{authLabel(t, 'agent.authUseModel')}</button></div><small>{authLabel(t, 'agent.authCustomModelHint')}</small></form></div>}
          {state.error && <p className="error-banner" role="alert">{state.error}</p>}
        </main>
      </div>
      <div className="pi-auth-footer"><span>{authLabel(t, 'agent.authFooter')}</span><button className="button" type="button" onClick={close}>{authLabel(t, 'agent.authClose')}</button></div>
      </section>
    </div>
  </div>, document.body)
}
