import { JSDOM } from 'jsdom'

export function installTestDom() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://demo.hf.space/' })
  globalThis.window = dom.window
  globalThis.document = dom.window.document
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: dom.window.navigator,
  })
  globalThis.HTMLElement = dom.window.HTMLElement
  globalThis.Node = dom.window.Node
  globalThis.getComputedStyle = dom.window.getComputedStyle
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  return () => dom.window.close()
}
