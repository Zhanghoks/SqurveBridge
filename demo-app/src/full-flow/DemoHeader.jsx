export default function DemoHeader({
  locale,
  setLocale,
  sqlAuth,
  onConfigureSql,
  t,
  configCount,
  credentialMode = 'session',
}) {
  const nextLocale = locale === 'zh-CN' ? 'en-US' : 'zh-CN'
  const languageLabel = locale === 'zh-CN'
    ? t('language.switchToEnglish')
    : t('language.switchToChinese')

  return <header className="flow-header flow-glass">
    <div className="flow-brand">
      <span aria-hidden="true">S</span>
      <div>
        <strong>SqurveBridge</strong>
        <small>{t('brand.subtitle')}</small>
      </div>
    </div>
    <div className="flow-header-status">
      <span>{t('header.configCount', { count: configCount })}</span>
      <span className={sqlAuth?.configured ? 'connected' : 'unavailable'}>
        {sqlAuth?.configured
          ? `${sqlAuth.provider || ''}${sqlAuth.model ? ` · ${sqlAuth.model}` : ''}`
          : t('status.unavailable')}
      </span>
    </div>
    <div className="flow-header-actions">
      <button type="button" onClick={onConfigureSql}>
        {t(credentialMode === 'local' ? 'header.configureLocalApi' : 'header.configureApi')}
      </button>
      <button
        type="button"
        aria-label={languageLabel}
        onClick={() => setLocale(nextLocale)}
      >
        {languageLabel}
      </button>
    </div>
  </header>
}
