# Contributing to GaiaAgent

> **Thank you for considering contributing to GaiaAgent and the AURC protocol!**
> 感谢你关注 GaiaAgent 并考虑贡献！

Whether you're fixing a bug, proposing a feature, writing a protocol bridge, or improving documentation — your contribution makes the AI agent ecosystem more connected and more powerful.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting Pull Requests](#submitting-pull-requests)
- [Protocol Changes (AURC-RFC)](#protocol-changes-aurc-rfc)
- [Architecture Decisions](#architecture-decisions)
- [Community](#community)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for everyone, regardless of experience level, gender identity, sexual orientation, disability, personal appearance, body size, race, ethnicity, age, religion, or nationality.

**Be respectful. Be constructive. Be kind.**

---

## How Can I Contribute?

### 🐛 Report Bugs

Found a bug? [Open a bug report](https://github.com/gaiaagent/gaiaagent/issues/new?template=bug_report.md) and include:

- **Python version** (`python --version`)
- **OS** (Linux/macOS/Windows + version)
- **Minimal reproduction** (code snippet or link to repo)
- **Expected vs. actual behavior**
- **Full error traceback** (if applicable)

### 💡 Suggest Features

Have an idea? [Open a feature request](https://github.com/gaiaagent/gaiaagent/issues/new?template=feature_request.md) with:

- **Use case** — what problem does this solve?
- **Proposed API** — how would it look from a developer's perspective?
- **Alternatives considered** — what else did you think about?

### 🔌 Write a Protocol Bridge

One of the most powerful ways to contribute is writing a bridge for a new protocol. See the [Bridge Developer Guide](docs/architecture/bridge-guide.md) for a step-by-step walkthrough.

Current bridges: MCP, A2A, ACP. We'd love bridges for: gRPC, GraphQL, NATS, Kafka, AMQP, or any protocol you use.

### 📝 Improve Documentation

Documentation is a first-class citizen. Typos, unclear explanations, missing examples — all fair game. Documentation PRs are often merged within 24 hours.

### 🧪 Write Tests

Every module should have tests. If you find an untested code path, adding tests is an excellent contribution.

---

## Development Setup

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR-USERNAME/gaiaagent
cd gaiaagent

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. Install with all development dependencies
pip install -e ".[all]"

# 4. Verify everything works
pytest
mypy src/
ruff check src/ tests/
```

---

## Development Workflow

```
1. Pick an issue (or create one)
2. Comment on the issue to let others know you're working on it
3. Create a feature branch from main
4. Write your code + tests
5. Run the full test suite
6. Submit a Pull Request
```

### Branch Naming

```
feature/short-description     # New features
fix/issue-number-description  # Bug fixes
bridge/protocol-name          # New protocol bridges
docs/what-youre-documenting   # Documentation
refactor/what-youre-refactoring  # Refactoring
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(bridges): add gRPC bridge implementation
fix(lifecycle): prevent invalid PAUSED→COMPLETED transition
docs(workflows): add nested pattern examples
test(security): add delegation chain edge cases
refactor(bus): extract routing logic into strategy pattern
```

---

## Code Standards

| Standard | Tool | Configuration |
|:---|:---|:---|
| **Formatting** | `ruff format` | Line length: 100 |
| **Linting** | `ruff check` | Rules: E, F, I, N, W, UP |
| **Type Checking** | `mypy` | Strict mode enabled |
| **Docstrings** | Google style | Bilingual (EN/ZH) encouraged |
| **Async** | `async/await` | All I/O must be async |
| **Models** | Pydantic v2 | For all data structures |

### Quick Commands

```bash
# Format code
ruff format src/ tests/

# Check for issues
ruff check src/ tests/

# Type check
mypy src/

# Run all checks at once
make all
```

---

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/test_lifecycle.py

# With verbose output
pytest -v --tb=short

# With coverage
pytest --cov=src/gaiaagent --cov-report=term-missing

# Run only fast tests (skip integration)
pytest -m "not integration"
```

### Writing Tests

- **Every new function needs tests** — no exceptions
- **Test both happy paths and error paths**
- **Use `pytest-asyncio`** for async tests (configured in `pyproject.toml`)
- **Use descriptive test names**: `test_delegation_chain_rejects_scope_escalation` not `test_delegation`

```python
import pytest

@pytest.mark.asyncio
async def test_bridge_translates_mcp_to_aurc():
    bridge = MCPBridge()
    mcp_msg = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search"}}

    aurc_msg = await bridge.translate_to_aurc(mcp_msg)

    assert aurc_msg.type == MessageDirection.REQUEST
    assert aurc_msg.body.skill == "search"
```

---

## Submitting Pull Requests

### Before You Submit

- [ ] All tests pass (`pytest`)
- [ ] No lint errors (`ruff check src/ tests/`)
- [ ] No type errors (`mypy src/`)
- [ ] New code has tests
- [ ] New public APIs have docstrings
- [ ] `CHANGELOG.md` updated (if applicable)

### PR Description Template

```markdown
## What does this PR do?

Brief description of the change.

## Motivation

Why is this change needed? Link to issue if applicable.

## Changes

- Change 1
- Change 2

## Testing

- How did you test this?
- What tests did you add?

## Checklist

- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes (or documented in CHANGELOG)
```

### Review Process

1. **Automated checks** run (CI, lint, type-check)
2. **At least 1 maintainer** reviews and approves
3. **Address feedback** — push new commits to the same branch
4. **Squash and merge** — maintainers will squash your commits on merge

---

## Protocol Changes (AURC-RFC)

Changes to the AURC protocol specification require a formal **RFC (Request for Comments)** process:

### When to Submit an RFC

- Adding a new message type
- Changing the message format schema
- Adding a new lifecycle state or transition
- Modifying the security model
- Adding a new bridge interface requirement

### RFC Process

```
1. Create: docs/rfcs/AURC-RFC-NNN-short-title.md
2. Include: motivation, specification, backward compatibility, migration plan
3. Open PR: labeled "rfc" for community review
4. Discussion: 2-week public comment period
5. Revision: address feedback
6. Approval: requires 2+ maintainer approvals
7. Implementation: reference implementation in GaiaAgent
8. Standardization: after 2+ independent implementations, becomes part of spec
```

### RFC Template

```markdown
# AURC-RFC-NNN: Title

## Status: Draft | Discussion | Accepted | Rejected

## Motivation
What problem does this solve?

## Specification
Detailed technical specification.

## Backward Compatibility
How does this affect existing implementations?

## Migration Plan
How do existing users upgrade?

## Security Considerations
Any security implications?

## Unresolved Questions
Open questions for discussion.
```

---

## Architecture Decisions

When making significant architectural changes, consider these core principles:

| Principle | Meaning |
|:---|:---|
| **Bridge First** | Don't invent new communication primitives; unify existing protocols |
| **Runtime is King** | Agent = Model + Harness; the Harness is a first-class citizen |
| **Progressive Complexity** | Simple core, enterprise features as optional modules |
| **Protocol-Agnostic Identity** | One agent, one identity across all protocols |
| **Security by Default** | Permissions enforceable at the protocol level, not just declarative |

---

## Community

- **GitHub Issues** — bug reports, feature requests
- **GitHub Discussions** — questions, ideas, community chat
- **Discord** — real-time conversation with other contributors
- **RFC Process** — formal protocol evolution

### Becoming a Maintainer

Active contributors who demonstrate deep understanding of the codebase and protocol may be invited to become maintainers. Maintainers can:

- Merge PRs
- Triage issues
- Participate in architectural decisions
- Review RFCs

---

## License

By contributing to GaiaAgent, you agree that your contributions will be licensed under:

- **Code**: [AGPL-3.0](LICENSE)
- **Documentation**: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Protocol Specification**: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

---

<p align="center">
  <strong>Ready to contribute?</strong>
  <a href="https://github.com/gaiaagent/gaiaagent/issues">Browse open issues →</a>
</p>
