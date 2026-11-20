# Decisions log

Why things in trash-watch are the way they are: each entry gives the decision, the reason, what was
considered and not done, and review findings that were declined, with why. Newest first. What shipped when
is in the [pass map](pass-map.md).

## 2026-11-20: Renovate merges its own pull requests

Job `renovate-automerge` (#51).

**Decision.** Renovate merges its pull requests itself once every check passes,
majors included; new versions wait 3 days, security fixes and image rebuilds
don't, on the model homelab-atlas already uses. Kept manual: the fuzz workflow's
Python hold stays. `platformAutomerge` is true.

**Why.** The owner asked for every repo with Renovate to merge its updates
automatically (2026-11-20) and chose this model, majors included, over keeping
majors manual.

**Not done.** Repository settings and branch rules (owner only) and workflows
are unchanged. A group merges automatically only when every update in it may, so
each manual exception gets its own pull request.

**Review findings.** Fixed: stale docs that still promised a manual review or
named Dependabot, and (where it applied) exceptions that sat inside the update
group. None declined. Docs now say the GitLab pipeline images are tracked too,
and that Renovate acts as its GitHub App.

## 2026-11-20: the fuzz workflow stays on Python 3.14 until Atheris supports 3.15

Job `fuzz-python-hold`.

**Decision.** A package rule in `renovate.json` keeps the `python-version` of `.github/workflows/fuzz.yml`
below 3.15. Everything else that names a Python version still follows new releases.

**Why.** Renovate's #49 moved the fuzz workflow to 3.15, and Atheris 3.1.0, its newest release, ships wheels
for cp312 to cp314 only, so every fuzz job failed at install. The rest of #49 passes.

**Not done.** Editing #49 by hand (Renovate's next run would undo it); dropping the fuzz workflow's
Python update from Renovate altogether (it would then miss 3.14 patch releases); changing the workflow file
(the owner's).

**Review findings.** Security review: one formatting fix (a missing blank line in `docs/dependencies.md`),
done. Code audit: approved; a simulated Renovate run regenerated #49's branch without the fuzz change and
with no separate pull request. None declined.
