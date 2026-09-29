# Security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository:
**Security -> Advisories -> Report a vulnerability**. It is enabled, and it is
the only channel that stays private until a fix ships.

Please do not open a public issue for a suspected vulnerability.

Expect an acknowledgement within a week. This is a single-maintainer project,
so a fix may take longer than an acknowledgement does.

## Supported versions

Pre-1.0, with no long-term support branches. Only the latest release gets
fixes; there is no backporting to an earlier minor.

| Version | Supported |
| ------- | --------- |
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Scope

MPMB-Copilot is self-hosted and there is no service to test against, so a
report should describe a defect in this repository's code.

Likely in scope:

- Authentication bypass, or a tenant reading another tenant's data
- Path traversal or symlink escape through the source and upload file tools
- A provider credential reaching logs, an API response, or an error page
- Retrieved source or an uploaded document being treated as instructions
  rather than as data
- A write tool applying a change without the human approval it requires

Out of scope:

- Anything that depends on setting `AUTH_DISABLED`. It is honoured only while
  the bind host is loopback, and it is a local development affordance
- Defects in the MPMB character-sheet sources themselves. Those are
  third-party repositories cloned into `data/packs/`, not code we ship
- Denial of service through a deliberately expensive prompt. Turn budgets are
  a cost control, not a security boundary
- Findings that require administrator access to the instance already

## Disclosure

Once a fix is released, the advisory is published and credit is given unless
you ask otherwise.
