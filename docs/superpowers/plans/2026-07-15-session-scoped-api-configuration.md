# Session-Scoped API Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every Hugging Face Space visitor configure Squrve SQL and Pi Agent credentials independently for the lifetime of one browser session, without storing secrets or relying on maintainer-owned keys.

**Architecture:** Flask owns only the browser session and request-scoped Squrve SQL credential. Each Pi child process owns its own Pi-native in-memory `AuthStorage` and `ModelRegistry`; Python and React only relay typed auth messages. The two credential paths have separate state, routes, UI, and tests.

**Tech Stack:** Python 3.11, Flask, flask-sock/WebSocket, React 19/Vite, Node.js 20, embedded `@earendil-works/pi-coding-agent`, pytest, Node test runner, Testing Library/jsdom.

**Global Constraints:** Never write hosted credentials to `.env`, `os.environ`, files, browser storage, logs, traces, or API responses. Keep local `/api/provider` behavior unchanged. Keep the hosted Pi tool profile read-only. Sanitize provider errors before sending them to a browser.

---

## Task 1: Add a bounded browser-session SQL credential registry

**Files:**

- Create: `demo/session_credentials.py`
- Create: `tests/test_session_credentials.py`

- [ ] **Step 1: Write failing lifecycle and isolation tests**

```python
def test_credentials_are_isolated_and_expire():
    clock = FakeClock()
    registry = SessionCredentialRegistry(max_sessions=2, idle_timeout=1800, clock=clock)
    registry.put("browser-a", SqlCredential("qwen", "qwen-plus", "key-a"))
    registry.put("browser-b", SqlCredential("deepseek", "deepseek-chat", "key-b"))
    assert registry.get("browser-a").api_key == "key-a"
    assert registry.get("browser-b").api_key == "key-b"
    clock.advance(1801)
    assert registry.get("browser-a") is None

def test_eviction_and_delete_clear_secret_reference():
    registry = SessionCredentialRegistry(max_sessions=1)
    registry.put("a", SqlCredential("qwen", "qwen-plus", "key-a"))
    registry.put("b", SqlCredential("qwen", "qwen-plus", "key-b"))
    assert registry.get("a") is None
    assert registry.delete("b") is True
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run: `pytest -q tests/test_session_credentials.py`

Expected: FAIL with `ModuleNotFoundError: No module named 'demo.session_credentials'`.

- [ ] **Step 3: Implement the registry with injectable time and deterministic eviction**

```python
@dataclass(slots=True)
class SqlCredential:
    provider: str
    model: str
    api_key: str
    validated_at: float = 0.0

class SessionCredentialRegistry:
    def __init__(self, *, max_sessions=128, idle_timeout=1800, clock=time.monotonic): ...
    def put(self, session_id: str, credential: SqlCredential) -> None: ...
    def get(self, session_id: str) -> SqlCredential | None: ...
    def status(self, session_id: str) -> dict: ...
    def delete(self, session_id: str) -> bool: ...
    def cleanup(self) -> int: ...
```

Use an `RLock` and ordered last-access timestamps. `status()` may expose only `configured`, `provider`, `model`, and `validated_at`. Add `new_session_id()` using `secrets.token_urlsafe(32)` and `session_log_id()` using a one-way SHA-256 prefix.

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_session_credentials.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add demo/session_credentials.py tests/test_session_credentials.py
git commit -m "feat: add session SQL credential registry"
```

## Task 2: Add hosted SQL auth routes and request-scoped Squrve configuration

**Files:**

- Modify: `demo/gradio_demo.py:198-225`
- Modify: `demo/api_server.py:80-150,276-390,428-478`
- Modify: `demo/deployment.py:8-45`
- Modify: `tests/test_space_api.py`
- Modify: `tests/test_demo_deployment.py`

- [ ] **Step 1: Write failing route-policy, cookie-isolation, and redaction tests**

Add tests with two Flask clients and fake validation/generation functions:

