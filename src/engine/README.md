# The Engine (`src/engine/`)

This directory houses the heavy lifting of the deduplication pipeline.

## Modules

### 1. `data_loader.py`
Handles the initial ingestion of the messy historical database and base canonical rosters.

### 2. `normalization.py`
Groups the raw data by `Messy Consignee Name`, aggregates the Account Officers into unique lists, and applies text normalization to prepare strings for matching.

### 3. `exact_match.py`
Performs deterministic string matching between the normalized messy names and the normalized base names. 
* **Key Feature**: It detects when a single normalized name maps to multiple distinct canonical Base Names (a multi-parent conflict). It isolates these edge cases and pivots the messy variations horizontally into `MATCH 1`, `MATCH 2` columns.

### 4. `vector_store.py`
Handles semantic similarity matching for ambiguous records that fail exact matching.
* Uses `sentence-transformers` (e.g., `all-MiniLM-L6-v2`) to embed the canonical Base Names into a FAISS index.
* Queries unmatched messy names against the index, applying strict similarity thresholds to prevent wasting downstream LLM tokens on obvious mismatches.
