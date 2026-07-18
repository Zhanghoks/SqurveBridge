# Local benchmark assets

Benchmark payloads are installed locally and are excluded from Git.  The public
repository contains only code, registration metadata, and approved Spider/BIRD
packages; it never contains benchmark questions, reference SQL, or unreviewed
external databases.

The Live Demo exposes every installed database as a read-only target:

| Benchmark | Demo database | Local source | Space inclusion |
| --- | --- | --- | --- |
| Spider | All installed SQLite databases | `benchmarks/spider/` | Installed package |
| BIRD | All installed SQLite databases | `benchmarks/bird/` | Installed package |
| BULL-EN | All installed SQLite databases | `benchmarks/bull-en/` | Local reference asset |
| EHRSQL-2024 | All installed SQLite databases | `benchmarks/ehrsql-2024/` | Local reference asset |

The packaged benchmark archives contain the complete evaluation payloads,
including questions and reference SQL where supplied upstream. The Space Docker
build unpacks the same archives so hosted evaluation uses the exact packaged
payload. Before publishing a new source or replacing an asset, record the
upstream source, immutable revision or checksum, and license/data-use terms,
then run the repository privacy and security scans.
