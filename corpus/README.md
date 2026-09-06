# Mining corpus

Labeled soil for a future miner. **Not** the promote signal. **Not** sealed hold-out training.

## How to find it

GitHub issues labeled `corpus:mine` in this repo. Index: `corpus/MANIFEST.json`.

Each example cites `issue:N` plus, when the convention is documented, a CONTRIBUTING/CODEOWNERS ref.

## Layers

| Layer | Where | Labels on the issue? |
|---|---|---|
| A. Labeled mining corpus | `corpus:mine` issues | yes — documented conventions, plus one hidden cluster |
| B. Unlabeled eval targets | eval JSON in `arjun7n9s/30hr-build` | no |
| C. Hidden convention | builders: `corpus/HIDDEN.md` | corpus cluster labeled; eval targets unlabeled |

Do not put the hidden rule in CONTRIBUTING.md.
