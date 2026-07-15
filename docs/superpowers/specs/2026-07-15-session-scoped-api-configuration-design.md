# Session-Scoped API Configuration Design

## Goal

Add clear API configuration dialogs to the SqurveBridge Live Demo so each visitor can configure SQL generation and the embedded Pi Agent independently. Both credential paths must work on Hugging Face Spaces without maintainer-owned model keys.

## Product Boundary

- SQL uses Squrve's existing providers, models, and request path.
- Agent chat uses Pi's native provider, model, and authentication implementation.
- SQL credentials never enter a Pi process. Pi credentials never enter Squrve configuration.
- Hosted credentials exist only for one browser session. Local development may retain its current trusted `.env` workflow.
- The public Pi profile remains `hosted-readonly`; authentication must not unlock shell, write, or execution tools.

## User Experience

### SQL API dialog

The runtime header exposes `Configure SQL API`. The dialog provides a searchable provider list, provider-specific model selector, masked API-key input, show/hide control, `Test connection`, `Use for this session`, and `Disconnect`.

Testing a key must not activate it. Saving succeeds only after validation and clears the input element immediately. The header then shows `Provider / model · Connected`. Errors remain inside the dialog and never repeat the submitted key.

### Pi authentication dialog

The Agent Harness header exposes Pi's authentication status and a `Login` action. Its React presentation follows Pi's terminal UI structure and wording while using browser controls. It includes searchable providers, `API key` and `subscription` labels, configured status, Pi-native model selection, logout, and provider switching.

API-key and OAuth flows are driven by Pi's own provider auth objects and `AuthLoginCallbacks`. The web dialog renders Pi auth prompts and events: secret/text/select prompts, authorization URLs, device codes, progress, manual codes, cancellation, and completion. It does not duplicate provider-specific login logic in Python or React.

## Architecture

### Browser session identity

Flask issues an opaque, cryptographically random session identifier in a `Secure`, `HttpOnly`, `SameSite=Lax` cookie. The cookie contains no provider or credential data. Hosted API routes resolve it to an in-memory session registry with a 30-minute idle timeout. Expired sessions are removed lazily on access and by a bounded cleanup loop.

### SQL credential registry

A focused Python service owns SQL session state: provider, model, validated key, timestamps, and validation status. SQL generation resolves credentials from the current browser session rather than global environment mutation. The key is passed directly to a request-scoped `SqurveDemo`/LLM instance and is never written to `.env` or process-wide `os.environ`.

### Pi authentication bridge

The embedded Node bridge owns one Pi `InMemoryCredentialStore` and `Models` instance per Pi session. Flask forwards typed auth commands and events over the existing Pi session channel. Pi performs provider discovery, login, OAuth refresh, model resolution, logout, and request authentication. Python stores neither Pi API keys nor OAuth tokens.

The existing React Agent Harness receives catalog, auth-status, auth-prompt, auth-event, model, and completion messages. A dedicated Pi auth dialog maps those typed messages to web controls styled after Pi's `OAuthSelectorComponent` and `LoginDialogComponent`.

## Interfaces

Hosted SQL routes:

- `GET /api/sql-auth` returns provider/model/status metadata without secrets.
- `POST /api/sql-auth/test` validates `{provider, model, api_key}` without activating it.
- `PUT /api/sql-auth` validates and activates `{provider, model, api_key}` for the browser session.
- `DELETE /api/sql-auth` removes the browser session's SQL credential.

Pi auth messages use the existing agent WebSocket and receive stable message types:

- Browser to Pi: `auth_start`, `auth_prompt_response`, `auth_cancel`, `model_select`, `logout`.
- Pi to browser: `auth_catalog`, `auth_status`, `auth_prompt`, `auth_event`, `model_catalog`, `auth_complete`, `auth_error`.

No interface returns an API key, OAuth access token, refresh token, authorization header, or raw provider exception containing request credentials.

## Data Flow

For SQL, the browser submits a key to the SQL auth endpoint over HTTPS. Flask validates it, keeps it in the SQL registry under the cookie session, and clears it on disconnect or timeout. Query requests resolve the same session and inject its credential into only that request.

For Pi, the browser starts a Pi session, requests Pi's native auth catalog, and selects a provider. Pi emits prompts/events through the bridge. The browser answers them, Pi stores the resulting credential in its session-local `InMemoryCredentialStore`, and subsequent prompts use Pi's selected model. Stopping the Pi session destroys the store.

## Error Handling

- Missing, expired, or disconnected credentials return a typed `auth_required` response.
- Invalid keys return `credential_rejected`; provider network failures return `provider_unreachable`.
- Unsupported providers/models return `unsupported_provider` or `unsupported_model` before any outbound request.
- OAuth cancellation is normal completion with `cancelled`, not a server error.
- Agent disconnect stops the Pi process and destroys its credential store.
- Error sanitization permits provider name, model, status code, and safe guidance only.

## Security and Resource Controls

- Hosted credential persistence to files, environment variables, browser storage, traces, analytics, and logs is forbidden.
- Password inputs disable autocomplete and are cleared after submit, cancel, and close.
- Logs record session IDs only as one-way short hashes.
- SQL auth mutation routes require the same-origin session cookie and reject cross-origin requests.
- Session registries are bounded; eviction clears credentials before dropping state.
- Existing maximum Pi session limits remain enforced.

## Testing

Python tests cover cookie isolation, SQL/Pi separation, timeout cleanup, disconnect, cross-origin rejection, error redaction, provider/model validation, and hosted route policy. Node tests cover Pi-native catalog/auth reuse, in-memory credential lifecycle, OAuth prompt/event translation, logout, and destruction on stop. React tests cover both dialogs, masked inputs, provider/model selection, Pi prompt rendering, success/error states, and input clearing.

Integration checks start two browser sessions with different fake keys and prove that SQL and Pi use only their assigned credential. Release verification rebuilds the Hugging Face bundle and Docker image, then checks `/api/health`, `/api/capabilities`, SQL auth status, Pi catalog, and the rendered dialogs without using a real secret.

## Deployment and Rollback

The feature ships through the existing allowlisted Space bundle. After GitHub Actions pass, upload one Space commit and verify the public CPU Space. Rollback means reverting the Space repository to the previous verified commit and redeploying the matching SqurveBridge revision.

## Out of Scope

- Shared maintainer API keys for public traffic.
- Persistent user accounts or credential databases.
- Browser-local storage of credentials.
- Changes to Squrve's provider implementation or Pi's provider-specific auth logic.
- Enabling write, shell, or execution tools in the hosted Pi profile.