```python
def test_hosted_sql_auth_is_cookie_scoped(client_factory, monkeypatch):
    monkeypatch.setattr(api_server, "_validate_sql_credential", lambda c: None)
    first, second = client_factory(), client_factory()
    assert first.put("/api/sql-auth", json=KEY_A).status_code == 200
    assert first.get("/api/sql-auth").json["configured"] is True
    assert second.get("/api/sql-auth").json["configured"] is False
    assert "key-a" not in first.get("/api/sql-auth").get_data(as_text=True)

def test_sql_and_pi_keys_never_cross_boundaries(...): ...
def test_sql_auth_rejects_cross_origin_mutation(...): ...
def test_invalid_key_response_is_redacted(...): ...
```

Assert hosted policy permits `GET/POST/PUT/DELETE /api/sql-auth`, still forbids `POST /api/provider`, and advertises `session_sql_auth: true`.

- [ ] **Step 2: Run focused tests and confirm 404/policy failures**

Run: `pytest -q tests/test_space_api.py tests/test_demo_deployment.py`

Expected: FAIL because `/api/sql-auth` does not exist and hosted capabilities do not expose session SQL auth.

- [ ] **Step 3: Make `SqurveDemo` accept a direct credential without environment mutation**

Change the constructor to:

```python
def __init__(self, config_path=None, provider=None, model_name=None, api_key=None):
    ...
    if provider and api_key:
        config.setdefault("api_key", {})[provider] = api_key
    else:
        config = resolve_config_api_keys(config)
```

Do not add a hosted key to `os.environ`; ensure the resolved config passed to `Router.init_config()` contains only the request credential.

- [ ] **Step 4: Add cookie and auth helpers in `api_server.py`**

```python
_sql_credentials = SessionCredentialRegistry(max_sessions=128, idle_timeout=1800)

def _browser_session(create: bool) -> tuple[str | None, bool]: ...
def _set_session_cookie(response, session_id: str) -> None: ...
def _require_same_origin() -> Response | None: ...
def _validate_sql_credential(credential: SqlCredential) -> None: ...
def _session_demo(credential: SqlCredential) -> SqurveDemo:
    return SqurveDemo(provider=credential.provider, model_name=credential.model,
                      api_key=credential.api_key)
```

Use cookie name `squrve_session`, `secure=is_hf_space()`, `httponly=True`, `samesite="Lax"`, `max_age=1800`. Same-origin validation must compare `Origin` to `request.host_url` for hosted mutations and reject missing/foreign origins only when an Origin header is present, so non-browser tests and same-origin clients remain usable.

Implement validation through the same Squrve provider implementation used by SQL generation, with a small non-streaming request and a short validation timeout:

```python
def _validate_sql_credential(credential: SqlCredential) -> None:
    demo = _session_demo(credential)
    llm = demo.engine.dataloader.llm
    if llm is None:
        raise SqlAuthError("unsupported_provider")
    llm.time_out = min(float(llm.time_out), 20.0)
    llm.complete("Reply with OK only.")
```

The production helper owns error classification; tests monkeypatch the outbound completion. Do not validate by mutating `_runtime_llm`, calling `/api/provider`, or running a SQL workflow.

- [ ] **Step 5: Implement the four SQL auth routes**

Return stable payloads and codes:

```json
{"status":"ok","configured":true,"provider":"qwen","model":"qwen-plus"}
{"status":"error","code":"credential_rejected","message":"The qwen credential was rejected."}
```

`POST /api/sql-auth/test` validates but does not store. `PUT` validates, stores, and sets the cookie. `DELETE` removes the entry and expires the cookie. Validate provider/model against `_provider_models` before any outbound call. Map timeouts/5xx to `provider_unreachable`; 401/403 to `credential_rejected`; never include the raw exception.

- [ ] **Step 6: Resolve hosted query credentials from the browser session**

In `/api/query`, branch only for `hf-space`: ignore submitted provider/model values, load the stored `SqlCredential`, return `401 {code:"auth_required"}` when absent, and instantiate a request-scoped demo. Preserve `_get_demo()` and the local provider workflow unchanged. Never cache a hosted demo because its Router owns the credential.

- [ ] **Step 7: Update hosted capability and route policy**

