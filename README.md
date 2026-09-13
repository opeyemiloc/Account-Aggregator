# Account Aggregator & Deduplication Engine

A dedicated data processing pipeline and Streamlit application designed to ingest messy historical databases of Consignee names, identify and map various permutations of the same company, and group them under a canonical Base Account Name.

This tool helps organizations clean up messy historical exports, standardize naming conventions, and cleanly consolidate Account Officer assignments tied to these entity variations, providing a clear and unified view of account ownership.

## 🏗️ Architecture Flow

The pipeline executes in four distinct phases:

1. **Normalization & Aggregation**: Groups messy databases and standardizes text (removing punctuation, stripping legal suffixes).
2. **Exact Match Pivot (The Free Pass)**: Performs deterministic matching. It cleverly handles 1-to-many conflicts by grouping messy variations and pivoting them horizontally so overlapping account officers are easily identifiable.
3. **Vector Search (Candidate Retrieval)**: For records that fail exact matching, the engine builds a vector index of canonical names and performs a semantic similarity search.
4. **LLM Resolution (The Judge)**: The most ambiguous records that pass the similarity threshold are flagged for an LLM to make a final deterministic choice.

## 🚀 How to Run Locally

1. Activate your virtual environment (e.g., `.\dbvenv\Scripts\activate` on Windows).
2. Install the requirements: `pip install -r requirements.txt`
3. Run the Streamlit UI:
   ```bash
   streamlit run app.py
   ```

## 📊 Output Buckets

The engine exports a multi-sheet Excel file separating your data into actionable buckets:
* **1_Single_Matches**: Clean, 1-to-1 matches where a normalized name maps perfectly to a single canonical Base Account.
* **2_Pending_LLM**: Ambiguous matches that require LLM resolution.
* **3_Manual_Review**: Acronyms or low-confidence matches rejected by the Vector DB.
* **4_Multi_Parent_Conflicts**: Edge cases where a normalized messy name maps to *multiple* canonical base accounts. Overlaps are pivoted horizontally for easy review.

## 📁 Source Code Navigation
Explore the `src/` directory for detailed documentation on the underlying engine mechanics.
