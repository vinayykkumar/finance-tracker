# Modular glossary (`slices/`)

Each file under `slices/` exports a single finance-related English label plus a tiny `describeTerm()` helper. They exist so glossary copy can grow **one term per file** (easier reviews, future i18n keys, and tree-shaking when wired into UI).

Nothing imports these yet; wire `describeTerm()` from the relevant feature when you add tooltips or a glossary page.
