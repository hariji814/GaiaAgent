# General Engineering Principles

These apply across the entire `src/gaiaagent/` package — every subdomain.

## DRY — Search Before You Build

Before writing any utility, type, helper, or protocol helper, grep the codebase for it.

- Shared cross-domain logic belongs in `src/gaiaagent/core/` — import it, never copy it into another subdomain.
- If you find the same logic in two places while working, consolidate before adding more.
- Duplicated code that diverges silently is worse than no abstraction at all.
- Example: `derive_authz_request` lives in `security/message_authz.py` and is reused by both `BridgeAuthzGuard` and `RouteAuthzGuard` — that is the pattern. Do not re-derive agent_id / resource_type / action in a third place.

## Dead Code

After every change, clean up before considering work done.

- Remove unused imports, variables, functions, types, and files.
- When replacing an implementation, remove the old one entirely — no "just in case" leftovers.
- When renaming or restructuring, hunt every reference down and update or remove it.
- Never comment out code instead of deleting it.
- If unsure whether something is still used, grep for it — do not assume.

## Constants Over Magic Values

No magic strings or numbers anywhere in the codebase.

- Extract literal values that carry meaning to named constants.
- Group constants by domain in dedicated modules (e.g. `core/types.py`, a `constants.py` in the subdomain).
- Constants are the single source of truth — if the same value appears in two places, one should import from the other.

## Domain-Based Organization

GaiaAgent is organized by subdomain (`bridges/`, `bus/`, `core/`, `harness/`, `security/`, `transport/`, …), not by technical type.

- A subdomain owns its modules together — do not reach into another subdomain's internals; import only from its `__init__.py` public exports or the specific module it exposes.
- Cross-domain shared types belong in `core/`.
- When a new responsibility clearly doesn't fit any existing subdomain, add a new one rather than stuffing it into an unrelated one.

## File Size & Single Responsibility

- A file that does two things should be two files.
- When a file exceeds ~200–300 lines, it is a signal to split by responsibility.
- No monolithic files that accumulate unrelated logic over time.

## Self-Documenting Code

- Write code that explains itself through naming and structure — not through comments.
- A comment that restates what the code obviously does is noise.
- Reserve comments for non-obvious decisions: *why* something is done a particular way, not *what* it does.
- The bilingual (English + 中文) comment convention is fine — both halves should add information, not restate each other verbatim.

## Cleanup Is Part of the Task

No change is done until the surrounding area is clean. "Working" and "complete" are different bars.

- Fix the thing you were asked to fix, and remove any related dead code you encounter in the process.
- Do not leave a file in worse shape than you found it.
- `make lint && make type-check && make test` passes are not optional — run them before considering a task done.
