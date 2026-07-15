# Third-Party Sources and Research Provenance

SqurveBridge is built on the upstream Squrve framework and integrates ideas from
published Text-to-SQL methods. The repository MIT license applies only to
material for which the project can grant that license. Upstream notices,
licenses, and dataset terms continue to apply.

Candidate repositories are algorithm documentation, not vendored runtime
dependencies. A public integration must record its paper, upstream URL, exact
revision, license, local Actor/config mapping, and dataset terms. Small copied or
modified compatibility fragments must retain their original notices.

The original Squrve copyright line remains in `LICENSE`. Spider, BIRD, and every
other benchmark remain governed by their upstream distribution terms; see
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

The embedded Pi Agent runtime under `pi/` was acquired from the
[`earendil-works/pi`](https://github.com/earendil-works/pi) distribution at the
revision recorded in `pi/SQURVEBRIDGE_UPSTREAM.md`; that distribution derives
from the open-source Pi project. Pi is distributed under its upstream MIT
license in `pi/LICENSE`; those notices remain authoritative for vendored files.
