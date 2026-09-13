import streamlit as st
import pandas as pd
import io
from src.engine.normalization import aggregate_and_clean_data, normalize_base_roster
from src.engine.exact_match import perform_exact_match
from src.engine.vector_store import VectorMatcher

st.set_page_config(page_title="Account Aggregator", layout="wide")

st.title("Account Aggregator & Deduplication Engine")
st.markdown("Map different variations of company names to their canonical base parent and track Account Officer overlaps.")

# --- SIDEBAR: FILE UPLOADS & MAPPING ---
st.sidebar.header("1. Upload Data")
base_file = st.sidebar.file_uploader("Upload Base Roster (Canonical Names)", type=['xlsx', 'xls'])
messy_file = st.sidebar.file_uploader("Upload Messy Database (With Officers)", type=['xlsx', 'xls'])

# Initialize session state for processed results
if 'processed' not in st.session_state:
    st.session_state.processed = False

def get_sheet_and_cols(uploaded_file, key_prefix):
    xls = pd.ExcelFile(uploaded_file)
    sheet_name = st.sidebar.selectbox(f"Select Sheet for {uploaded_file.name}", xls.sheet_names, key=f"{key_prefix}_sheet")
    df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
    return df, df.columns.tolist()

if base_file and messy_file:
    st.sidebar.header("2. Data Mapping")
    
    st.sidebar.subheader("Base Roster Mapping")
    base_raw_df, base_cols = get_sheet_and_cols(base_file, "base")
    base_name_col = st.sidebar.selectbox("Select Canonical Name Column", base_cols, key="base_col")
    
    st.sidebar.subheader("Messy DB Mapping")
    messy_raw_df, messy_cols = get_sheet_and_cols(messy_file, "messy")
    messy_name_col = st.sidebar.selectbox("Select Messy Name Column", messy_cols, key="messy_name_col")
    officer_col = st.sidebar.selectbox("Select Account Officer Column", messy_cols, key="officer_col")
    
    # --- DATA PREVIEW SECTION ---
    if not st.session_state.processed:
        st.header("Data Preview & Inspection")
        st.markdown("Verify your column mappings before running the engine.")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Base Roster Preview")
            st.dataframe(base_raw_df.head())
        with col2:
            st.subheader("Messy DB Preview")
            st.dataframe(messy_raw_df.head())
            
        if st.button("Confirm Mapping & Run Deduplication", type="primary"):
            # Normalize expected columns for the engine
            working_messy_df = messy_raw_df[[messy_name_col, officer_col]].copy()
            working_messy_df.rename(columns={
                messy_name_col: 'Messy Consignee Name',
                officer_col: 'Account Officer'
            }, inplace=True)
            
            working_base_df = base_raw_df.copy()
            
            # Create progress indicators
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("Running Deduplication Pipeline..."):
                status_text.text("Step 1/4: Aggregating and Normalizing Messy Data...")
                cleaned_messy_df = aggregate_and_clean_data(working_messy_df)
                progress_bar.progress(25)
                
                status_text.text("Step 2/4: Normalizing Base Roster...")
                norm_base_df = normalize_base_roster(working_base_df, base_name_col)
                progress_bar.progress(50)
                
                status_text.text("Step 3/4: Performing Exact Matching & Pivoting Overlaps...")
                single_match_df, multi_match_df, unmatched_df = perform_exact_match(cleaned_messy_df, norm_base_df, base_name_col)
                progress_bar.progress(75)
                
                status_text.text("Step 4/4: Initializing Vector Store & Searching Unmatched...")
                matcher = VectorMatcher()
                matcher.build_index(norm_base_df, base_name_col)
                vector_results_df = matcher.search_unmatched(unmatched_df)
                progress_bar.progress(100)
                
                if not vector_results_df.empty:
                    pending_llm = vector_results_df[vector_results_df['Status'] == 'Pending LLM Review']
                    manual_review = vector_results_df[vector_results_df['Status'].str.contains('Manual Review|Rejected')]
                else:
                    pending_llm = pd.DataFrame()
                    manual_review = pd.DataFrame()
                    
                st.session_state.single = single_match_df
                st.session_state.multi = multi_match_df
                st.session_state.pending = pending_llm
                st.session_state.manual = manual_review
                st.session_state.processed = True
                status_text.empty()
                progress_bar.empty()

# --- TABS FOR RESULTS ---
if st.session_state.processed:
    st.divider()
    tab1, tab2, tab3 = st.tabs(["Pipeline Analytics", "Interactive Review", "Export Hub"])
    
    with tab1:
        st.subheader("Pipeline Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Single Matches", len(st.session_state.single))
        col2.metric("Multi-Parent Conflicts", len(st.session_state.multi))
        col3.metric("Pending LLM", len(st.session_state.pending))
        col4.metric("Manual Review", len(st.session_state.manual))
        
    with tab2:
        st.subheader("Multi-Parent Conflicts (Overlap Viewer)")
        if not st.session_state.multi.empty:
            st.dataframe(st.session_state.multi, use_container_width=True)
        else:
            st.info("No multi-parent conflicts found! All matches were clean 1-to-1 mappings.")
            
    with tab3:
        st.subheader("Download Results")
        st.info("Generate the final multi-sheet Excel file containing all mapped buckets.")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state.single.to_excel(writer, sheet_name="1_Single_Matches", index=False)
            st.session_state.pending.to_excel(writer, sheet_name="2_Pending_LLM", index=False)
            st.session_state.manual.to_excel(writer, sheet_name="3_Manual_Review", index=False)
            st.session_state.multi.to_excel(writer, sheet_name="4_Multi_Parent_Conflicts", index=False)
        
        st.download_button(
            label="📥 Download Excel Report",
            data=output.getvalue(),
            file_name="Deduplication_Results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
