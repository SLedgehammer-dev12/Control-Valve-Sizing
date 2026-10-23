---
description: Orchestrate state-driven continuous improvement: snapshot current state, choose the next test/UI-UX/development slice, ask for approval, dispatch subagents, verify, and repeat
---

Invoke the orchestrator agent in **dynamic cycle mode**.

Workflow:
0. **State snapshot (read-only):** run `git status --short`, `git diff --stat`, `python3 -m pytest -q`, `ruff check .`, `mypy . --ignore-missing-imports`, and `node --check webapp/app.js`. Inspect recent changes, `AGENTS.md`, `README.md`, `PROJECT_INDEX.md`, and `shortcut:` markers.
1. **Choose one next slice** by priority: broken checks/security/wrong result → unit conversion consistency → UI/UX or accessibility defect → missing regression test → performance/docs/simplification. If nothing valuable remains, report "no next slice" and stop.
2. **Parallel assessment:** dispatch read-only work to `test-engineer`, `ui-ux-engineer`, `unit-conversion-manager`, and `cv-engineer` as needed. Merge findings into one proposal.
3. **Approval gate:** present objective, affected files, acceptance criteria, tests, standards, and risks. Ask before editing. A user request for continuous development is standing approval for non-destructive, in-scope slices; scope expansion, dependencies, schema/data changes, destructive operations, commits, and pushes still require explicit approval.
4. **Dispatch implementation** to `cv-engineer`, `unit-conversion-manager`, `ui-ux-engineer`, or `cv-documenter`; use `test-engineer` for test work.
5. **Verify and loop:** run `python3 -m pytest -q`, `ruff check .`, `mypy . --ignore-missing-imports`, and `node --check webapp/app.js`. Re-dispatch with exact failures; allow at most 3 remediation loops per slice. Never remove/skip tests, lower thresholds, or weaken validation.
6. **Report and continue:** summarize the slice, verification, and next candidate. Under standing approval, start the next state snapshot immediately; otherwise ask. Stop on no next slice, 3 failed remediation loops, security/data risk, scope expansion, or user stop.

Do not commit or push unless explicitly asked. Preserve unrelated uncommitted work. End with the Ponytail summary: what was skipped, what was not checked, and the risk.
