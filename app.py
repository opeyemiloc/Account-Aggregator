import streamlit as st
import pandas as pd
import io
from src.engine.normalization import aggregate_and_clean_data, normalize_base_roster
from src.engine.exact_match import perform_exact_match
from src.engine.vector_store import VectorMatcher

st.set_page_config(page_title="Account Aggregator", layout="wide")

st.title("Account Aggregator & Deduplication Engine")
st.markdown("Map different variations of company names to their canonical base parent and track Account Officer overlaps.")

# --- INITIALIZE SESSION STATE ---
if 'base_file_bytes' not in st.session_state:
    st.session_state.base_file_bytes = None
    st.session_state.base_filename = None
if 'messy_file_bytes' not in st.session_state:
    st.session_state.messy_file_bytes = None
    st.session_state.messy_filename = None
    
if 'processed' not in st.session_state:
    st.session_state.processed = False

# Default configs
if 'sim_threshold' not in st.session_state:
    st.session_state.sim_threshold = 0.5

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
nav_options = [
    "1. Upload Data", 
    "2. Data Previews & Mapping", 
    "3. Data Configuration", 
    "4. Run & Results"
]
page = st.sidebar.radio("Go to", nav_options)

# --- PAGE 1: UPLOAD DATA ---
if page == "1. Upload Data":
    st.header("1. Upload Data")
    st.info("Upload your Excel files here. They will be saved in memory as you navigate the app.")
    
    base_file = st.file_uploader("Upload Base Roster (Canonical Names)", type=['xlsx', 'xls'])
    if base_file:
        st.session_state.base_file_bytes = base_file.getvalue()
        st.session_state.base_filename = base_file.name
        st.success(f"Loaded: {base_file.name}")
        
    messy_file = st.file_uploader("Upload Messy Database (With Officers)", type=['xlsx', 'xls'])
    if messy_file:
        st.session_state.messy_file_bytes = messy_file.getvalue()
        st.session_state.messy_filename = messy_file.name
        st.success(f"Loaded: {messy_file.name}")

# --- PAGE 2: DATA PREVIEWS & MAPPING ---
elif page == "2. Data Previews & Mapping":
    st.header("2. Data Previews & Mapping")
    
    if st.session_state.base_file_bytes is None or st.session_state.messy_file_bytes is None:
        st.warning("Please upload both files in the 'Upload Data' tab first.")
    else:
        # Helper to read excel from bytes efficiently
        @st.cache_data
        def read_excel_file(file_bytes):
            return pd.ExcelFile(io.BytesIO(file_bytes))

        base_xls = read_excel_file(st.session_state.base_file_bytes)
        messy_xls = read_excel_file(st.session_state.messy_file_bytes)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Base Roster Mapping")
            base_sheet = st.selectbox(f"Select Sheet for Base Roster ({st.session_state.base_filename})", base_xls.sheet_names)
            base_df = pd.read_excel(io.BytesIO(st.session_state.base_file_bytes), sheet_name=base_sheet)
            st.session_state.base_col = st.selectbox("Select Canonical Name Column", base_df.columns.tolist())
            
            st.markdown("**Preview:**")
            st.dataframe(base_df.head(5))
            # Save to state for processing
            st.session_state.working_base_df = base_df.copy()
            
        with col2:
            st.subheader("Messy DB Mapping")
            messy_sheet = st.selectbox(f"Select Sheet for Messy DB ({st.session_state.messy_filename})", messy_xls.sheet_names)
            messy_df = pd.read_excel(io.BytesIO(st.session_state.messy_file_bytes), sheet_name=messy_sheet)
            st.session_state.messy_name_col = st.selectbox("Select Messy Name Column", messy_df.columns.tolist())
            st.session_state.officer_col = st.selectbox("Select Account Officer Column", messy_df.columns.tolist())
            
            st.markdown("**Preview:**")
            st.dataframe(messy_df.head(5))
            # Save to state for processing
            st.session_state.working_messy_df = messy_df[[st.session_state.messy_name_col, st.session_state.officer_col]].copy()
            st.session_state.working_messy_df.rename(columns={
                st.session_state.messy_name_col: 'Messy Consignee Name',
                st.session_state.officer_col: 'Account Officer'
            }, inplace=True)
            
        st.success("Mapping complete! You can now configure the vector search or proceed to Run & Results.")

