# Contributing to Blast From the Ads

Thanks for helping improve this local Windows workflow. Small, well-tested changes are easiest to review and safest for people’s media.

## Before you start

- Read [DEVELOPMENT.md](DEVELOPMENT.md) for the supported Windows and Python setup.
- Keep the product local-first and manual-export-first. Do not add automatic publishing or online data transfer without a clearly documented user choice.
- Never commit credentials, local settings, source media, generated outputs, logs, posting packs, or customer information.

## Change process

1. Create a focused branch from the appropriate integration branch.
2. Make the smallest complete change, including documentation when behavior changes.
3. Run the checks that cover your work.
4. Open a pull request using the template and explain how you tested it.

For ordinary Python changes, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall scripts
```

For packaging, launcher, dependency, or release changes, also run:

```powershell
cmd /c Verify-Release.bat
```

## Compatibility and safety

- Preserve existing local workspaces and the safe path checks around inboxes, outputs, and cleanup.
- Keep secrets only in ignored `.env` files. Keep shareable preferences in `settings.example.json`.
- Test failure paths as well as successful paths whenever media movement, recovery, readiness, or exports change.
- Use sanitized test names and fixtures; do not include real campaign media in the repository or an issue.

## Reporting a bug or proposing a feature

Use the issue forms so reports include the information needed to reproduce the behavior without exposing private data. For security-sensitive reports, follow [SECURITY.md](SECURITY.md) instead of posting details in a public issue.
