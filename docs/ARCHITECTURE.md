# TheAssembly Architecture Documentation Index

This is the canonical reference for all architecture artifacts in TheAssembly. Each artifact is tagged with its current status:
- **✅ Current**: Accurate and up-to-date with implementation
- **🔄 Needs Update**: Exists but contains outdated or inaccurate information
- **📋 Planned**: Describes future intended state (not yet implemented)

---

## Quick Navigation

| Artifact | Purpose | Status | Link |
|----------|---------|--------|------|
| **System Overview** | High-level 2-repo architecture + deployment paths | 🔄 Needs Update | [architecture-system.mmd](architecture-system.mmd) |
| **Application Internals** | App code modules, APIs, secrets flow | ✅ Current | [architecture-app.mmd](architecture-app.mmd) |
| **Infrastructure & Deployment** | Docker, Streamlit Cloud, Kubernetes options | ✅ Current | [architecture-infra.mmd](architecture-infra.mmd) |
| **LangGraph Pipeline** | 7-node poster generation orchestration | 🔄 Needs Update | [architecture-langgraph-pipeline.mmd](#langgraph-pipeline) (NEW) |
| **Data Model** | WorkoutRecord, Movement, PhotoRecord schemas | 📋 Planned | [architecture-data-model.mmd](#data-model) (NEW) |
| **Time Logic State Machine** | 3 time windows, window transitions, edge cases | 📋 Planned | [architecture-time-logic.mmd](#time-logic) (NEW) |
| **API Integration Contracts** | GitHub, Open-Meteo, Gemini, Analytics APIs | 📋 Planned | [API_CONTRACTS.md](#api-contracts) (NEW) |
| **Security & Token Isolation** | Token flow, read/write separation, private repo | 📋 Planned | [SECURITY.md](#security) (NEW) |
| **Deployment Decision Tree** | Choose Streamlit Cloud vs Docker vs K8s | 📋 Planned | [architecture-deployment-decision.mmd](#deployment-decision) (NEW) |
| **Fallback Patterns** | Graceful degradation when APIs fail | 📋 Planned | [FALLBACK_PATTERNS.md](#fallback-patterns) (NEW) |
| **Monitoring & Alerting** | Pipeline metrics, quality thresholds, runbooks | 📋 Planned | [MONITORING_ALERTING.md](#monitoring) (NEW) |
| **LangGraph Implementation** | Current 7-node graph, schemas, retry logic | 🔄 Needs Update | [LANGGRAPH_IMPLEMENTATION_COMPLETE.md](../LANGGRAPH_IMPLEMENTATION_COMPLETE.md) |
| **LangGraph Quality Analysis** | Metrics, performance, validation accuracy | 🔄 Needs Update | [LANGGRAPH_QUALITY_ANALYSIS.md](../LANGGRAPH_QUALITY_ANALYSIS.md) |
| **Tier Roadmap** | LLM schema evolution: Tier 1–4 progression | 🔄 Needs Update | [TIER_IMPLEMENTATION_ROADMAP.md](../TIER_IMPLEMENTATION_ROADMAP.md) |
| **Tier Code Examples** | Before/after for schema decomposition | 🔄 Needs Update | [TIER_CODE_EXAMPLES.md](../TIER_CODE_EXAMPLES.md) |
| **Architecture Decisions** | ADRs: 2-repo model, Streamlit, GitHub API, LangGraph | 📋 Planned | [ARCHITECTURE_DECISIONS.md](#adr) (NEW) |
| **Deployment Guide** | Streamlit Cloud, Docker, Kubernetes setup | 🔄 Needs Update | [DEPLOYMENT_GUIDE.md](#deploy-guide) (NEW - consolidates SETUP.md + SETUP_KUBERNETES.md) |
| **Known Limitations** | Design trade-offs, constraints, workarounds | 📋 Planned | [KNOWN_LIMITATIONS.md](#limitations) (NEW) |
| **Architecture Governance** | Update triggers, artifact lifecycle, breaking changes | 📋 Planned | [ARCHITECTURE_GOVERNANCE.md](#governance) (NEW) |

---

## Detailed Artifact Reference

<a id="langgraph-pipeline"></a>
### LangGraph Pipeline Architecture

**Status**: 🔄 Needs Update (Implemented but docs lag code)

**Current Reality** (from graph.py):
```
raw_wod
  ↓
[reasoning_node] ← LLM (Gemini Flash)
  Classify archetype, intensity, layout strategy
  ↓
[editor_node]
  Validate schema, canonical rows, semantic contract
  ↓
[nutrition_baseline_node] ← LLM (non-blocking)
  Daily macro guidance (independent artifact)
  ↓
[designer_node] ← LLM (Gemini Pro)
  Visual composition, compliance checklist
  ↓
[critic_node] ← LLM (optional quality gate)
  Audit fidelity, hallucination detection
  ↓ (if score ≥ threshold)
[generator_node]
  Gemini image generation API
  ↓
[validation_node]
  OCR verification, similarity scoring
  ↓ (if similarity < threshold AND retries < max)
  ↔ Loop back to [reasoning_node] with OCR feedback
  ↓ (if success or max retries reached)
final → image_path + trace JSON
```

**Files**:
- Graph compilation: [theassembly/langgraph_pipeline/graph.py](../../theassembly/langgraph_pipeline/graph.py)
- Node implementations: [theassembly/langgraph_pipeline/nodes.py](../../theassembly/langgraph_pipeline/nodes.py)
- State schema: [theassembly/langgraph_pipeline/state.py](../../theassembly/langgraph_pipeline/state.py)
- Pydantic LLM schemas: [theassembly/langgraph_pipeline/llm_schemas.py](../../theassembly/langgraph_pipeline/llm_schemas.py)

**What Needs Updating in Docs**:
1. LANGGRAPH_IMPLEMENTATION_COMPLETE.md shows architect_node (line 11-36) but actual graph uses nutrition_node
2. Retry logic documented as simple loop; should detail OCR feedback fields and structured directives
3. Critic quality gate behavior not fully documented

**What's Planned** (Phase 3):
- Add architect_node between editor and designer for layout computation
- Add structured feedback schema for retry directives (not just string feedback)
- Add trace fields for observability

---

<a id="data-model"></a>
### Data Model Architecture (NEW)

**Status**: 📋 Planned

**Scope**: Mermaid diagram showing:
- WorkoutRecord entity with movements, dates, scheduling state
- Movement entity with reps/weights/modifications
- CurrentState entity for time-window tracking
- PhotoRecord metadata (AI-generated poster metadata)

**Dependencies**: Extract from [theassembly/models.py](../../theassembly/models.py)

---

<a id="time-logic"></a>
### Time Logic State Machine (NEW)

**Status**: 📋 Planned

**Scope**: Mermaid state diagram showing:
- 3 time windows (overnight 12 AM–11 AM, closed 11 AM–4 PM, preview 4 PM–12 AM)
- Window transitions with minute-level precision
- Edge cases: DST transitions, timezone offset, boundary conditions

**Current Reference**: Text in [SETUP.md](../SETUP.md) and [schedule.py](../../theassembly/schedule.py)

---

<a id="api-contracts"></a>
### API Integration Contracts (NEW)

**Status**: 📋 Planned

**Scope**: Markdown document covering:
- **GitHub Contents API**: GET /repos/{owner}/{repo}/contents/{path}, PUT for writes, error handling
- **GitHub Workflow API**: Manual dispatch trigger for poster generation
- **Open-Meteo Forecast**: Hourly weather, no auth required
- **JokeAPI v2**: Safe-mode joke fetch
- **Hacker News Firebase**: Top stories + item detail
- **Google Analytics 4**: Measurement Protocol for event tracking
- **Microsoft Clarity**: Client-side script injection, event tracking
- **Gemini Image Generation**: IMAGE modality, aspect ratios, retry logic

**Consumer**: Links from code modules using these APIs

---

<a id="security"></a>
### Security & Token Isolation (NEW)

**Status**: 📋 Planned

**Scope**: Markdown document covering:
- Token lifecycle: GitHub PAT → Streamlit Secrets → app environment
- Read vs write token isolation
- Private repo requirements for data privacy
- Secrets management across deployment options (Streamlit Cloud, Docker, K8s)

**Current Reference**: Inline in [SETUP.md](../SETUP.md) and deployment configs

---

<a id="deployment-decision"></a>
### Deployment Decision Tree (NEW)

**Status**: 📋 Planned

**Scope**: Mermaid flowchart:
- "Choose your deployment" decision tree
- 4 paths: Streamlit Community Cloud, Docker Local, Kubernetes, Custom Server
- Pros/cons for each (cost, scaling, ops overhead, privacy)

**Consumer**: Gym owners and operations teams

---

<a id="fallback-patterns"></a>
### Fallback Patterns (NEW)

**Status**: 📋 Planned

**Scope**: Markdown document covering:
- Gemini image generation fails → fallback to Pillow poster
- LLM JSON parse fails → heuristic extraction
- GitHub API rate limit → cache fallback
- External API timeout → degraded mode behavior
- Test coverage for each fallback path

**Current Implementation**: Inline in [nodes.py](../../theassembly/langgraph_pipeline/nodes.py) and [generate_workout_image.py](../../tools/generate_workout_image.py)

---

<a id="monitoring"></a>
### Monitoring & Alerting (NEW)

**Status**: 📋 Planned

**Scope**: Markdown document covering:
- LangGraph pipeline quality metrics (JSON success %, OCR similarity, response time)
- Alert thresholds (JSON success < 50%, response time > 60s)
- Dashboard setup (Streamlit, Prometheus, or external)
- Incident response playbook (escalation, rollback procedures)

**Current Metrics**: [LANGGRAPH_QUALITY_ANALYSIS.md](../LANGGRAPH_QUALITY_ANALYSIS.md) has baseline data

---

<a id="adr"></a>
### Architecture Decision Records (NEW)

**Status**: 📋 Planned

**Scope**: Markdown with ADRs:
- ADR-001: Why 2-repo model (app + data) instead of monolith?
- ADR-002: Why Streamlit Cloud over custom server?
- ADR-003: Why GitHub API vs database?
- ADR-004: Why LangGraph for poster generation?
- ADR-005: Why Tier 1/2/3/4 schema progression?
- Template for future ADRs

**Audience**: Architecture reviewers, future maintainers

---

<a id="deploy-guide"></a>
### Deployment Guide (NEW - Consolidates SETUP.md + SETUP_KUBERNETES.md)

**Status**: 📋 Planned (Refactor)

**Scope**: 4 sections:
1. Streamlit Community Cloud (quick start, 5 minutes)
2. Docker Local (development machine, 15 minutes)
3. Kubernetes Self-Hosted (production-grade, 30 minutes + ops)
4. Custom Server (advanced, manual Streamlit server)

Each section includes:
- Prerequisites
- Step-by-step instructions
- Secrets management for that platform
- Troubleshooting

**Current Reference**: [SETUP.md](../SETUP.md) and [SETUP_KUBERNETES.md](../SETUP_KUBERNETES.md)

---

<a id="limitations"></a>
### Known Limitations & Trade-offs (NEW)

**Status**: 📋 Planned

**Scope**: Markdown covering:
- JSON-only data (no database) → scaling limits
- Single admin password (no RBAC) → operational constraint
- Streamlit Cloud dependency → availability risk
- Time window fixed to America/New_York → timezone limitation
- No real-time sync (GitHub polling) → eventual consistency
- Recommended workarounds for each

**Audience**: Gym owners, operators planning extensions

---

<a id="governance"></a>
### Architecture Governance (NEW)

**Status**: 📋 Planned

**Scope**: Markdown covering:
- **Update Triggers**: When docs/diagrams must be refreshed
  - LLM schema version changes
  - Node additions/removals in LangGraph
  - Workflow file changes
  - Output path changes
  - New API integrations
- **Review Process**: Who approves architecture changes
- **Breaking Change Policy**: Deprecation notice timeline (e.g., 3 releases)
- **Artifact Maintenance Checklist**: Monthly review cadence

**Enforced By**: [.github/GOVERNANCE.md](../../.github/GOVERNANCE.md) (NEW)

---

## Update Frequency & Policy

| Trigger | Action | Artifacts | Deadline |
|---------|--------|-----------|----------|
| **graph.py or nodes.py changed** | Update LANGGRAPH_IMPLEMENTATION_COMPLETE.md, architecture-langgraph-pipeline.mmd | Phase 3 docs | Before merge |
| **state.py schema added/removed** | Update architecture-data-model.mmd, LANGGRAPH_IMPLEMENTATION_COMPLETE.md | Phase 3 docs | Before merge |
| **New API integrated** | Add to API_CONTRACTS.md, architecture-api-integrations.mmd | Phase 3 docs | Before merge |
| **Workflow file added/changed** | Update architecture diagrams, DEPLOYMENT_GUIDE.md | Phase 3 docs | Before merge |
| **Image output path changed** | Update athlete_app.py consumer docs, system diagram | Phase 3 docs | Before merge |
| **LLM schema tier upgraded** | Update TIER_IMPLEMENTATION_ROADMAP.md, architecture diagrams | Phase 3 docs | Release cycle |
| **Monthly or quarterly** | Run consistency checks (link validation, mermaid rendering, docs-to-code mapping) | All | Monthly |

---

## How to Use This Index

1. **For understanding system architecture**: Start with [architecture-system.mmd](architecture-system.mmd), then drill into [architecture-app.mmd](architecture-app.mmd) or [architecture-infra.mmd](architecture-infra.mmd).

2. **For implementing poster generation**: Read [architecture-langgraph-pipeline.mmd](#langgraph-pipeline) (to be created) and cross-reference [theassembly/langgraph_pipeline/](../../theassembly/langgraph_pipeline/).

3. **For deploying TheAssembly**: Use [DEPLOYMENT_GUIDE.md](#deploy-guide) (to be created) to choose your path.

4. **For making architecture changes**: Follow [ARCHITECTURE_GOVERNANCE.md](#governance) update triggers and submit PRs with artifact updates.

5. **For troubleshooting**: Check [KNOWN_LIMITATIONS.md](#limitations) and [FALLBACK_PATTERNS.md](#fallback-patterns) first.

---

## Current Status Summary

- **✅ Current** (4): system diagrams, app diagrams, infra diagrams, quality analysis
- **🔄 Needs Update** (6): LangGraph docs, tier roadmap, tier examples, README, setup guides, monitoring
- **📋 Planned** (14): langgraph diagram, data model, time logic, API contracts, security, deployment tree, fallback patterns, monitoring, ADRs, deployment guide, limitations, governance, plus 2 implementation upgrades

**Next Steps** (Phase 1–3): Create canonical index, update existing docs for accuracy, then implement architect node, validator feedback, and GitHub Actions automation.

---

## Related Documents

- [README.md](../README.md) — Main entry point (link to this index)
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Developer setup
- [CHANGELOG.md](../CHANGELOG.md) — Release history
