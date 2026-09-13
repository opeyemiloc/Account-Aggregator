# Utilities (`src/utils/`)

This directory contains helper scripts that support the core engine.

## Modules

### `text_cleaner.py`
Provides the `normalize_company_name` function, which is critical for standardizing text before matching.
* Converts text to uppercase.
* Removes punctuation and special characters.
* Completely removes conjunctions (`AND`, `&`) to normalize variations like "A&B", "A AND B", and "A B" into a single standard string.
* Strips common legal suffixes (e.g., `LTD`, `PLC`, `GLOBAL`, `INC`) using Regex word boundaries to avoid accidentally modifying parts of actual names.
