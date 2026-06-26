# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in GaiaAgent, please report it
responsibly:

1. **Do NOT open a public GitHub issue.**
2. Email security@gaiaagent.dev with a description and reproduction steps.
3. You will receive an acknowledgment within 48 hours.
4. We will coordinate a fix and disclosure timeline with you.

## Security Features

AURC includes several built-in security mechanisms:

- **CapABAC**: Capability-based access control for agent permissions
- **Delegation chains**: Scope narrowing validation (prevents confused deputy)
- **Audit logging**: Tamper-evident event trail for all agent actions
- **Protocol-level auth**: Token references (not raw tokens) in messages

## Scope

The AURC protocol design includes security as a first-class concern, but the
v0.1 reference implementation has not yet undergone a formal security audit.
Do not use it in production security-critical environments without additional
hardening.
