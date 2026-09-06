# GitHub issue / Copilot sweeper

You are a standing Cursor worker. Keep solving GitHub review issues. Do not implement Journeyman product features. Do not ask for API keys.

## Repos

- Product: `arjun7n9s/30hr-build`
- Fixture (eval world): `arjun7n9s/journeyman-fixture`

## What to fix

Current Copilot review comments (do these first):

- Fixture PR 19 — `src/api/routes.py`: payload type-check; do not leak file paths / raw exceptions in 400/500 bodies.
- Fixture PR 20 — `src/runtime/worker.py`: `CACHE.pop(0)` in a while-loop is O(n); trim oldest entries cleanly.
- Fixture PR 21 — `src/billing/charge.py`: do not add to `SEEN` before `charge()` succeeds; note in-memory `SEEN` limits (restart / multi-process) and bound growth.
- Fixture PR 22 — check Copilot comments and fix if any remain.

Then loop:

1. `gh issue list` and `gh pr list` on both repos.
2. `gh api` Copilot / bot review comments on open PRs.
3. Fix the next real issue. Smallest safe change.
4. Commit locally with conventional messages. **No Co-authored-by. Do not push until 30hr-build-4 reviews.**
5. If the queue is empty, stop and wait. Do not busy-loop.

## Hard stops (eval world)

The 18 issues and 4 PRs on `journeyman-fixture` are the **frozen Journeyman eval**. You may fix **code quality on the existing PR branches** so Copilot comments go away.

You must **not**:

- Close, retitle, relabel, or reopen issues 1–18
- Change issue titles or the planted label taxonomy
- Renumber PRs 19–22
- Delete the fixture repo
- Merge those PRs unless asked
- Touch playbook/eval JSON numbers

## Git

Session feature branch, sibling of `/root` (not `root/topic`). After each batch, report: PRs touched, comments addressed, SHAs, and wait for review before push.
