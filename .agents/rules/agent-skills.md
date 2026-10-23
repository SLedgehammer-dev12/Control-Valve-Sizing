# Agent Skills Framework & Orchestration

Production-grade engineering skills covering every phase of software development: spec, plan, build, verify, review, and ship.

## Intent → Skill Mapping

Automatically identify and invoke the matching skill based on user intent:

- **Feature / New Functionality**: `spec-driven-development` → `incremental-implementation` → `test-driven-development`
- **Architecture / API Design**: `api-and-interface-design`
- **Idea Exploration**: `idea-refine` or `interview-me`
- **Task Planning & Decomposition**: `planning-and-task-breakdown`
- **Constraints / Hard Limits**: `constraint-driven-development`
- **Bug / Failure / Error Recovery**: `debugging-and-error-recovery`
- **Frontend / UI Components**: `frontend-ui-engineering`
- **Code Review**: `code-review-and-quality` (with `code-reviewer` persona)
- **Code Refactoring & Reduction**: `code-simplification` (complements Ponytail lazy senior dev mode)
- **Security & Hardening**: `security-and-hardening` (with `security-auditor` persona)
- **Testing & Test Strategy**: `test-driven-development` (with `test-engineer` persona)
- **Web Performance**: `browser-testing-with-devtools` (with `web-performance-auditor` persona)
- **Release / Pre-Merge**: `shipping-and-launch`

## Specialized Personas

Subagents and roles available for delegated review, audit, and orchestration tasks:

- **`orchestrator` / `cv-orchestrator`**: Master orchestration agent. Runs a state-driven continuous improvement cycle, decomposes tasks, coordinates specialized agents and skills, evaluates results iteratively, and asks user confirmation before applying file changes.
- **`code-reviewer`**: Evaluates changes across 5 dimensions: Correctness, Readability, Architecture, Security, Performance.
- **`security-auditor`**: Focuses on trust boundaries, input validation, secret hygiene, dependency risks, and safe execution.
- **`test-engineer`**: Analyzes test pyramid, regression risks, edge cases, mocking fidelity, and assertions.
- **`web-performance-auditor`**: Inspects Core Web Vitals, payload size, rendering bottlenecks, and cache headers.
- **`ui-ux-engineer`**: Browser, desktop, and Streamlit usability, accessibility, responsive layout, loading/error/stale states, and interaction feedback.
- **`unit-conversion-manager`**: Unit correctness across `units.py`, API conversion endpoints, engine boundaries, and UI unit maps; round-trip and equivalence tests.
- **`cv-engineer`**: Domain sizing calculations, CoolProp HEOS thermodynamics, and vendor catalogs.
- **`cv-reviewer`**: IEC 60534 / ISA formula and unit verification.
- **`cv-documenter`**: Technical documentation, README, and AGENTS.md sync.

## Orchestration Rules

1. **User / Command / Orchestrator**: The `orchestrator` directs the workflow, maps user intent to skills, and dispatches subtasks.
2. **Human-in-the-Loop Confirmation**: The orchestrator MUST ask user approval with a concrete change plan before applying file modifications. An explicit request for continuous development is standing approval for non-destructive, in-scope slices; scope expansion, dependencies, schema/data changes, destructive operations, commits, and pushes still require explicit approval.
3. **Iterative Evaluation & Re-dispatch**: After execution, test results (`pytest`) and lint (`ruff`) are evaluated. If failures occur, the orchestrator formulates remediation tasks and re-dispatches to the responsible agent until green.
4. **Parallel Fan-Out with Merge**: During release or thorough review (`/ship` or `/review`), run `code-reviewer`, `security-auditor`, and `test-engineer` in parallel, then synthesize findings into a single actionable summary.
5. **Dynamic Continuous Improvement**: On `/orchestrate` or "devam", the orchestrator snapshots the current state (`git status`, `pytest`, `ruff`, `mypy`, UI syntax), chooses exactly one highest-value test/UI-UX/development slice, dispatches parallel read-only assessment to `test-engineer`, `ui-ux-engineer`, `unit-conversion-manager`, and `cv-engineer`, then implements under the approval gate. It verifies, re-dispatches failures up to 3 loops, reports, and starts the next state snapshot while standing approval remains. It stops when no valuable slice remains, failures repeat 3 times, a security/data risk appears, scope expands, or the user says stop.
6. **Domain Integration**:
   - For Control Valve Sizing, all engineering domain rules (IEC 60534, ISA-RP75.23, ASME B16.34) take precedence.
   - Code simplification and senior dev mode (`ponytail`) apply to all diffs: keep solutions minimal, robust, and zero-bloat.
