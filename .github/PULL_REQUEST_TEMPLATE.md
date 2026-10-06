## What and why

<!-- What does this change, and why? Link the issue it closes, if any. -->

## Checklist

- [ ] Every commit is signed off (`git commit -s`), certifying the [DCO](https://developercertificate.org/); see [CONTRIBUTING.md](../CONTRIBUTING.md#developer-certificate-of-origin).
- [ ] `make lint` and `make test` pass locally (CI runs the same, plus the workflow, Dockerfile and secret scanners).
- [ ] New behaviour has tests; a bug fix has a regression test (the [test policy](../CONTRIBUTING.md#test-policy)).
- [ ] User-visible changes are in `CHANGELOG.md` under "Unreleased", and the README / `docs/` / `.env.example` are updated.
- [ ] Nothing here writes to the Recyclarr config, and no secrets, hostnames or addresses are committed.
