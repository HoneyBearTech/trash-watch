# Contributing to trash-watch

trash-watch is a personal project with a single maintainer (see [GOVERNANCE.md](GOVERNANCE.md)).
Contributions are welcome, but there is no service-level agreement, and review may take a while. Releases
are tagged `vMAJOR.MINOR.PATCH`; only the latest release and `main` are supported ([SUPPORT.md](SUPPORT.md)).
Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and suggesting changes

- Use [GitHub Issues](https://github.com/HoneyBearTech/trash-watch/issues) for bugs, questions and ideas.
  A wrong or missing finding is a bug: say which profile, which CF and which guide profile it was checked
  against (the log lists that for every profile), and include the relevant part of your config with
  `api_key` and `base_url` removed. For anything bigger than a small fix, please open an issue first so we
  can agree on the approach. The [roadmap](docs/roadmap.md) says what's planned and what's out of scope.
- **Do not report security vulnerabilities in a public issue.** Follow [SECURITY.md](SECURITY.md) and use
  GitHub's private vulnerability reporting instead.

## Development setup

You need git, Python 3.14 (the image's version), and Docker with Compose v2 for the image and the end-to-end check.

```sh
git clone https://github.com/HoneyBearTech/trash-watch.git && cd trash-watch
make test     # creates .venv with the hash-pinned tools, runs the tests with coverage
make lint     # ruff, ruff format, yamllint
```

trash-watch is one script, [`trash_watch.py`](trash_watch.py); how it works is in
[docs/architecture.md](docs/architecture.md). To try a change against a real config without touching it,
copy the config into a scratch directory, point `RECYCLARR_CONFIG_PATH` at the copy in `.env`, and run one
check that stays off your notifiers:

```sh
docker compose run --rm --build -e RUN_ONCE=1 -e DISCORD_WEBHOOK= -e NTFY_URL= trash-watch
```

`make suggest` prints the `--suggest` output for the same config.

## When and how tests run

Every push and pull request runs one CI job, "Checks + tests"
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), which is the required check on `main`. It runs
the linters below, a gitleaks scan of the whole history, the unit tests with a coverage floor, builds the
image and starts it, and validates the compose file. CodeQL, dependency review, a DCO check and OpenSSF
Scorecard also run on the repository, and Trivy scans the image weekly for known vulnerabilities.

The tests are offline: they run against small fixtures in [`tests/fixtures/`](tests/fixtures/) (a fake
guides tree and a fake Recyclarr config), a local git repository stands in for GitHub, and any attempt to
reach the network fails the test.

[`tests/test_properties.py`](tests/test_properties.py) holds property-based tests (Hypothesis): arbitrary
Unicode thrown at everything that turns names from the guides or the config into output. They run with the
other tests (100 examples each; `pytest --hypothesis-profile=thorough` runs 5,000). The fuzz workflow
([`.github/workflows/fuzz.yml`](.github/workflows/fuzz.yml)) drives the same properties with Atheris,
coverage-guided, on pull requests that change the code and weekly; a crashing input is uploaded as an
artifact and replays with `python fuzz/fuzz_properties.py <target> <file>` on Linux x86_64.

## Before you open a pull request

Run what CI runs and make sure it passes:

```sh
make lint
make test
docker build -t trash-watch:dev .
```

The workflow, Dockerfile and secret scanners run in containers; the exact commands are in
[`ci.yml`](.github/workflows/ci.yml).

## Coding standards

- **Python** (`trash_watch.py`, `tests/`, `fuzz/`): [PEP 8](https://peps.python.org/pep-0008/) and
  [PEP 257](https://peps.python.org/pep-0257/), enforced by [ruff](https://docs.astral.sh/ruff/) with every rule
  family enabled, including type annotations, docstrings and the bandit security rules, and `ruff format`; the
  few rules left out, and why, are in [`pyproject.toml`](pyproject.toml). Everything is type-annotated. YAML is
  always loaded with a safe loader, never `yaml.load` with the full loader.
- **YAML** (compose file, workflows, templates): [yamllint](https://yamllint.readthedocs.io/) with
  [`.yamllint.yml`](.yamllint.yml), warnings treated as errors.
- **GitHub Actions workflows**: [actionlint](https://github.com/rhysd/actionlint), which also runs
  [shellcheck](https://www.shellcheck.net/) on every `run:` script. Actions are pinned by commit SHA, jobs
  ask for the fewest permissions they need, and untrusted values reach scripts through `env:`, never
  `${{ }}` inside `run:`.
- **Dockerfile**: [hadolint](https://github.com/hadolint/hadolint), failing on any finding down to style;
  the base image pinned by version and digest, Python packages installed with `--require-hashes`.
- Exceptions are made per line (for example `# noqa: S603 - reason`) with the reason next to them, never by
  turning a rule off for the whole repository.

## Test policy

- **New functionality comes with automated tests.** A new check gets a fixture case that produces the
  finding and a case that must not; `test_exactly_the_expected_findings` stays exact, so a new false
  positive fails it.
- **Bug fixes come with a regression test** that fails before the fix, where the bug can be tested at all. A
  bug a property or the fuzzer found gets its input pinned as an `@example` on that property.
- **Code that turns names from the guides or the config into output** (notifications, `--suggest`) keeps a
  property in `tests/test_properties.py` and a target in `fuzz/fuzz_properties.py`.
- Unit tests must keep statement and branch coverage of `trash_watch.py` at or above the floor in
  `pyproject.toml` (90 %); CI fails below it.
- Tests never reach the network, a real Recyclarr config, or a notifier.

## Developer Certificate of Origin

Every commit must be signed off to certify the [Developer Certificate of Origin](https://developercertificate.org/):
that you wrote the change or otherwise have the right to submit it under the project's license. Add the
sign-off with `git commit -s`, which appends:

```
Signed-off-by: Your Name <you@example.com>
```

using your git `user.name` and `user.email`. The DCO check
([`.github/workflows/dco.yml`](.github/workflows/dco.yml)) fails a pull request with an unsigned commit; fix
it with `git rebase --signoff main` and force-push your branch.

## Pull requests

- `main` is protected: changes land only through a pull request, and the required CI check must pass. Pull
  requests are squash-merged.
- Keep each pull request focused on one change, and describe what it does and why.
- Update `README.md`, `.env.example`, the docs and `CHANGELOG.md` (under "Unreleased") when you change
  settings or user-visible behaviour.
- **trash-watch only reads.** Nothing may write to the Recyclarr config, remove the `:ro` from its mount, or
  add a way to apply `--suggest` output automatically.
- **This repository is public.** Never commit webhook URLs, API keys, tokens, `.env` files, hostnames or
  addresses. Secret scanning with push protection is on, and CI runs gitleaks over the history.

## Releases

The maintainer adds a `## [x.y.z] - date` section to `CHANGELOG.md`, then pushes a signed tag
(`git tag -s vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`). The release workflow builds, signs and publishes
the image and creates the GitHub Release from that changelog section
([docs/verifying-releases.md](docs/verifying-releases.md)).

## License

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
