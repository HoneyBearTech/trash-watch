# Dependencies and vulnerability management

How trash-watch chooses, obtains, tracks and updates what it's built from, and what happens when one of
those dependencies has a vulnerability.

trash-watch is deliberately small: at runtime it needs Python, git and one Python package, PyYAML. The rest
are the tools its checks and tests use and the GitHub Actions in its workflows.

## Choosing a dependency

A new dependency must:

- be open source under an OSI-approved license compatible with MIT and with redistribution in an image (see
  "Licenses" below);
- be actively maintained (releases in the last year, security issues answered) and widely used;
- be worth it: the standard library is preferred, and nothing is added for what a few lines of code can do.
  A runtime dependency in particular needs a reason in the pull request that adds it.

## Obtaining dependencies

All dependencies are fetched by standard tooling from their official registries, pinned so that a build
always gets the same bytes:

| Dependency | Declared in | Pinned by | Fetched by |
| --- | --- | --- | --- |
| Base image (`python:3.14-slim`, which brings Python and Debian) | [`Dockerfile`](../Dockerfile) | version tag and multi-arch digest | Docker / BuildKit |
| git, ca-certificates | [`Dockerfile`](../Dockerfile) | the base image's Debian release | apt |
| PyYAML (runtime) | [`requirements.in`](../requirements.in) → [`requirements.txt`](../requirements.txt) | exact version and SHA-256 hashes (`pip-compile --generate-hashes`) | `pip install --require-hashes --no-deps` |
| Check and test tools (pytest, coverage, Hypothesis, ruff, yamllint, PyYAML) | [`requirements-dev.in`](../requirements-dev.in) → [`requirements-dev.txt`](../requirements-dev.txt) | exact version and SHA-256 hashes | `pip install --require-hashes --no-deps` |
| Atheris (coverage-guided fuzzing, Linux x86_64 only) | [`requirements-fuzz.in`](../requirements-fuzz.in) → [`requirements-fuzz.txt`](../requirements-fuzz.txt) | exact version and SHA-256 hashes | `pip install --require-hashes --no-deps` in [`fuzz.yml`](../.github/workflows/fuzz.yml) |
| Linters and scanners used only by CI (actionlint, hadolint, gitleaks) | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | version tag and digest | Docker |
| GitHub Actions | [`.github/workflows/`](../.github/workflows/) | full commit SHA (version in a comment) | GitHub Actions |

Released images carry an SBOM listing every package in them ([verifying-releases.md](verifying-releases.md)).
To update a pinned Python dependency, edit the `.in` file if needed and run
`pip-compile --generate-hashes --strip-extras <file>.in` (pip-tools).

## Tracking dependencies

- **Dependabot** ([`.github/dependabot.yml`](../.github/dependabot.yml)) checks weekly for new versions of
  the base image, the Python packages and the GitHub Actions, and opens a pull request for each. Dependabot
  alerts and security updates are on.
- **Dependency review** ([`.github/workflows/dependency-review.yml`](../.github/workflows/dependency-review.yml))
  blocks a pull request that adds or changes a dependency with a known vulnerability of moderate severity or
  higher, or with a license outside the allowlist.
- Pull requests are **merged by hand**, never automatically: CI must pass, and a base-image or PyYAML bump
  gets a one-time check against a real config first.
- The CI-only images in `run:` steps aren't seen by Dependabot; they're bumped by hand at least every
  quarter.

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found by Dependabot alerts (Python packages, Actions), dependency review on pull
requests, and the base image's own advisories (Debian and the Python image).

Each finding is triaged within 14 days:

1. **If a fixed release exists**, bump to it (a Dependabot pull request usually already does) and merge. A
   fix for an exploitable critical or high-severity vulnerability goes out in a patch release within 30
   days; others go out with the next release.
2. **If upstream hasn't released a fix**, assess whether the vulnerable code is reachable in trash-watch
   (no listening ports; inputs are a read-only config, the guides JSON and HTTP status codes). If it is
   exploitable, mitigate it where possible and say so in the release notes; otherwise record the reason
   when dismissing the alert. Either way, it's fixed by a bump when upstream ships one.
3. **If a dependency is abandoned** and keeps accumulating vulnerabilities, replace it.

### Current findings

None known as of 6 October 2026. Planned: a scheduled image scan (Trivy) like the maintainer's other
projects, reported to code scanning.

## Licenses

Every dependency must be under an OSI-approved open source license that allows redistribution in an image
(MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 and similar); dependency review enforces the list. yamllint
(GPL-3.0) is allowed as a development tool only: it is never shipped in the image. trash-watch's own files
are MIT-licensed.

## Policy for findings from static analysis (SAST)

CodeQL analyses the Python code and the workflows on every pull request and weekly, and ruff runs the
bandit security rules in CI. A CodeQL finding of medium severity or higher is fixed before the next release,
or, if it is a false positive, dismissed in code scanning with a written reason. A ruff finding fails CI; a
deliberate exception is a per-line `noqa` with the reason next to it.

## Published vulnerabilities

Vulnerabilities in trash-watch itself are published as GitHub security advisories, as described in
[SECURITY.md](../SECURITY.md#published-vulnerabilities).
