export default function CatalogCard({
  name,
  teaser,
  selected,
  focused,
  selectLabel,
  openLabel,
  onToggleSelect,
  onOpenFlashcard,
}) {
  return (
    <article
      className={[
        'catalog-card',
        'flashcard-tile',
        selected ? 'selected' : '',
        focused ? 'focused' : '',
      ].filter(Boolean).join(' ')}
    >
      <button
        type="button"
        className="flashcard-tile-open"
        aria-label={openLabel}
        onClick={onOpenFlashcard}
      >
        <strong>{name}</strong>
        <p>{teaser}</p>
        <span className="flashcard-tile-hint" aria-hidden="true">{'→'}</span>
      </button>
      <button
        type="button"
        className="catalog-card-select"
        aria-label={selectLabel}
        aria-pressed={selected}
        onClick={onToggleSelect}
      >
        <span className="catalog-card-state" aria-hidden="true">
          {selected ? '●' : '○'}
        </span>
      </button>
    </article>
  )
}
