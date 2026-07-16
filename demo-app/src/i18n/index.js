import enUS from './en-US.js'
import zhCN from './zh-CN.js'

export const SUPPORTED_LOCALES = ['en-US', 'zh-CN']

const messages = {
  'en-US': enUS,
  'zh-CN': zhCN,
}

export function detectLocale(navigatorLanguage = '', storedLocale = '') {
  if (SUPPORTED_LOCALES.includes(storedLocale)) return storedLocale
  return String(navigatorLanguage).toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US'
}

export function translate(locale, key, params = {}) {
  const template = messages[locale]?.[key] ?? messages['en-US'][key] ?? key
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  )
}

export function setDocumentLocale(locale) {
  document.documentElement.lang = locale
}
