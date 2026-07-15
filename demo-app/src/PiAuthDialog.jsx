import React, { useEffect, useMemo, useState } from 'react'
import { commandForPrompt } from './piAuth.js'

export default function PiAuthDialog({ open, state, send, onClose }) {
  const [search, setSearch] = useState('')
  const [providerId, setProviderId] = useState(state.providers[0]?.id || '')
  const [input, setInput] = useState('')
  const [selectedOption, setSelectedOption] = useState('')
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

  const close = () => {
    if (state.prompt || ['prompting', 'authenticating'].includes(state.status)) cancel()
    setSearch('')
    setInput('')
    setSelectedOption('')
    setRevealed(false)
    onClose()
  }

  return <div className="auth-dialog-backdrop" role="presentation">
    <section className="auth-dialog pi-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="pi-auth-title">
      <div className="auth-dialog-header pi-auth-header">
        <div><span>Pi native authentication</span><h2 id="pi-auth-title">Login to Pi</h2></div>
        <button className="icon-button" type="button" aria-label="Close" onClick={close}>×</button>
      </div>
      <div className="pi-tui-frame">
        <aside className="pi-auth-providers">
          <label className="field"><span>Search providers</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search Pi providers" /></label>
          <div className="pi-auth-provider-list">
            {filteredProviders.map(item => <button type="button" key={item.id} className={item.id === activeProviderId ? 'active' : ''} onClick={() => setProviderId(item.id)}>
              <span><strong>{item.name}</strong><code>{item.id}</code></span>
              <small>{item.configured ? 'configured' : item.auth_methods.join(' · ')}</small>
            </button>)}
          </div>
        </aside>
        <main className="pi-auth-stage">
          <div className="pi-auth-stage-title"><div><span>{provider?.name || 'Select a provider'}</span><small>{provider?.configured ? `${provider.credential_type || 'credential'} configured` : 'Choose Pi native login method'}</small></div>{provider?.configured && <button className="button danger compact" type="button" onClick={() => send({ type: 'logout', provider: activeProviderId })}>Logout</button>}</div>

          {provider && <div className="pi-auth-methods">
            {provider.auth_methods.includes('api_key') && <button className="button secondary" type="button" disabled={state.status === 'prompting'} onClick={() => begin('api_key')}>API key</button>}
            {provider.auth_methods.includes('subscription') && <button className="button secondary" type="button" disabled={state.status === 'prompting'} onClick={() => begin('subscription')}>subscription</button>}
          </div>}

          {state.events.length > 0 && <div className="pi-auth-events" aria-live="polite">
            {state.events.map((event, index) => {
              if (event.event === 'auth_url') return <div key={index}><span>Authorization URL</span><a href={event.url} target="_blank" rel="noreferrer">{event.url}</a>{event.instructions && <p>{event.instructions}</p>}</div>
              if (event.event === 'device_code') return <div key={index}><span>Device authorization</span><a href={event.verification_uri} target="_blank" rel="noreferrer">{event.verification_uri}</a><code>{event.user_code}</code></div>
              return <div key={index}><span>Progress</span><p>{event.message}</p></div>
            })}
          </div>}

          {state.prompt && <form className="pi-auth-prompt" autoComplete="off" onSubmit={event => { event.preventDefault(); answer() }}>
            <div className="pi-auth-prompt-field"><span id="pi-auth-prompt-label">{state.prompt.message}</span>
              {state.prompt.kind === 'select' ? <div className="pi-auth-options" role="radiogroup" aria-labelledby="pi-auth-prompt-label">{(state.prompt.options || []).map(option => <label key={option.id}><input type="radio" name="pi-auth-option" value={option.id} checked={selectedOption === option.id} onChange={() => setSelectedOption(option.id)} /> <span>{option.label}</span></label>)}</div> : <div className="pi-auth-input"><input aria-label={state.prompt.message} type={state.prompt.kind === 'secret' && !revealed ? 'password' : 'text'} autoComplete={state.prompt.kind === 'secret' ? 'new-password' : 'off'} value={input} onChange={event => setInput(event.target.value)} placeholder={state.prompt.placeholder || ''} />{state.prompt.kind === 'secret' && <button type="button" onClick={() => setRevealed(value => !value)}>{revealed ? 'Hide' : 'Show'}</button>}</div>}
            </div>
            <div className="pi-auth-prompt-actions"><button className="button primary" type="submit" disabled={state.prompt.kind === 'select' ? !selectedOption : !input.trim()}>Continue</button><button className="button" type="button" onClick={cancel}>Cancel login</button></div>
          </form>}

          {provider?.configured && <div className="pi-model-picker"><div><span>Model</span><small>Select a model from Pi's native catalog</small></div>{models.length ? <div>{models.map(model => <button type="button" key={model.id} className={model.selected ? 'active' : ''} onClick={() => send({ type: 'model_select', provider: model.provider, model: model.id })}><strong>{model.name}</strong><code>{model.id}</code>{model.selected && <small>selected</small>}</button>)}</div> : <p>No authenticated models are available for this provider.</p>}</div>}
          {state.error && <p className="error-banner" role="alert">{state.error}</p>}
        </main>
      </div>
      <div className="pi-auth-footer"><span>Credentials live only in this Pi process.</span><button className="button" type="button" onClick={close}>Close</button></div>
    </section>
  </div>
}
