---
name: repo-indexer
description: "Repository indexing, structural mapping, dependency graphing, and token-efficient context summarization for Control Valve Sizing. Covers project directory scanning, entry point mapping, internal/external dependency analysis, change hotspot detection, freshness tracking, and generation of PROJECT_INDEX.md / PROJECT_INDEX.json. USE FOR: re-indexing the repository after structural changes, generating compressed context for agents, assessing code churn and risk surfaces, verifying dependency health."
license: MIT
metadata:
  project: control-valve-sizing
  version: "1.0"
  staleness_threshold_days: 7
---

# Repository Indexer Skill

Autonomous repository indexer for the Control Valve Sizing project (v3.3.0). Provides automated structural scanning, dependency analysis, change intelligence, and token-efficient summarization for AI agents and human developers.

## Indexing Workflow

### 1. Freshness Detection
- Check whether `PROJECT_INDEX.md` and `PROJECT_INDEX.json` exist.
- Compare `updated_at` against the staleness threshold (7 days default).
- Count commits since the last index update (`git rev-list --count <indexed-commit>..HEAD`).
- If no drift is detected and files are fresh, skip re-indexing.

### 2. Structural & Focus Area Scan
- Inspect focus areas: source code (`*.py`), tests (`test_*.py`, `verify_*.py`), config (`pyproject.toml`, `requirements*.txt`), docs (`README.md`, `AGENTS.md`, `docs/releases/`), workflows (`.github/workflows/`), skills (`.opencode/skills/`).
- Classify modules by architectural tier (presentation, calculation core, thermodynamic data, safety/standards, export/reporting).

### 3. Dependency & Coupling Graphing
- Internal imports: Map fan-in, fan-out, and Robert C. Martin instability index $I = \frac{F_o}{F_i + F_o}$.
- Verify acyclicity (zero circular dependencies).
- External dependencies: CoolProp, fluids, chemicals, pint, iapws, thermo, streamlit, pandas.

### 4. Change Hotspots & Risk Ranking
- Analyze git churn (`git log --name-only`, `git log --numstat`).
- Surface co-commit pairs and files with high bug-fix frequency.
- Track author concentration and knowledge bus-factor.

### 5. Index Document Generation
- Produce `PROJECT_INDEX.md` (human-readable navigation and architecture guide).
- Produce `PROJECT_INDEX.json` (machine-parseable structural metadata).
- Maintain multi-tier token compression (Tier 1: <500 tokens, Tier 2: <2000 tokens, Tier 3: full API).

## Commands

```bash
# Verify test suite and coverage
python3 -m pytest -q
python3 -m pytest --cov=. --cov-report=term -q

# Run 52-scenario industrial verification
python3 verify_50_scenarios.py

# Lint check
ruff check .

# Check git drift since last index
git log -n 1 --oneline
```
