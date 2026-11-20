# Plan: keep the fuzz tests on Python 3.14 until Atheris supports 3.15

**What Sean asked for:** "work all open PRs in trash-watch".

## What we found

- **#47 and #48** (two image digest updates in `.gitlab-ci.yml`) are approved by the owner, green and ready
  to merge. Nothing to change in them.
- **#49** (Renovate's group of minor and patch updates) fails all seven fuzz jobs. One of its updates moves
  `python-version` in `.github/workflows/fuzz.yml` from 3.14 to 3.15, and Atheris, the fuzzing library, has
  no build for Python 3.15: its newest release, 3.1.0, ships wheels for Python 3.12, 3.13 and 3.14 only
  (`ERROR: No matching distribution found for atheris==3.1.0`). Every other check on #49 passes, including
  the tests on Python 3.15.
- The fuzz jobs run on GitHub only, not in the GitLab copy.
- The team may not edit workflow files, and editing #49 by hand would be undone by Renovate's next run.
  The lasting fix is a rule in `renovate.json`.

## What we'll change

1. **`renovate.json`: one new package rule** that keeps the Python version in `.github/workflows/fuzz.yml`
   below 3.15. Nothing else in the config changes: the CI workflow, the Dockerfile and the GitLab copy
   still move to 3.15.
   *Checked by:* Renovate's config validator passes in strict mode, and the rule matches only that one
   dependency in that one file.
2. **A short note in `docs/dependencies.md`** (where the repo already explains its dependency updates) saying why the
   fuzz tests stay on 3.14 and when the rule can go: when Atheris publishes wheels for 3.15.
   *Checked by:* review.
3. **After the owner merges this**, Renovate's next run rebuilds #49 without the fuzz workflow change, and
   its fuzz jobs pass. *Checked by:* the checks on #49's new version.

## Who's on it

Team lead, Engineer, Security Officer, code auditor.

## Risks

- If the rule is written wrong, Renovate could hold back other Python updates or keep proposing 3.15 for
  the fuzz workflow. The validator and the review check that it matches only the one dependency.
- The fuzz workflow's comment calls 3.14 "the image's Python", which is already untrue: the Dockerfile on
  `main` is on 3.15. Changing that comment means editing a workflow file, which is the owner's to do.

## Out of scope

- Merging #47, #48 and #49 (the owner merges).
- The workflow comment above, and the places in `GOVERNANCE.md` that still describe Dependabot.
- The repo has no guidelines file; adding one is a separate job.
