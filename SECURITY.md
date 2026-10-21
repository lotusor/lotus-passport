# Security Policy

## Supported versions

Security fixes are applied to the `main` branch. Older commits and forks are not supported.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub Security Advisories:

<https://github.com/lotusor/lotus-passport/security/advisories/new>

Do **not** open a public issue for a vulnerability, and do not include real user data, credentials, tokens, or production host details in a report.

A useful report includes:

- affected version / commit
- impact and attack preconditions
- minimal reproduction steps or a proof of concept
- suggested fix, if known
- whether the issue is already public

## Response targets

- acknowledgement: within 3 business days
- initial triage: within 7 business days
- fix or mitigation plan for critical issues: within 30 days

These are targets, not guarantees. We will keep you informed through the advisory.

## Scope

In scope:

- authentication, OAuth, PKCE, JWT / JWKS and session handling
- authorization bypass, account takeover, privilege escalation
- injection, SSRF, path traversal, unsafe file upload
- secret exposure in the repository or build artifacts
- supply-chain issues in first-party dependencies

Out of scope:

- reports that only rely on a public IP address or DNS record
- missing hardening headers on non-production deployments
- automated dependency alerts without a demonstrated exploit path
- test fixtures, demo data, or documented placeholder values

## Safe harbor

Good-faith research is welcome. Please avoid privacy violations, data destruction, service disruption, and testing against accounts or data you do not own. If you encounter a real secret, stop, report it privately, and do not use it.

## Repository hygiene

This repository is public. Real credentials, private keys, production runbooks, hand-over documents, and host-specific deployment details must never be committed. If such material is found in history, we rotate the affected credentials first, then purge the history and notify GitHub Support. See [CONTRIBUTING.md](CONTRIBUTING.md) for the admission rules.
