# Support

trash-watch is maintained by one person in their own time (see [GOVERNANCE.md](GOVERNANCE.md)), so this is
a best-effort policy, not a contract.

## Getting help

- **Questions, bugs and ideas**: [GitHub Issues](https://github.com/HoneyBearTech/trash-watch/issues). Say
  which version you run, which profile or finding is involved, and what you expected. Leave out webhook
  URLs, API keys, hostnames and addresses.
- **Security vulnerabilities**: never in a public issue; see [SECURITY.md](SECURITY.md).
- **Documentation**: the [README](README.md) and [docs/](docs/README.md), starting with the
  [quick start](docs/quick-start.md).

## Which versions are supported, and for how long

| Version | Supported with | Until |
| --- | --- | --- |
| The latest release | bug fixes and security fixes | the next release is published |
| An older release | nothing | it stopped being supported when the next release came out |
| `main` | bug fixes and security fixes | always (it's where fixes land first) |

- A fix is released as a new version (a patch release such as 0.1.1 for fixes only), never applied to an
  older release.
- **A release stops receiving security updates the moment the next release is published.** Its notes and
  [CHANGELOG.md](CHANGELOG.md) say what changed and whether upgrading needs steps; upgrading is described in
  [docs/upgrading.md](docs/upgrading.md).
- Before 1.0, a minor release (0.2.0) may change behaviour, settings or the state file; such changes are
  listed in the changelog under "Upgrading".
- trash-watch follows the TRaSH Guides JSON format and Recyclarr's config format as they are when a release
  is made. When either changes in a way that breaks trash-watch, the fix comes in a new release.
- If a supported line will end differently (for example a 1.x line kept alive after 2.0), it will be
  announced in the release notes and in this table first.

Images stay available on GHCR after their support ends, so existing installations keep working, but they
won't get fixes: run the latest release, or `main` from a checkout.
