# Embedded Pi Upstream

SqurveBridge vendors the open-source [Pi Agent Harness](https://github.com/earendil-works/pi) at commit `dcfe36c79702ec240b146c45f167ab75ecddd205` (Pi packages `0.80.7`). The upstream source remains licensed under the MIT License in `LICENSE`.

SqurveBridge-specific integration code does not modify Pi internals. It lives in:

- `demo/pi_agent_bridge.mjs` — native Pi SDK session bridge
- `demo/pi_backend.py` and `demo/pi_api.py` — Flask process and chat APIs
- `config/pi_models.json` — project model/provider definitions
- `demo-app/src/AgentHarness.jsx` — Live Demo chat client

Build the embedded runtime with `bash demo/build_embedded_pi.sh`. To update Pi, replace this directory from a reviewed upstream commit, preserve this provenance file, and run the Pi, backend, frontend, security, and release checks.
