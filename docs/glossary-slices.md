# Glossary slice files (`term_*.py` / `term_*.ts`)

The repository contains many small modules under:

- `fin-backend/app/glossary_slices/term_*.py`
- `fin-front/src/lib/glossary/slices/term_*.ts`

These are **intentional content slices** (glossary / terminology data), not runtime API code. They inflate file count and are excluded from backend Ruff analysis via `extend-exclude` in `fin-backend/pyproject.toml` so CI stays fast.

If a slice is no longer needed for the product, remove it in a dedicated PR with a short note in the changelog.
