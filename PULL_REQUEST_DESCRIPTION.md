# Multi-Category Routing Detection

## Summary

This PR implements a comprehensive multi-category routing system that enables the application to route user questions to multiple intent categories simultaneously, retrieve evidence per category, and synthesize unified answers. The implementation follows a phased approach with all features being **configurable, optional, and backward compatible**.

## Key Changes

### Core Features

#### 1. Multi-Category Routing Infrastructure
- **New routing taxonomy**: Introduced [`RoutingCategory`](backend/app/routing_category.py:23) enum with 8 distinct routing categories (e.g., "Hands-on engineering", "AI and ML practice", "Education and formal background")
- **New content taxonomy**: Introduced [`CardCategory`](backend/app/card_category.py:23) enum for knowledge card classification (project, research, certification, experience, profile, education)
- **Routing function**: [`route_categories()`](backend/app/llm.py:115) determines which categories a question belongs to with confidence levels and budgets

#### 2. Per-Category Retrieval
- **Category-scoped retrieval**: [`retrieve_for_category()`](backend/app/retrieval.py:304) retrieves evidence constrained to a specific routing category
- **Merge with provenance**: [`merge_dedup_preserve_provenance()`](backend/app/retrieval.py:571) combines results from multiple categories while tracking origin
- **Pinned-aware capping**: [`cap_chunks_with_coverage()`](backend/app/retrieval.py:627) respects pinned chunks during evidence capping

#### 3. Configurable Mechanisms (Phase 1-4)
- **Pinning rules** (`MULTI_CATEGORY_PINNING_RULES`): Force-include specific cards when certain categories are routed
- **Section weighting** (`MULTI_CATEGORY_SECTION_WEIGHTS`): Boost specific sections per category (capped at 0.25 bonus)
- **Quality rules** (`MULTI_CATEGORY_QUALITY_RULES`): Validate answers contain expected tokens per category (log-only in v1)

#### 4. Observability & Diagnostics
- **Database migration**: Added JSONB columns (`routing`, `retrieval_by_category`, `quality_gate`) to `interaction_logs` table
- **Structured logging**: New events `chat_routing`, `chat_retrieve_category`, `chat_retrieve_merge`, `chat_synthesis_quality_gate`
- **GIN indexes**: For efficient JSONB query performance

### Files Changed

| Category | Files |
|----------|-------|
| **New Modules** | `backend/app/card_category.py`, `backend/app/routing_category.py`, `backend/app/quality.py` |
| **Core Logic** | `backend/app/main.py` (+601 lines), `backend/app/retrieval.py` (+657 lines), `backend/app/llm.py` (+302 lines), `backend/app/config.py` (+286 lines) |
| **Database** | `backend/db/migrations/2026-02-13_add_multi_category_diagnostics.sql`, `backend/db/migrations/2026-02-15_add_card_category_column.sql` |
| **Tests** | `backend/tests/test_main_unit.py` (+436 lines), `backend/tests/test_retrieval_unit.py` (+599 lines), `backend/tests/test_quality.py` (new, 194 lines) |
| **Documentation** | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, `docs/OBSERVABILITY.md` |
| **Knowledge Cards** | Updated `education-facts.md`, research cards, and asset PDFs |

### Configuration

New environment variables (all optional with safe defaults):

```env
# Master switch
MULTI_CATEGORY_RETRIEVAL_ENABLED=false

# JSON configs (empty by default)
MULTI_CATEGORY_PINNING_RULES={}
MULTI_CATEGORY_SECTION_WEIGHTS={}
MULTI_CATEGORY_QUALITY_RULES={}

# Retrieval tuning
RETRIEVAL_MAX_DISTANCE=0.35
RETRIEVAL_DISTANCE_DELTA=0.15
```

## Design Principles

1. **Category-agnostic**: No category-specific hardcoded logic; all rules in configuration maps
2. **Optional**: Empty defaults mean no behavior change
3. **Backward compatible**: Feature flags OFF = identical to previous behavior
4. **Incremental rollout**: Each phase shipped and verified independently

## Testing

- **Unit tests**: All new functions tested in isolation with mocked dependencies
- **Integration tests**: Full pipeline tested with real retrieval (mocked LLM)
- **Regression tests**: Verified feature flag OFF produces identical behavior to single-category

## Migration Notes

1. Run database migrations before deployment:
   ```sql
   -- Add multi-category diagnostics columns
   \i backend/db/migrations/2026-02-13_add_multi_category_diagnostics.sql
   -- Add card_category column
   \i backend/db/migrations/2026-02-15_add_card_category_column.sql
   ```

2. Feature is disabled by default; enable with `MULTI_CATEGORY_RETRIEVAL_ENABLED=true`

## Related Documentation

- [Implementation Plan](plans/multi-category-routing-remaining-implementation-plan.md)
- [Architecture Decision #7](docs/DECISIONS.md:53) - Multi-category routing design
- [Architecture Decision #8](docs/DECISIONS.md:66) - Configurable mechanisms

## Commits Summary

- `b4292f5` - First implementation
- `f8be3aa` - Cards updated
- `19945b6` - Updated assets
- `53889ed` - Removed education and experience specific tweaks
- `b38c95b` - feat(multi-category): implement general pinning mechanism (Phase 1)
- `62ff03a` - feat(multi-category): add interaction log persistence for diagnostics (Phase 2)
- `2a34134` - feat(multi-category): implement general section weighting mechanism (Phase 3)
- `7711a2d` - feat(multi-category): implement configurable quality rules validation (Phase 4)
- `06945d5` - docs: update documentation for multi-category routing implementation (Phase 5)
- `66e76ea` - chore: add multi-category routing config to docker-compose
- `1a02e15` - fix: education-facts retrieval and category filter
- `874e975` - fix: remove category filter from retrieve_for_category()
- `af3de76` - fix: normalize section weight keys for case-insensitive lookup
- `55a8596` - Fix xMBA completion status and ingestion deadlock
- `8dc4cf3` - fix: normalize category names and update references to 'education'
- `d449e0d`/`52ae21f` - Add education category; split CardCategory/RoutingCategory; rename fields
- `4935237` - Fixed synthesis
