# Assurance case

This document argues that trash-watch meets its [security requirements](security.md). It describes the
threat model, identifies the trust boundaries, shows how secure design principles were applied, and lists
how common weaknesses are countered, with pointers to the files and tests that back each claim. How the
check works is in [architecture.md](architecture.md).

The top-level claim is:

> **Deployed as documented, trash-watch reports drift between a Recyclarr config and the TRaSH Guides
> without changing that config, without sending its secrets anywhere, without executing anything from the
> config or the guides, and with releases whose origin can be verified, within the limits stated in
> [security.md](security.md).**

It rests on four arguments: the threat model is understood (1), every trust boundary is mediated or
explicitly accepted (2), the design follows secure design principles (3), and the implementation counters
common weaknesses and is continuously verified (4, 5).

## 1. Threat model

**Assets**, most valuable first: the Recyclarr config (it decides what Radarr and Sonarr download, and it
may contain their API keys inline); the notification URLs in `.env` (anyone holding them can post to the
operator's Discord channel or ntfy topic); the integrity of the findings (no false silence that hides
drift, no false alarms that train the operator to ignore them); the integrity of the published image and
release files; and the host trash-watch runs on.

**Actors and what they may try:**

| Actor | Trusted with | Threats considered |
| --- | --- | --- |
| TRaSH Guides repository (upstream) | Publishing guide JSON | Malformed or hostile JSON: oversized files, unexpected types, names crafted to break the notification markup or YAML output; a compromised upstream publishing misleading data. |
| Recyclarr config author (the operator) | Everything in the config | A config shape trash-watch doesn't understand, leading to silently wrong findings. |
| Notification service (Discord, ntfy) | Receiving reports | Slow or failing endpoints stalling the loop; a typo'd URL pointing somewhere unintended. |
| Network attacker | Nothing | Tamper with the guides fetch or the notifications in transit; read the notification URLs. |
| Contributor | Proposing changes | A pull request that adds a write path to the config, a credential, or a malicious workflow change. |
| Supply chain | Nothing beyond what's pinned | A tampered base image, Python package or GitHub Action; a tampered trash-watch image between registry and user. |

