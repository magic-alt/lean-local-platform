# Security Policy

Security matters in this repository because it handles credentials, market-data trust, isolated strategy execution, Paper state, audit evidence, and future broker-facing boundaries.

## Supported versions

This project does not currently publish a certified stable release line.

| Version / branch | Security support |
| --- | --- |
| `main` | Actively maintained |
| Historical commits / archived audit baselines | Not supported |
| Current release certification | **NOT CERTIFIED** |
| Live trading / P9 | **Disabled** |

See [Current Release Status](docs/release-status.md) for the authoritative certification state.

## Reporting a vulnerability

**Do not open a public issue for a suspected security vulnerability.**

Preferred reporting path:

1. Use GitHub's private vulnerability reporting / Security Advisory flow for this repository when it is available.
2. If that channel is unavailable, contact the repository maintainer privately through the GitHub profile for [`@magic-alt`](https://github.com/magic-alt) and request a private channel before sharing exploit details, credentials, tokens, or sensitive logs.

Please include enough information to reproduce and assess the issue safely:

- affected commit, branch, component, or endpoint;
- vulnerability class and realistic impact;
- minimal reproduction steps or proof of concept;
- required privileges and deployment assumptions;
- whether secrets, broker credentials, market data, or user data are exposed;
- suggested remediation, if known.

Never include real provider tokens, database passwords, RabbitMQ credentials, API tokens, runner tokens, broker credentials, or private market-data payloads in a report.

## High-priority security boundaries

Reports are especially valuable when they involve:

- authentication or authorization bypass;
- leakage of `.env`, provider credentials, database credentials, API tokens, or runner tokens;
- path traversal, arbitrary file access, or unsafe artifact extraction;
- command injection, code execution, or container / native-runner sandbox escape;
- unauthorized Docker socket or host filesystem access;
- unsafe image selection or digest / allowlist bypass;
- SQL injection or unauthorized control-plane writes;
- integrity failures in DataRelease, manifests, checksums, lineage, or research artifacts;
- bypass of fail-closed QA, PIT, benchmark, source-certification, or execution gates;
- Paper ledger / fill / checkpoint corruption or replay inconsistencies;
- accidental enablement of broker writes, cancel/replace, OMS live writes, QMT writes, or P9 live activation;
- a vulnerability that can mutate authoritative state from a read-only or observation surface.

## Out of scope

The following are normally not treated as security vulnerabilities unless they create a concrete security impact:

- missing features or unsupported markets;
- expected denial of unsupported live-trading functionality;
- model quality, alpha decay, or investment performance;
- public market-data inaccuracies that are already rejected or quarantined by documented gates;
- findings that require the reporter to first disclose or install their own compromised credentials on the same trusted local account;
- generic dependency-version reports without an exploitable path in this repository.

## Disclosure and remediation

Please keep vulnerability details private until maintainers have assessed the issue and a remediation / disclosure plan has been agreed. The project may request additional reproduction information, coordinate a fix, and credit reporters who want attribution.

A security fix does **not** automatically certify a release. Runtime, migration, API-contract, fault, restore, and soak evidence remain governed by [Release Status](docs/release-status.md).

## Operational security notes

- Never commit `.env` or runtime secrets.
- API and restricted-runner credentials are separate trust domains.
- Production-like LEAN execution should use approved digest-pinned images and bounded mounts/resources.
- RabbitMQ is transport, not a source of business truth.
- PostgreSQL is the control-plane fact store and must not become a market quote store.
- Live broker writes and P9 activation are disabled unless an explicit architecture and security project changes that boundary.
