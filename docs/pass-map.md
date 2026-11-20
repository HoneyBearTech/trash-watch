# Pass map

A short record of each piece of work on trash-watch: what shipped, or what a review found, and where to
look. Newest first. The reasons behind the choices are in the [decisions log](decisions-log.md); what is
planned next is in the [roadmap](roadmap.md).

| Date | Job | What shipped or was found | Where |
| --- | --- | --- | --- |
| 2026-11-20 | `fuzz-python-hold` | Renovate keeps the fuzz workflow on Python 3.14 (one package rule in `renovate.json`), because Atheris has no Python 3.15 wheels and all seven fuzz jobs of #49 failed installing it. CI, the Dockerfile and the GitLab copy still move to 3.15. Note in `docs/dependencies.md`. #47 and #48 (image digests) merged by the owner the same day. | This pull request; `docs/plans/fuzz-python-hold.md` |
| 2026-11-20 | `renovate-automerge` | Renovate merges its pull requests itself once every check passes, majors included; new versions wait 3 days, security fixes and image rebuilds don't. The fuzz workflow's Python hold stays. `platformAutomerge` is true. Docs now say the GitLab pipeline images are tracked too, and that Renovate acts as its GitHub App. | #51 |
