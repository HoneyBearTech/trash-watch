# trash-watch documentation

Start with the [README](../README.md) for what trash-watch is and how to run it.

| Document | For |
| --- | --- |
| [Quick start](quick-start.md) | Setting up `.env`, running a one-time check, then leaving it running |
| [Installing](installing.md) | Building from a checkout or running a signed release image, running it securely, uninstalling |
| [User guide](user-guide/README.md) | Reading notifications, getting every profile checked, keeping differences, applying fixes |
| [How it works](architecture.md) | What each run does, what each finding means, and when you get notified |
| [Interfaces](interfaces.md) | Every setting, mount, file, command and outbound connection |
| [Upgrading](upgrading.md) | Moving to a new release, backing up state, and rolling back |
| [Verifying releases](verifying-releases.md) | Checking that images and release files came from this repository, unchanged |
| [Security requirements](security.md) | The read-only rule, where secrets live, what it protects and what it doesn't |
| [Assurance case](assurance-case.md) | The threat model, trust boundaries and why the security requirements are met |
| [Dependencies](dependencies.md) | How dependencies are chosen, pinned, tracked and patched |
| [Roadmap](roadmap.md) | What's planned for the next year, and what trash-watch will not do |

Project policies live at the top of the repository: [CONTRIBUTING.md](../CONTRIBUTING.md),
[GOVERNANCE.md](../GOVERNANCE.md), [SECURITY.md](../SECURITY.md), [SUPPORT.md](../SUPPORT.md),
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) and [CHANGELOG.md](../CHANGELOG.md).

These documents change in the same pull request as the behaviour they describe. If you find one that's
wrong, please [open an issue](https://github.com/HoneyBearTech/trash-watch/issues): it's treated as a bug.
