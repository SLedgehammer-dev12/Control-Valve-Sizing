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

Subagents and roles available for delegated review and audit tasks:

- **`code-reviewer`**: Evaluates changes across 5 dimensions: Correctness, Readability, Architecture, Security, Performance.
- **`security-auditor`**: Focuses on trust boundaries, input validation, secret hygiene, dependency risks, and safe execution.
- **`test-engineer`**: Analyzes test pyramid, regression risks, edge cases, mocking fidelity, and assertions.
- **`web-performance-auditor`**: Inspects Core Web Vitals, payload size, rendering bottlenecks, and cache headers.

## Orchestration Rules

1. **User / Command as Orchestrator**: Personas do not invoke other personas directly; the orchestrating agent or command directs the workflow.
2. **Parallel Fan-Out with Merge**: During release or thorough review (`/ship` or `/review`), run `code-reviewer`, `security-auditor`, and `test-engineer` in parallel, then synthesize findings into a single actionable summary.
3. **Domain Integration**:
   - For Control Valve Sizing, all engineering domain rules (IEC 60534, ISA-RP75.23, ASME B16.34) take precedence.
   - Code simplification and senior dev mode (`ponytail`) apply to all diffs: keep solutions minimal, robust, and zero-bloat.