**Out of scope** (see [security.md](security.md#what-trash-watch-does-not-protect-against)): anyone with
write access to the host, its Docker daemon, `.env`, the Recyclarr config directory or `data/`; the
correctness of the TRaSH Guides themselves; vulnerabilities in Python, git or the base image (handled by
updating them, [dependencies.md](dependencies.md)).

## 2. Trust boundaries

| # | Boundary | What crosses it | How it is mediated |
| --- | --- | --- | --- |
| B1 | Recyclarr config → trash-watch | YAML files, includes | Mounted read-only (`:ro` in [`docker-compose.yml`](../docker-compose.yml)); parsed with a `yaml.SafeLoader` subclass that turns `!secret`/`!env_var` into their names without resolving them ([`trash_watch.py`](../trash_watch.py) `Loader`, `load_yaml`; tested in `test_secret_and_env_var_tags_load_without_being_resolved`). Includes resolve only to files under the config directory or Recyclarr's template checkout. Unknown keys and missing includes are logged, not guessed at (`test_missing_include_and_unknown_key_are_warned`). |
| B2 | TRaSH Guides (GitHub) → trash-watch | git objects, JSON | Fetched over HTTPS by git with certificate verification; only `docs/json` is checked out (sparse, shallow; `test_sync_guides_clones_only_the_json_then_follows_upstream`); parsed with `json.loads` as data and never executed. |
| B3 | trash-watch → Discord / ntfy | Report text | Only `https://` or `http://` URLs are opened (`test_non_http_notifier_urls_are_refused`); 15 s timeout; each target sent separately so one failure doesn't stop the other (`test_each_notifier_is_sent_separately`); messages contain only instance, profile and CF names, trash_ids and scores, never config values such as API keys. |
| B4 | trash-watch → host | Files | The only writable mount is `./data` (guides cache and `state.json`); no ports are published. |
| B5 | Contributor → repository | Pull requests | `main` accepts changes only through pull requests that pass the required CI check; DCO sign-off; secret scanning with push protection and gitleaks in CI; workflows from forks get read-only tokens and no secrets; CodeQL analyses the code and workflows. |
| B6 | Upstream → build → GHCR → user | Base image, packages, Actions, the published image | Base image pinned by version and digest, PyYAML and the dev tools by hash, Actions by commit SHA; the release workflow signs the image keylessly (identity: the workflow on the tag), attaches SBOM and provenance, and signs the release checksums; users verify with cosign ([verifying-releases.md](verifying-releases.md)). |

### Attack surface

trash-watch listens on nothing. Its inputs are the config files (trusted, read-only), the guide JSON
(untrusted data from a well-known public repository, fetched over HTTPS), and the HTTP responses of the
notifiers (only their status matters). The full list of settings, mounts and connections is in
[interfaces.md](interfaces.md).

## 3. Secure design principles

| Principle | How trash-watch applies it |
| --- | --- |
| Economy of mechanism | One script with one dependency (PyYAML); git and the standard library do the rest. |
| Fail-safe defaults | The config mount is read-only; compose refuses to start without `RECYCLARR_CONFIG_PATH`; with no notifier set, findings only go to the log; a profile that matches no guide profile is reported as "not checked" rather than guessed at. |
| Complete mediation | Every notification URL is checked for scheme before every send; every config file goes through the same safe loader. |
| Open design | Everything is public and documented; security rests on the operator's `.env` and file permissions, not on secrecy of the code. |
| Separation of privilege | Publishing a release needs both a tag pushed by the maintainer and the release workflow's identity; changes to `main` need a pull request and a passing check. |
| Least privilege | Read-only config mount; no published ports; workflows default to read-only tokens and each job asks only for what it needs; a server that pulls the repository needs only a read-only, single-repository deploy key. The container still runs as root inside its namespace (planned: non-root, [roadmap](roadmap.md)). |
| Least common mechanism | trash-watch shares nothing with Recyclarr but the read-only directory; it has its own container and state. |
| Psychological acceptability | One `.env` with placeholders for every setting; `--suggest` prints fixes for the operator to review and paste, so the safe path (review, then `recyclarr sync --preview`) is also the easy one. |

## 4. Countering common weaknesses

| Weakness | Countermeasure | Evidence |
| --- | --- | --- |
| Deserialization of untrusted data (CWE-502) | YAML only through a `SafeLoader` subclass; JSON with the standard library | `Loader` / `load_yaml` in [`trash_watch.py`](../trash_watch.py); ruff's bandit rule S506 in CI, with the one reviewed exception |
| Hard-coded or committed credentials (CWE-798, CWE-312) | Secrets only in the gitignored `.env`; gitleaks over the full history in CI; push protection | [`.gitignore`](../.gitignore), [`ci.yml`](../.github/workflows/ci.yml) |
| Exposure of sensitive information (CWE-200) | Config values (API keys, base URLs) are never logged or sent; only names and trash_ids are | `check()`, `render()` and `render_suggestions()` only format names, trash_ids and scores; the config's `api_key` and `base_url` are never read by any check |
| SSRF / unexpected URL schemes (CWE-918, CWE-73) | Notification URLs must be `http(s)://`; the guides repository URL is a constant | `post()`; `test_non_http_notifier_urls_are_refused` |
| OS command injection (CWE-78) | git runs with an argument list, never a shell; the only variable arguments are this script's own paths | `git()` in [`trash_watch.py`](../trash_watch.py); ruff S603 with a reviewed exception |
| Unintended writes to the operator's config (CWE-732) | Read-only mount; no code path writes outside `data/`; `--suggest` prints only | [`docker-compose.yml`](../docker-compose.yml); `test_suggest_only_prints` (config bytes unchanged, no state written) |
| Uncontrolled resource consumption (CWE-400) | Shallow, sparse clone of `docs/json` only; 15 s notifier timeouts; notifications capped at about 20 lines and Discord's 2,000 characters | `sync_guides()`; `test_notification_is_capped_for_a_phone` |
| Incorrect logic hiding drift | Each check has a fixture case; an exact-findings test catches new false positives; profile coverage is logged on every run | [`tests/`](../tests/); `test_exactly_the_expected_findings`, `test_unmatched_and_ignored_profiles_are_logged_not_silently_skipped` |
| Inclusion of functionality from an untrusted source (CWE-829, CWE-494) | Digest-pinned base image, hash-pinned packages, SHA-pinned Actions; signed releases | [`Dockerfile`](../Dockerfile), [`requirements.txt`](../requirements.txt), the workflows; OpenSSF Scorecard (Pinned-Dependencies) |
| Injection into CI scripts (CWE-78, CWE-94) | Untrusted values reach `run:` scripts only through `env:`; no `pull_request_target` | actionlint and shellcheck in CI; CodeQL for Actions |
| Use of components with known vulnerabilities (CWE-1395) | Dependabot for the base image, packages and Actions; dependency review on pull requests | [dependencies.md](dependencies.md) |

## 5. Verification evidence

On every push and pull request, CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs ruff
(including the bandit security rules) and `ruff format`, yamllint, actionlint with shellcheck, hadolint,
gitleaks over the full history, the unit tests with a 90 % branch-coverage floor, an image build and start,
and a compose-file check. CodeQL analyses the Python code and the workflows on every change and weekly;
dependency review and a DCO check run on every pull request; OpenSSF Scorecard scores the repository
weekly. Releases are signed and carry an SBOM and provenance.

This document is reviewed when the threat model changes: a new input or output, a new kind of secret, any
code path that writes outside `data/`, or a change to how releases are built.
