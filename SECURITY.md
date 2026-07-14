# Security Policy

SqurveBridge is a research platform under active development. Security fixes
apply to the latest `main` branch.

## Reporting

Do not open a public issue for credentials, private benchmark data, remote code
execution, arbitrary file access, or another exploitable problem. Use GitHub's
private vulnerability reporting. Redact API keys, database credentials,
benchmark records, provider responses, and user data from logs.

## Credential and Data Rules

- Keep provider keys only in the ignored root `.env` or an external secret
  manager. Published configs use placeholders or `${ENV:VARIABLE_NAME}`.
- Treat a key committed anywhere in Git history as compromised: rotate it
  before removing it from every reachable ref.
- Use least-privilege, read-only database credentials for evaluation.
- Do not commit private databases, raw provider responses, run workspaces,
  unapproved archives, recordings, or browser traces. The only approved ZIP
  payloads are `benchmarks/packages/spider.zip` and
  `benchmarks/packages/bird.zip`, governed by the package manifest and stored
  through Git LFS.
- Run `python tools/security_scan.py --history` and
  `python tools/benchmarks.py verify-archives` before a public release.

## Archive Safety

Benchmark archives are treated as untrusted input even when they are versioned in
the repository. Verification rejects unsafe paths, symbolic links, duplicate or
encrypted members, credential files, hidden system metadata, suspicious
compression ratios, checksum mismatches, and unexpected package contents. Never
extract a replacement archive manually into the repository; use
`python tools/benchmarks.py install <benchmark>` so validation occurs before the
installed directory is made visible.
