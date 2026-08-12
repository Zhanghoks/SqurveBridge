import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { EditorState, Compartment } from '@codemirror/state'
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  placeholder as editorPlaceholder,
} from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { autocompletion, closeBrackets, completionKeymap } from '@codemirror/autocomplete'
import { bracketMatching, syntaxHighlighting, HighlightStyle } from '@codemirror/language'
import { sql, SQLite } from '@codemirror/lang-sql'
import { tags } from '@lezer/highlight'

const warmTheme = EditorView.theme({
  '&': {
    backgroundColor: 'transparent',
    color: 'var(--flow-text, #ececec)',
    fontSize: '13px',
  },
  '.cm-content': {
    fontFamily: '"SF Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
    caretColor: 'var(--flow-claude, #d4a574)',
    padding: '10px 0',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: 'var(--flow-inactive, #5c5c5c)',
    border: 'none',
  },
  '.cm-activeLine': { backgroundColor: 'rgb(255 255 255 / 4%)' },
  '.cm-activeLineGutter': { backgroundColor: 'transparent', color: 'var(--flow-muted, #8a8a8a)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
    backgroundColor: 'rgb(212 165 116 / 22%)',
  },
  '.cm-cursor': { borderLeftColor: 'var(--flow-claude, #d4a574)' },
  '.cm-tooltip': {
    backgroundColor: 'var(--flow-glass-strong, #1e1e1e)',
    color: 'var(--flow-text, #ececec)',
    border: '1px solid rgb(255 255 255 / 14%)',
    borderRadius: '8px',
  },
  '.cm-tooltip-autocomplete ul li[aria-selected]': {
    backgroundColor: 'rgb(212 165 116 / 20%)',
    color: 'var(--flow-text, #ececec)',
  },
}, { dark: true })

const sqlLanguage = schema => sql({ dialect: SQLite, schema: schema || {}, upperCaseKeywords: true })

const warmHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: 'var(--flow-claude, #d4a574)', fontWeight: '600' },
  { tag: tags.string, color: 'var(--flow-green, #8fbc8f)' },
  { tag: tags.number, color: 'var(--flow-amber, #d4a35c)' },
  { tag: tags.comment, color: 'var(--flow-inactive, #5c5c5c)', fontStyle: 'italic' },
  { tag: tags.operator, color: 'var(--flow-muted, #8a8a8a)' },
  { tag: tags.typeName, color: 'var(--flow-claude-strong, #e0b68a)' },
  { tag: tags.propertyName, color: 'var(--flow-text, #ececec)' },
])

/**
 * CodeMirror-backed SQL editor bound to the warm theme tokens.
 * Falls back to a plain textarea when the editor cannot mount
 * (e.g. minimal DOM environments), keeping the workflow usable.
 */
export default function SqlEditor({
  value = '',
  onChange,
  onSubmit,
  schema = null,
  placeholder = '',
  ariaLabel = 'SQL editor',
  disabled = false,
  ref = null,
}) {
  const hostRef = useRef(null)
  const viewRef = useRef(null)
  const fallbackRef = useRef(null)
  const compartmentsRef = useRef(null)
  const callbacksRef = useRef({ onChange, onSubmit })
  const [fallback, setFallback] = useState(false)
  callbacksRef.current = { onChange, onSubmit }

  useEffect(() => {
    if (fallback || !hostRef.current || viewRef.current) return undefined
    const languageCompartment = new Compartment()
    const editableCompartment = new Compartment()
    compartmentsRef.current = { language: languageCompartment, editable: editableCompartment }
    try {
      const view = new EditorView({
        parent: hostRef.current,
        state: EditorState.create({
          doc: value,
          extensions: [
            lineNumbers(),
            history(),
            bracketMatching(),
            closeBrackets(),
            highlightActiveLine(),
            autocompletion(),
            warmTheme,
            syntaxHighlighting(warmHighlight),
            editorPlaceholder(placeholder),
            languageCompartment.of(sqlLanguage(schema)),
            editableCompartment.of(EditorView.editable.of(!disabled)),
            keymap.of([
              {
                key: 'Mod-Enter',
                run: () => {
                  callbacksRef.current.onSubmit?.()
                  return true
                },
              },
              ...completionKeymap,
              ...defaultKeymap,
              ...historyKeymap,
            ]),
            EditorView.updateListener.of(update => {
              if (update.docChanged) callbacksRef.current.onChange?.(update.state.doc.toString())
            }),
          ],
        }),
      })
      viewRef.current = view
    } catch {
      setFallback(true)
    }
    return () => {
      viewRef.current?.destroy()
      viewRef.current = null
    }
  }, [fallback])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current !== value) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value } })
    }
  }, [value])

  useEffect(() => {
    const view = viewRef.current
    const compartments = compartmentsRef.current
    if (!view || !compartments) return
    view.dispatch({
      effects: [
        compartments.language.reconfigure(sqlLanguage(schema)),
        compartments.editable.reconfigure(EditorView.editable.of(!disabled)),
      ],
    })
  }, [schema, disabled])

  useImperativeHandle(ref, () => ({
    insert(text) {
      const view = viewRef.current
      if (view) {
        const range = view.state.selection.main
        view.dispatch({
          changes: { from: range.from, to: range.to, insert: text },
          selection: { anchor: range.from + text.length },
        })
        view.focus()
        return
      }
      const element = fallbackRef.current
      if (!element) return
      const start = element.selectionStart ?? element.value.length
      const end = element.selectionEnd ?? element.value.length
      const next = element.value.slice(0, start) + text + element.value.slice(end)
      callbacksRef.current.onChange?.(next)
      element.focus()
    },
    focus() {
      viewRef.current?.focus()
      fallbackRef.current?.focus()
    },
  }), [])

  if (fallback) {
    return (
      <textarea
        className="query-sql-fallback"
        ref={fallbackRef}
        value={value}
        aria-label={ariaLabel}
        placeholder={placeholder}
        disabled={disabled}
        onChange={event => callbacksRef.current.onChange?.(event.target.value)}
        onKeyDown={event => {
          if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
            event.preventDefault()
            callbacksRef.current.onSubmit?.()
          }
        }}
      />
    )
  }

  return <div className="query-sql-editor" ref={hostRef} role="textbox" aria-label={ariaLabel} />
}
