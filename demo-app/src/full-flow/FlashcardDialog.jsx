import { useEffect, useRef } from 'react'

function ExternalLink({ href, children }) {
  if (!href) return null
  return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
}

export default function FlashcardDialog({
  open,
  kind,
  entry,
  selected,
  t,
  onClose,
  onToggleSelect,
}) {
  const closeRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    closeRef.current?.focus()
    const onKeyDown = event => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open || !entry) return null

  const prefix = kind === 'method' ? `catalog.method.${entry.slug}` : `catalog.database.${entry.slug}`
  const selectLabel = kind === 'method'
    ? t('configure.selectMethod', { name: entry.name })
    : t('configure.selectDatabase', { name: entry.name })

  return (
    <div
      className="flashcard-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="flashcard-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="flashcard-title"
        data-testid="flashcard-dialog"
        onClick={event => event.stopPropagation()}
      >
        <header className="flashcard-dialog-header">
          <div>
            <span className="flashcard-kind">{kind === 'method' ? t('configure.methods') : t('configure.databases')}</span>
            <h3 id="flashcard-title">{entry.name}</h3>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="flashcard-close"
            aria-label={t('catalog.closeFlashcard')}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="flashcard-face">
          <section>
            <h4>{t('catalog.what')}</h4>
            <p>{t(`${prefix}.what`)}</p>
          </section>
          <section>
            <h4>{t('catalog.origin')}</h4>
            <p>{t(`${prefix}.origin`)}</p>
          </section>
          <section>
            <h4>{t('catalog.intro')}</h4>
            <p>{t(`${prefix}.intro`)}</p>
          </section>
        </div>

        <dl className="flashcard-meta">
          {kind === 'method' ? (
            <>
              <div>
                <dt>{t('catalog.pipeline')}</dt>
                <dd><code>{entry.pipeline.join(' -> ')}</code></dd>
              </div>
              <div>
                <dt>{t('catalog.actors')}</dt>
                <dd><code>{entry.actors.join(' · ')}</code></dd>
              </div>
              <div>
                <dt>{t('catalog.configPath')}</dt>
                <dd><code>{entry.configPath}</code></dd>
              </div>
              <div>
                <dt>{t('catalog.sourcePath')}</dt>
                <dd><code>{entry.sourcePath}</code></dd>
              </div>
              <div>
                <dt>{t('catalog.paper')}</dt>
                <dd>
                  {entry.paperUrl ? (
                    <ExternalLink href={entry.paperUrl}>{entry.paperLabel || entry.paperUrl}</ExternalLink>
                  ) : (
                    <span>{t('catalog.attributionPending')}</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>{t('catalog.sourceUrl')}</dt>
                <dd>
                  {entry.sourceUrl ? (
                    <ExternalLink href={entry.sourceUrl}>{entry.sourceUrl}</ExternalLink>
                  ) : (
                    <span>{t('catalog.attributionPending')}</span>
                  )}
                </dd>
              </div>
            </>
          ) : (
            <>
              <div>
                <dt>{t('catalog.defaultSplit')}</dt>
                <dd><code>{entry.defaultSplit}</code></dd>
              </div>
              {entry.packagePath ? (
                <div>
                  <dt>{t('catalog.packagePath')}</dt>
                  <dd><code>{entry.packagePath}</code></dd>
                </div>
              ) : null}
              <div>
                <dt>{t('catalog.sourceUrl')}</dt>
                <dd>
                  {entry.sourceUrl ? (
                    <ExternalLink href={entry.sourceUrl}>{entry.sourceUrl}</ExternalLink>
                  ) : (
                    <span>{t('catalog.attributionPending')}</span>
                  )}
                </dd>
              </div>
              {entry.mirrorUrl ? (
                <div>
                  <dt>{t('catalog.mirrorUrl')}</dt>
                  <dd><ExternalLink href={entry.mirrorUrl}>{entry.mirrorUrl}</ExternalLink></dd>
                </div>
              ) : null}
            </>
          )}
        </dl>

        <footer className="flashcard-actions">
          <button
            type="button"
            className={selected ? 'selected' : ''}
            aria-pressed={selected}
            aria-label={selectLabel}
            onClick={() => onToggleSelect(entry.name)}
          >
            {selected ? t('catalog.selected') : t('catalog.select')}
          </button>
          <button type="button" onClick={onClose}>
            {t('catalog.done')}
          </button>
        </footer>
      </div>
    </div>
  )
}
