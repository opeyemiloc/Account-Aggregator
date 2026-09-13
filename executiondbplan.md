# Database Cleanup & Entity Deduplication Blueprint

## 1. Project Overview

A standalone Python/Streamlit tool designed to ingest a messy historical database of Consignee names, identify variations of the same company, group them under a canonical "Base Account Name" (Parent), and aggregate the Account Officers assigned to each variation.

## 2. Input Data Requirements

- **Base Account Roster:** A clean list of canonical company names (The Parents).
- **Messy Database:** A historical export containing `[Messy Consignee Name | Account Officer]`.

## 3. Core Execution Pipeline (The Engine)

**Phase 1: Normalization & Aggregation**

- **Data Grouping:** Group the messy database by `Messy Consignee Name` to aggregate a list of all `Account Officers` who have historically handled it.
- **Text Cleaning:** Apply rigorous text normalization (removing punctuation, stripping legal suffixes like LTD/PLC, standardizing "AND" to "&") to both the Base Names and the Messy Names.

**Phase 2: Deterministic Matching (The Free Pass)**

- Perform exact string matching on the normalized names. Matches are immediately mapped to the Base Name without needing AI.

**Phase 3: Vector Search (Candidate Retrieval & Ambiguity Filter)**

- **Vector DB Creation:** Generate text embeddings for all Base Names and store them in a local Vector Database (e.g., FAISS).
- **Similarity Search:** For every unmatched Messy Name, query the Vector DB to retrieve the Top 3 to 5 most semantically similar Base Names.
- **The Threshold Cutoff (LLM Bypass):** Apply strict rules to prevent wasting LLM tokens on obvious mismatches.
  - If the vector similarity is too low (e.g., `RMJ INTEGRATED SERVICES LTD` pulling up `BMV INTEGRATED SERVICES LTD`), it is outright rejected.
  - If it's a short 3-letter acronym that failed exact matching, it is auto-routed to manual review.
  - *Result:* Only the true "gray area" ambiguous records are allowed to proceed to Phase 4.

**Phase 4: LLM Resolution (The Judge of Ambiguity)**

- *Note:* The LLM is used purely as a last-resort judge for the highly ambiguous cases that passed the Vector Search threshold.
- **Prompt Engineering:** Construct a strict prompt passing the Messy Name and the Top 5 candidate Base Names.
- **LLM Wiring:**
  - Use an LLM API (like Gemini) with a structured output schema (e.g., Pydantic JSON enforcement) so it only returns valid machine-readable data, not conversational text.
  - The LLM must output the exact matching Base Name or `null` if it determines the messy name is an entirely new, distinct company.
  - *Crucial:* The LLM acts purely as an identity resolution engine. It is completely blind to the Account Officer data to prevent bias in its matching logic.

**Phase 5: Business Logic & Segmentation**

- Map the LLM`s matched Base Name back to the original Messy Name and its list of Account Officers.
- Segment the final data into three distinct buckets for the output:
  1. **Clean Assignments:** Base Names with variations tied to exactly *one* Account Officer.
  2. **Multi-Officer Overlaps:** Base Names with variations tied to *multiple* distinct Account Officers.
  3. **Unassigned:** Base Names/Variations with no Account Officer.

## 4. Streamlit UI Execution Plan

The UI will serve as a clean, interactive control panel for the data team.

**Sidebar / Setup:**

- File uploaders for the Base Names Excel file and the Messy Database Excel file.
- Configuration sliders (e.g., LLM batch size, vector strictness).
- A "Run Deduplication" trigger button.

**Tab 1: Pipeline Analytics & Progress:**

- Live progress bars showing Normalization, Vector Search mapping, and LLM API batch processing.
- High-level metrics: *Total Rows Processed, Exact Matches, AI Matches, Total Conflicts Found.*

**Tab 2: Interactive Review Dashboard:**

- A visual filter to toggle between the three buckets (Clean, Overlaps, Unassigned).
- Expandable rows for each Base Account. Clicking an account expands to reveal a sub-table showing all the messy variations and which Account Officer claimed them.

**Tab 3: Export Hub:**

- A primary "Download Excel Report" button.
- Generates a multi-sheet `.xlsx` file formatted perfectly for management review, with the three segmentation buckets split into their own tabs.
