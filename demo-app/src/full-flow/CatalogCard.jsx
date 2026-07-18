export default function CatalogCard({
  name,
  teaser,
  openLabel,
  onOpenFlashcard,
}) {
  return (
    <article className="catalog-card flashcard-tile catalog-card-explain">
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
    </article>
  )
}