# --- PAGE 3: DATA CONFIGURATION ---
elif page == "3. Data Configuration":
    st.header("3. Data Configuration")
    st.markdown("Tune the parameters of the deduplication engine.")
    
    st.subheader("Vector Similarity Search")
    st.markdown("""
    The similarity threshold determines how strict the AI matching should be for ambiguous records.
    - **Higher (e.g., 0.8)**: Very strict. Only extremely similar names will be considered a match.
    - **Lower (e.g., 0.4)**: Loose. Will try to match names even if they look quite different.
    """)
    st.session_state.sim_threshold = st.slider(
        "Similarity Threshold", 
        min_value=0.1, max_value=1.0, 
        value=st.session_state.sim_threshold, 
        step=0.05
    )
    st.success("Configuration saved!")

# --- PAGE 4: RUN & RESULTS ---
elif page == "4. Run & Results":
    st.header("4. Run & Results")
    
    if st.session_state.base_file_bytes is None or st.session_state.messy_file_bytes is None:
        st.warning("Please upload and map your files first.")
    elif 'working_base_df' not in st.session_state or 'working_messy_df' not in st.session_state:
        st.warning("Please complete the Data Previews & Mapping step first.")
    else:
        if st.button("Run Deduplication Engine", type="primary"):
            st.session_state.processed = False # Reset
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("Running Deduplication Pipeline..."):
                # 1. Normalization
                status_text.text("Step 1/4: Aggregating and Normalizing Messy Data...")
                cleaned_messy_df = aggregate_and_clean_data(st.session_state.working_messy_df)
                progress_bar.progress(25)
                
                # 2. Base Normalization
                status_text.text("Step 2/4: Normalizing Base Roster...")
                norm_base_df = normalize_base_roster(st.session_state.working_base_df, st.session_state.base_col)
                progress_bar.progress(50)
                
                # 3. Exact Match Pivot
                status_text.text("Step 3/4: Performing Exact Matching & Pivoting Overlaps...")
                single_match_df, multi_match_df, unmatched_df = perform_exact_match(cleaned_messy_df, norm_base_df, st.session_state.base_col)
                progress_bar.progress(75)
                
                # 4. Vector Search
                status_text.text(f"Step 4/4: Running Vector Search (Threshold: {st.session_state.sim_threshold})...")
                matcher = VectorMatcher()
                matcher.build_index(norm_base_df, st.session_state.base_col)
                vector_results_df = matcher.search_unmatched(unmatched_df, similarity_threshold=st.session_state.sim_threshold)
                progress_bar.progress(100)
                
                if not vector_results_df.empty:
                    pending_llm = vector_results_df[vector_results_df['Status'] == 'Pending LLM Review']
                    manual_review = vector_results_df[vector_results_df['Status'].str.contains('Manual Review|Rejected')]
                else:
                    pending_llm = pd.DataFrame()
                    manual_review = pd.DataFrame()
                    
                # Save to state
                st.session_state.single = single_match_df
                st.session_state.multi = multi_match_df
                st.session_state.pending = pending_llm
                st.session_state.manual = manual_review
                st.session_state.processed = True
                
                status_text.empty()
                progress_bar.empty()
                st.success("Pipeline Complete!")

        if st.session_state.processed:
            st.divider()
            
            # --- Export Button ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                st.session_state.single.to_excel(writer, sheet_name="1_Single_Matches", index=False)
                st.session_state.pending.to_excel(writer, sheet_name="2_Pending_LLM", index=False)
                st.session_state.manual.to_excel(writer, sheet_name="3_Manual_Review", index=False)
                st.session_state.multi.to_excel(writer, sheet_name="4_Multi_Parent_Conflicts", index=False)
            
            # Prominent Download Button above preview
            st.download_button(
                label="📥 Download Full Excel Report",
                data=output.getvalue(),
                file_name="Deduplication_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
            st.divider()
            
            # --- Analytics ---
            st.subheader("Pipeline Analytics")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Single Matches", len(st.session_state.single))
            c2.metric("Multi-Parent Conflicts", len(st.session_state.multi))
            c3.metric("Pending LLM", len(st.session_state.pending))
            c4.metric("Manual Review / Rejected", len(st.session_state.manual))
            
            # --- Interactive Preview ---
            st.subheader("Results Preview (Multi-Parent Conflicts)")
            if not st.session_state.multi.empty:
                display_df = st.session_state.multi
                if len(display_df) > 30:
                    st.info(f"⚠️ Found {len(display_df)} total conflicts. Showing the first 30 rows to preserve performance. Please download the Excel report to see all results.")
                    display_df = display_df.head(30)
                st.dataframe(display_df, use_container_width=True)
            else:
                st.info("No multi-parent conflicts found! All exact matches were clean 1-to-1 mappings.")
