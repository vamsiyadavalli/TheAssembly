# Architecture Governance

This document defines how architecture documentation and diagrams are maintained in sync with code changes, ensuring the system design remains discoverable and current.

---

## Update Triggers & Required Actions

| Trigger | When | What to Update | Deadline | Approval |
|---------|------|---|----------|----------|
| **Node added/removed in graph.py** | New LLM agent or removal | - LANGGRAPH_IMPLEMENTATION_COMPLETE.md<br>- architecture-langgraph-pipeline.mmd<br>- node_order in graph.py trace builder | Before merge | Code review |
| **Node implementation changed** | Major logic refactor in nodes.py | - Per-node docs<br>- architecture-langgraph-pipeline.mmd<br>- LANGGRAPH_QUALITY_ANALYSIS.md (if latency changes) | Before merge | Code review |
| **State schema field added/removed** | New state tracking or removal | - PosterState TypedDict<br>- architecture-data-model.mmd (future)<br>- LANGGRAPH_IMPLEMENTATION_COMPLETE.md | Before merge | Code review |
| **State field renamed** | Backward compatibility risk | - All references in nodes.py<br>- trace building code<br>- LANGGRAPH_IMPLEMENTATION_COMPLETE.md | Before merge | Code review |
| **API contract changed** | New external API or version bump | - API_CONTRACTS.md (future)<br>- architecture-app.mmd<br>- LANGGRAPH_IMPLEMENTATION_COMPLETE.md | Before merge | Code review |
| **Workflow file added/changed** | New CI/CD automation | - .github/GOVERNANCE.md (future)<br>- DEPLOYMENT_GUIDE.md (future)<br>- architecture diagrams (if operational impact) | Before merge | Code review |
| **Output path changed** | Image location or naming | - docs/ARCHITECTURE.md<br>- README.md or DEPLOYMENT_GUIDE.md (if user-visible)<br>- athlete_app.py fetch paths (verify sync) | Before merge | Code review |
| **Environment variable added** | New LLM model, temperature, or feature flag | - LANGGRAPH_IMPLEMENTATION_COMPLETE.md (Configuration section)<br>- DEPLOYMENT_GUIDE.md | Before merge | Code review |
| **Tier (schema version) upgraded** | Major LLM schema or approach change | - TIER_IMPLEMENTATION_ROADMAP.md (mark as current)<br>- LANGGRAPH_IMPLEMENTATION_COMPLETE.md<br>- architecture-langgraph-pipeline.mmd | Before release | Release owner |
| **New deployment option added** | Serverless, additional K8s variant, etc. | - architecture-deployment-decision.mmd (future)<br>- DEPLOYMENT_GUIDE.md<br>- architecture-infra.mmd | Before release | Release owner |
| **Breaking change** | API signature, state contract, data format | - CHANGELOG.md<br>- docs/KNOWN_LIMITATIONS.md (if design constraint)<br>- Notify users (issue + release notes) | 3 releases prior notice | Release owner |
| **Monthly or quarterly review** | Routine maintenance | - Run link validation on all architecture docs<br>- Verify mermaid diagrams render<br>- Check docs-to-code mapping | Monthly | Maintainer |

---

## Artifact Maintenance Cadence

### Daily/Per-Commit
- Verify graph.py and nodes.py remain in sync with LANGGRAPH_IMPLEMENTATION_COMPLETE.md during review
- If state schema changes, ensure TypedDict is updated

### Per-Release
- Update CHANGELOG.md with architecture-relevant changes
- Verify TIER_IMPLEMENTATION_ROADMAP.md reflects current tier
- Run full consistency checks (see Phase 4 validation)

### Quarterly
- Audit all "Planned" items in docs/ARCHITECTURE.md; promote to "Current" or update status
- Review KNOWN_LIMITATIONS.md for relevance
- Refresh metrics in LANGGRAPH_QUALITY_ANALYSIS.md with real production data if available

---

## Documentation Standards

### Diagram Style
- **Mermaid graphs**: Used for flow, state, and architecture diagrams (editable, version-controlled)
- **Screenshots**: Used for UI/UX reference only (export from live systems, not sources of truth)
- **All diagrams**: Include title, legend if needed, and link back to description in markdown

### Code References
- **Always use file paths relative to repo root**: `theassembly/langgraph_pipeline/graph.py`
- **Node/function names**: Use backticks: `` `architect_node`, `validation_node` ``
- **Line numbers**: Include only in narrative ("line 73 in graph.py"), not as permanent references

### Status Tags
- **✅ Current**: Verified accurate as of last check date
- **🔄 Needs Update**: Known to be outdated; PR/issue filed
- **📋 Planned**: Aspirational; describes future intended state, not current
- **❌ Deprecated**: No longer used; refer to replacement

---

## Consistency Checks (Phase 4 Validation)

Run these manually or via CI:

### 1. Docs-to-Code Mapping
```bash
# Verify every node mentioned in LANGGRAPH_IMPLEMENTATION_COMPLETE.md exists in graph.py
# Verify node_order in graph.py matches mermaid diagrams
# Verify state fields in docs match PosterState TypedDict
```

### 2. Link Validation
```bash
# Check all markdown links resolve (no 404s)
# Check all file paths exist and are readable
```

### 3. Mermaid Render Validation
```bash
# Render all .mmd files to verify syntax correctness
# Check diagrams for obvious inconsistencies (e.g., broken edges)
```

### 4. State Schema Audit
```bash
# Extract all state field references from nodes.py
# Compare against PosterState TypedDict and doc references
# Flag undocumented fields or orphaned fields
```

---

## Review Checklist for PRs

When reviewing PRs that touch code, ask:

- [ ] Does graph.py have any node wiring changes? → Update LANGGRAPH_IMPLEMENTATION_COMPLETE.md + architecture-langgraph-pipeline.mmd
- [ ] Does state.py have new/removed fields? → Update architecture docs + node trace builder
- [ ] Does a node's purpose or behavior change significantly? → Update that node's docs
- [ ] Do environment variables change? → Update Configuration section in LANGGRAPH_IMPLEMENTATION_COMPLETE.md
- [ ] Does workflow or output path change? → Update DEPLOYMENT_GUIDE.md + architecture system diagram
- [ ] Is this a breaking change? → Add to CHANGELOG.md and update docs/KNOWN_LIMITATIONS.md

---

## Deprecation Policy

When removing or replacing architecture components:

1. **Release N**: Mark deprecated in docs with ✅/🔄/📋 status + link to replacement
2. **Release N+1**: Same status + warning in README
3. **Release N+2**: Remove from docs; add migration guide to CHANGELOG.md

Example: If `nutrition_node` is later merged into architect, notify 3 releases prior that it's moving.

---

## Contacts & Escalation

- **Code + Docs Consistency**: Ask in PR review; no separate approval needed
- **Architecture Questions**: See docs/ARCHITECTURE.md index; escalate complex questions to maintainers
- **Major Changes**: Discuss in issue before PR; coordinate with stakeholders

---

## Related Documents

- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — Canonical architecture index
- [LANGGRAPH_IMPLEMENTATION_COMPLETE.md](../LANGGRAPH_IMPLEMENTATION_COMPLETE.md) — Current pipeline details
- [CHANGELOG.md](../CHANGELOG.md) — Release notes
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Developer setup + contribution process
