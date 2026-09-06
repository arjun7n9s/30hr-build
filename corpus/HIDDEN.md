# Hidden convention (builders only)

Do not copy this into CONTRIBUTING.md, CODEOWNERS, README, or Journeyman Python.

```
marker: flaky
WHEN title contains "flaky" THEN add labels=type:bug,priority:p1
```

This rule is true in `arjun7n9s/journeyman-fixture` (labeled `corpus:mine` examples H01–H08) and is the P1 mining proof. Unlabeled eval targets that need it: `dev-13`, `dev-14`, `hold-07` (`expects_p1` in MANIFEST.json).
