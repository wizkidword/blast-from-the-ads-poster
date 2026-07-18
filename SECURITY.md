# Security Policy

## Supported scope

Please report vulnerabilities that could expose secrets, access local files outside the configured workspace, corrupt or delete media unexpectedly, bypass readiness or integrity checks, or compromise the Windows package and its dependencies.

## Reporting a vulnerability

Do **not** include API keys, media, personal data, customer information, local paths, generated posting packs, or full exploit details in a public issue.

Use GitHub's private vulnerability-reporting option for this repository when it is available. If it is not available, open a minimal public issue requesting a private contact channel, without disclosing the vulnerability itself.

Include only the sanitized information needed to begin triage:

- affected version or commit;
- Windows and Python version;
- a minimal reproduction using safe placeholder paths and files;
- the impact you observed; and
- any mitigation you have already applied.

## Handling

Reports are reviewed privately when a safe contact channel is available. Please allow time to validate a report and prepare a fix before public disclosure. Once a fix is ready, the project will document the affected behavior and any upgrade or mitigation steps without exposing user data.
