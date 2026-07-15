---
title: SqurveBridge Live Demo
emoji: 🌉
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
license: mit
---

# SqurveBridge Live Demo

This Space runs the same Demo App shipped in the SqurveBridge repository: an interactive Text-to-SQL workspace with an embedded open-source Pi Agent backend, built on the upstream Squrve framework.

The hosted environment keeps live LLM-backed SQL generation, read-only execution, Pi chat, and project Skills. Pi is restricted to read-only tools in the public Space; full coding tools remain local-only.

The current Docker image defaults to `qwen/qwen-plus`. Until browser-scoped BYOK
configuration is enabled, a maintainer must add `QWEN_API_KEY` as a private Space
Secret for live SQL generation or Pi chat. Public deployments should add access
controls and usage limits before enabling a shared provider key; never commit it.