Add `session_sql_auth: hosted` and leave `provider_configuration: not hosted`. Extend CORS methods to `GET,POST,PUT,DELETE,OPTIONS`.

- [ ] **Step 8: Run focused tests**

Run: `pytest -q tests/test_session_credentials.py tests/test_space_api.py tests/test_demo_deployment.py`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add demo/gradio_demo.py demo/api_server.py demo/deployment.py tests/test_space_api.py tests/test_demo_deployment.py
git commit -m "feat: add hosted SQL session authentication"
```

## Task 3: Build the hosted SQL API dialog

**Files:**

- Create: `demo-app/src/SqlAuthDialog.jsx`
- Create: `demo-app/src/SqlAuthDialog.test.js`
- Create: `demo-app/src/testDom.js`
- Modify: `demo-app/src/main.jsx:1-140,153-215,515-528`
- Modify: `demo-app/src/styles.css`
- Modify: `demo-app/package.json`
- Modify: `demo-app/package-lock.json`

- [ ] **Step 1: Install the DOM component-test dependencies**

Run: `cd demo-app && npm install --save-dev @testing-library/react @testing-library/user-event jsdom`

Create `testDom.js` to install and clean up one jsdom document for Node's test runner. Do not introduce Jest/Vitest or change the existing `node --test src/*.test.js` script.

- [ ] **Step 2: Write failing component tests**

Cover provider search, model selection, password masking, show/hide, test-without-save, save, disconnect, error rendering, and input clearing after save/close:

```javascript
assert.equal(screen.getByLabelText('API key').type, 'password')
await user.click(screen.getByRole('button', { name: 'Test connection' }))
assert.equal(fetchCalls[0].path, '/api/sql-auth/test')
assert.equal(screen.getByLabelText('API key').value, 'key-a')
await user.click(screen.getByRole('button', { name: 'Use for this session' }))
assert.equal(screen.getByLabelText('API key').value, '')
```

- [ ] **Step 3: Run and confirm the missing-component failure**

Run: `cd demo-app && node --test src/SqlAuthDialog.test.js`

Expected: FAIL because `SqlAuthDialog.jsx` does not exist.

- [ ] **Step 4: Implement the controlled dialog**

Use `api(path, {method, body})` rather than the POST-only helper. Set `autoComplete="off"` on the form and `autoComplete="new-password"` on the key. Keep the key only in component state and clear it on save, cancel, close, disconnect, and unmount. Do not use `localStorage` or `sessionStorage`.

- [ ] **Step 5: Integrate the dialog and hosted status**

When `session_sql_auth` is enabled, `Topbar` shows `Configure SQL API` or `provider / model · Connected`. The Studio provider/model panel becomes read-only session status in hosted mode; local mode continues to render the existing `ProviderConfig`. Replace the hosted banner with `Bring your own SQL and Pi credentials · session only`.

- [ ] **Step 6: Run frontend tests and build**

Run: `cd demo-app && npm test && npm run build`

Expected: all tests PASS and Vite build succeeds.

- [ ] **Step 7: Commit**

```bash
git add demo-app/src/SqlAuthDialog.jsx demo-app/src/SqlAuthDialog.test.js demo-app/src/testDom.js demo-app/src/main.jsx demo-app/src/styles.css demo-app/package.json demo-app/package-lock.json
git commit -m "feat: add session SQL API dialog"
```

## Task 4: Convert the Pi bridge to native in-memory auth

**Files:**

- Modify: `demo/pi_agent_bridge.mjs`
- Modify: `tests/pi_agent_bridge.test.mjs`

- [ ] **Step 1: Write failing protocol tests with a fake Pi SDK**

Assert that hosted mode calls `AuthStorage.inMemory()` and `ModelRegistry.inMemory(authStorage)`, starts with no server credential, and emits only metadata:

```javascript
assert.deepEqual(events[0], { type: 'auth_catalog', providers: expectedProviders })
send({ type: 'auth_start', provider: 'anthropic', method: 'api_key' })
assert.equal(events.at(-1).type, 'auth_prompt')
assert.equal(events.at(-1).kind, 'secret')
send({ type: 'auth_prompt_response', request_id, value: 'pi-key' })
assert.equal(authStorage.get('anthropic').type, 'api_key')
assert.equal(JSON.stringify(events).includes('pi-key'), false)
```

Also cover OAuth `notify` events, cancellation, model selection, logout, prompt-before-auth, and bridge shutdown.

- [ ] **Step 2: Run and confirm unsupported-command failures**

Run: `node --test tests/pi_agent_bridge.test.mjs`

Expected: FAIL on `auth_start` and because hosted mode currently calls file-backed `AuthStorage.create()`.

- [ ] **Step 3: Refactor startup to separate auth/model state from agent creation**

For `hosted-readonly`, construct:

```javascript
const authStorage = sdk.AuthStorage.inMemory()
const modelRegistry = sdk.ModelRegistry.inMemory(authStorage)
```

Use `getAll()` to build a provider catalog grouped by `model.provider`; use `getProviderDisplayName()`, `getProviderAuthStatus()`, and `authStorage.getOAuthProviders()` for display/auth methods. Do not copy provider lists into React or Python. Emit `ready`, `auth_catalog`, `auth_status`, and `model_catalog` without credential values.

- [ ] **Step 4: Implement a single pending Pi-native auth interaction**

Maintain `{requestId, resolve, reject}` only while an auth prompt is active. For API keys, emit one Pi-styled `secret` prompt then call:

```javascript
authStorage.set(provider, { type: 'api_key', key: response })
modelRegistry.refresh()
```

For subscription/OAuth, call `authStorage.login(provider, { prompt, notify })`; translate Pi's `text`, `secret`, `select`, `manual_code` prompts and `auth_url`, `device_code`, `progress` events without interpreting provider-specific content. `auth_cancel` rejects the pending promise with a typed cancellation and removes partial auth.

- [ ] **Step 5: Implement Pi-native model selection and lazy agent creation**

Resolve `modelRegistry.find(provider, model)`, require `hasConfiguredAuth(model)`, then create the `AgentSession` on first selection. For later selections call `await session.setModel(model)`. A prompt with no authenticated selected model emits `auth_error {code:"auth_required"}` instead of terminating the bridge. `logout` calls `authStorage.logout(provider)`, refreshes catalog/status, and clears the active session/model when it belongs to that provider.

- [ ] **Step 6: Keep local behavior compatible**

Local mode may continue with `AuthStorage.create()` and `ModelRegistry.create(...)`, including environment/file credentials and configured startup model. Hosted mode must not read `auth.json`, `models.json`, or provider environment keys.

- [ ] **Step 7: Run bridge tests**

Run: `node --test tests/pi_agent_bridge.test.mjs`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add demo/pi_agent_bridge.mjs tests/pi_agent_bridge.test.mjs
git commit -m "feat: add Pi native session authentication"
```

## Task 5: Relay typed Pi auth commands over the existing WebSocket

**Files:**

- Modify: `demo/pi_backend.py`
- Modify: `demo/pi_api.py`
- Modify: `tests/test_pi_backend.py`
- Modify: `tests/test_pi_api.py`

- [ ] **Step 1: Write failing backend and WebSocket tests**

Test all allowed command types, unknown-command rejection, exact event forwarding, session-stop cleanup, and public-state redaction. Include a fake key and assert it never appears in `public_state()`, HTTP JSON, captured logs, or non-prompt events.

- [ ] **Step 2: Run focused tests and confirm auth commands are rejected**

Run: `pytest -q tests/test_pi_backend.py tests/test_pi_api.py`

Expected: FAIL because only `prompt` and `abort` are accepted.

- [ ] **Step 3: Add one typed command entry point to `PiAgentSession`**

```python
PI_CLIENT_COMMANDS = {
    "auth_start", "auth_prompt_response", "auth_cancel",
    "model_select", "logout", "prompt", "abort",
}

def send_command(self, command: Mapping[str, object]) -> None:
    command_type = str(command.get("type", ""))
    if command_type not in PI_CLIENT_COMMANDS:
        raise ValueError("Unsupported Pi client command")
    self._write_command(dict(command))
```

Keep `send_prompt()` as a small compatibility wrapper. Do not log command bodies.

- [ ] **Step 4: Extend the WebSocket relay**

Accept the allowlisted command objects and forward them unchanged to the child. Continue broadcasting bridge events unchanged. Close/stop must terminate the child, which destroys in-memory Pi credentials. Do not add an HTTP Pi-key endpoint or Python credential store.

- [ ] **Step 5: Remove hosted provider secrets from child environment**

In `PiBackendSettings`/child environment construction, pass provider environment variables only for local mode. Hosted mode receives runtime/profile/tool configuration but no `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `QWEN_API_KEY`, or Squrve SQL key.

- [ ] **Step 6: Run focused tests**

Run: `pytest -q tests/test_pi_backend.py tests/test_pi_api.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add demo/pi_backend.py demo/pi_api.py tests/test_pi_backend.py tests/test_pi_api.py
git commit -m "feat: relay Pi authentication protocol"
```

## Task 6: Add a Pi TUI-inspired React authentication dialog

**Files:**

- Create: `demo-app/src/piAuth.js`
- Create: `demo-app/src/piAuth.test.js`
- Create: `demo-app/src/PiAuthDialog.jsx`
- Create: `demo-app/src/PiAuthDialog.test.js`
- Modify: `demo-app/src/AgentHarness.jsx`
- Modify: `demo-app/src/styles.css`

- [ ] **Step 1: Write failing reducer and component tests**

Cover catalog search, `API key`/`subscription` badges, secret/text/select/manual-code prompts, authorization link, device code, progress, cancellation, model selection, logout, error states, and clearing secret input after every response/close.

```javascript
state = piAuthReducer(state, { type: 'auth_prompt', kind: 'secret', request_id: 'r1' })
state = piAuthReducer(state, { type: 'AUTH_INPUT', value: 'pi-key' })
const command = commandForPrompt(state)
assert.deepEqual(command, { type: 'auth_prompt_response', request_id: 'r1', value: 'pi-key' })
state = piAuthReducer(state, { type: 'AUTH_INPUT_CLEARED' })
assert.equal(JSON.stringify(state).includes('pi-key'), false)
```

- [ ] **Step 2: Run and confirm missing-module failures**

Run: `cd demo-app && node --test src/piAuth.test.js src/PiAuthDialog.test.js`

Expected: FAIL because the reducer and dialog do not exist.

- [ ] **Step 3: Implement the protocol reducer**

Keep transient input outside the durable event transcript. Normalize only message transport/state transitions; retain Pi-provided display names, prompt text, choices, URLs, and progress text verbatim. Never store a submitted secret in chat history.

- [ ] **Step 4: Implement the dialog using Pi TUI interaction structure**

Mirror the hierarchy of Pi's `OAuthSelectorComponent` and `LoginDialogComponent`: provider search/list, auth-method choice, prompt panel, progress/events, completion, then model list. Render it as an accessible browser dialog styled like the existing chat—not an xterm/terminal emulator. External auth URLs use `target="_blank" rel="noreferrer"`.

- [ ] **Step 5: Integrate with `AgentHarness`**

Open `Login` from the Agent header, send auth commands over the active WebSocket, and route auth events into `PiAuthDialog` instead of the chat transcript. Disable message submit until an authenticated model is selected. Show `provider / model · Connected`; expose `Switch model` and `Logout`. Closing the agent session clears all Pi auth UI state.

- [ ] **Step 6: Run frontend tests and build**

Run: `cd demo-app && npm test && npm run build`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add demo-app/src/piAuth.js demo-app/src/piAuth.test.js demo-app/src/PiAuthDialog.jsx demo-app/src/PiAuthDialog.test.js demo-app/src/AgentHarness.jsx demo-app/src/styles.css
git commit -m "feat: add Pi native login dialog"
```

## Task 7: Harden the integrated hosted credential boundary

**Files:**

- Modify: `tests/test_space_api.py`
- Modify: `tests/test_pi_api.py`
- Modify: `tests/test_hf_space_bundle.py`
- Modify: `README.md`
- Modify: `demo/README.md`

- [ ] **Step 1: Add cross-stack security regression tests**

Use two Flask clients, two fake Pi processes, `caplog`, and sentinel SQL/Pi secrets. Prove:

- each browser receives only its SQL credential;
- each Pi child receives only its own Pi auth response;
- SQL credentials never appear in Pi child environment/commands;
- Pi credentials never appear in `SqurveDemo` config;
- disconnect, timeout, process stop, and capacity eviction remove access;
- JSON responses, logs, and built frontend contain neither sentinel.

- [ ] **Step 2: Run the security tests**

Run: `pytest -q tests/test_space_api.py tests/test_pi_api.py tests/test_hf_space_bundle.py`

Expected: PASS.

- [ ] **Step 3: Update public documentation**

Document the two independent buttons and credential lifetimes. State that the public Space has no shared model key, credentials are held in memory for at most 30 idle minutes, browser refresh/restart may require re-entry, and Pi remains read-only. Remove instructions implying `QWEN_API_KEY` is required as a Space secret for public use.

- [ ] **Step 4: Rebuild embedded Pi and the frontend**

Run: `bash demo/build_embedded_pi.sh`

Run: `cd demo-app && npm ci && npm test && npm run build`

Expected: Pi build, frontend tests, and production build PASS.

- [ ] **Step 5: Run the full repository release check**

Run: `python tools/release_check.py`

Expected: PASS with no credential sentinels in output.

- [ ] **Step 6: Build and test the Hugging Face bundle**

Run: `python tools/build_hf_space.py`

Run: `pytest -q tests/test_hf_space_bundle.py`

Expected: bundle contains both dialogs, embedded Pi dist, and no provider key.

- [ ] **Step 7: Commit**

```bash
git add tests/test_space_api.py tests/test_pi_api.py tests/test_hf_space_bundle.py README.md demo/README.md
git commit -m "docs: document session credential workflow"
```

## Task 8: Publish and verify GitHub and Hugging Face Space

**Files:**

- Verify only; no new source file expected unless release checks expose a defect.

- [ ] **Step 1: Review the complete branch diff**

Run: `git status --short && git diff origin/main...HEAD --stat && git diff --check`

Expected: only planned files changed; no whitespace errors or secret-like values.

- [ ] **Step 2: Run final verification from the repository root**

Run: `pytest -q`

Run: `node --test tests/pi_agent_bridge.test.mjs`

Run: `cd demo-app && npm test && npm run build`

Run: `python tools/release_check.py`

Expected: every command PASS.

- [ ] **Step 3: Push the reviewed commits to GitHub**

Run: `git push origin main`

Expected: remote `main` advances to the reviewed HEAD. Wait for GitHub Actions and require all checks to pass before Space deployment.

- [ ] **Step 4: Upload one generated bundle commit to the existing Space**

Run: `hf upload zmmjjkk/SqurveBridge build/hf-space . --repo-type space --commit-message "feat: add session API configuration"`

Expected: one Hugging Face commit is created and the Space rebuild starts.

- [ ] **Step 5: Verify the running Space without a real credential**

Check:

```bash
curl -fsS https://zmmjjkk-squrvebridge.hf.space/api/health
curl -fsS https://zmmjjkk-squrvebridge.hf.space/api/capabilities
curl -fsS https://zmmjjkk-squrvebridge.hf.space/api/sql-auth
curl -fsS https://zmmjjkk-squrvebridge.hf.space/api/agent
```

Expected: HTTP 200; SQL is initially disconnected; Pi is available with `hosted-readonly`; no shared provider is reported as configured.

- [ ] **Step 6: Browser acceptance test with disposable credentials**

Confirm both dialogs render, SQL and Pi accept different providers/keys, chat resembles the Pi-style dialog, SQL generation and Pi chat work independently, logout/disconnect clear their states, a second private browser session is isolated, and no secret appears in DevTools response bodies or console logs. Revoke disposable keys after the check.

- [ ] **Step 7: Record the verified revisions**

Record the GitHub commit SHA, GitHub Actions run URL, Hugging Face commit SHA, and live Space URL in the release handoff. If deployment fails, roll the Space back to the last verified commit before debugging further.
