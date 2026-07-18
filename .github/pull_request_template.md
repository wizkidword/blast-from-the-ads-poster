## Summary

Explain the user-facing outcome and why this change belongs in the local, review-first workflow.

## Verification

- [ ] I ran the relevant unit tests.
- [ ] I ran `cmd /c Verify-Release.bat` when packaging, dependency, launcher, or release behavior changed.
- [ ] I tested the failure path where this change moves media, writes settings, creates an export, or changes readiness.

## Safety and documentation

- [ ] No credentials, private media, generated outputs, or local settings are included.
- [ ] I updated documentation, templates, or release notes when behavior changed.
- [ ] This change does not add automatic publishing or new external data transfer without a documented user choice.
