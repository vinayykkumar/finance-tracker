# Modular glossary (`glossary_slices/`)

Each `term_XXX.py` module holds one English finance label and a `describe()` helper for future i18n or OpenAPI documentation.

These modules are **not** registered on the FastAPI app until you import them from routers or services.
