# Public evidence bundles

SqurveBridge evidence bundles are deliberately smaller than private run artifacts. They
preserve aggregate scores and stage-localizable diagnostics without redistributing
benchmark questions, database rows, SQL text, provider payloads, credentials, or local
filesystem paths.

The `reported-results/` directory contains three sanitized snapshots for Spider dev:
C3SQL, DINSQL, and FinSQL, each using deterministic random-100 sampling with seed 42.
They demonstrate the public evidence contract and are not claims about another
provider, prompt, sample scope, or evaluator.

## Export

Prepare a metadata JSON object with these fields:

- `method`, `benchmark`, `split`, `provider`, `model`, `code_commit`, and
  `evaluator_version`: non-empty strings;
- `sample_count`: a non-negative integer;
- `source_alignment`: `source-aligned`, `cross-benchmark`, or `demo`;
- optional `notes`: public, non-sensitive context.

Then run:

```bash
python tools/evidence.py export \
  --run-id spider-c3sql-demo \
  --metadata metadata.json \
  --config private-run/config.json \
  --scores private-run/scores.json \
  --report private-run/report.md \
  --diagnostics private-run/public-diagnostics.jsonl
```

Diagnostics are fail-closed. Each JSONL record must contain `instance_id` and may only
contain `metrics`, `error_category`, `error_categories`, `stage_status`, `token_usage`,
and `latency_ms`. The exporter removes credential configuration and per-sample sections
from aggregate scores, but rejects forbidden fields, secret-like values, and absolute
paths everywhere else.

Existing output directories are never overwritten. Export happens in a temporary
directory and is published atomically only after self-verification.

## Verify

```bash
python tools/evidence.py verify evidence/reported-results/<bundle-id>
```

Verification rejects unknown files or directories, schema drift, invalid privacy
declarations, forbidden content, and checksum mismatches. A bundle contains exactly:

- `manifest.json`
- `config.json`
- `scores.json`
- `report.md`
- `sample-diagnostics.jsonl`
- `checksums.sha256`
