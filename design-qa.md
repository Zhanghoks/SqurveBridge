# Agent UI Design QA

- References:
  - Variant / Deedly dark agent share
  - Claude-style empty-state screenshot (serif greeting, centered composer, quiet suggestion pills)
- Implementation: `http://127.0.0.1:5173/#configure`
- State: dashboard collapsed; Pi authentication dismissed; empty conversation

## Visual comparison

- Material: passed. Warm charcoal solid surfaces (`#0e0e0e` / `#161616`), thin low-contrast borders, no purple/indigo radial washes, no triple glow orbs, no glass `backdrop-filter` on panes.
- Empty state (Claude): passed. Large serif time-of-day greeting with a small warm accent mark, centered composer, `Type / for skills` placeholder, model pill inside composer, outline suggestion pills below.
- Active chat (Deedly): passed. User messages as dark gray bubbles; assistant left-aligned without bubble chrome; floating bottom composer with white circular send.
- Hierarchy: passed. Connect / model control lives in the composer; toolbar stays quiet once a thread exists.
- Product adaptation: passed. Real Pi Skills via `/`; no fabricated legal documents; SqurveBridge branding retained.

## Interaction checks

- Automatic model authentication dialog still opens on load.
- The dialog can be dismissed to inspect the conversation surface.
- Dashboard collapse expands the Agent panel into an immersive chat canvas.
- `/` or Skills control opens project Skill shortcuts above the composer.
- Send remains disabled until draft text is present; model connect remains available from the composer pill.

## Fix history

- Removed blue/purple glow layers and glass dual-pane treatment from `agent-shell.css`.
- Unified `full-flow.css` and provider dialog chrome to the same warm charcoal tokens.
- Moved empty-state suggestions under the composer; Skills no longer flood the empty canvas.

final result: passed
