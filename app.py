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
if 'enable_fuzzy' not in st.session_state:
    st.session_state.enable_fuzzy = False

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
nav_options = [
    "1. Upload Data", 
    "2. Data Previews & Mapping", 
    "3. Data Configuration", 
    "4. Run & Results",
    "5. Base Roster Diagnostics"
]

if 'page' not in st.session_state:
    st.session_state.page = nav_options[0]

def nav_to(page_name):
    st.session_state.page = page_name

for nav_option in nav_options:
    button_type = "primary" if st.session_state.page == nav_option else "secondary"
    st.sidebar.button(
        nav_option, 
        use_container_width=True, 
        type=button_type, 
        on_click=nav_to, 
        args=(nav_option,)
    )

page = st.session_state.page

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
        # Streamlit's cache_data cannot serialize a pd.ExcelFile object. 
        # Instead, we cache the extraction of sheet names and the loading of the actual dataframe.
        @st.cache_data
        def get_sheet_names(file_bytes):
            return pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names
            
        @st.cache_data
        def load_dataframe(file_bytes, sheet_name):
            return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)

        base_sheets = get_sheet_names(st.session_state.base_file_bytes)
        messy_sheets = get_sheet_names(st.session_state.messy_file_bytes)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Base Roster Mapping")
            base_sheet = st.selectbox(f"Select Sheet for Base Roster ({st.session_state.base_filename})", base_sheets)
            base_df = load_dataframe(st.session_state.base_file_bytes, base_sheet)
            st.session_state.base_col = st.selectbox("Select Canonical Name Column", base_df.columns.tolist())
            
            st.markdown("**Preview:**")
            st.dataframe(base_df.head(5))
            # Save to state for processing
            st.session_state.working_base_df = base_df.copy()
            
        with col2:
            st.subheader("Messy DB Mapping")
            messy_sheet = st.selectbox(f"Select Sheet for Messy DB ({st.session_state.messy_filename})", messy_sheets)
            messy_df = load_dataframe(st.session_state.messy_file_bytes, messy_sheet)
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
    
    st.markdown("---")
    st.subheader("Aggressive Fuzzy Matching")
    st.markdown("""
    If enabled, the engine will run a vector search even on records that found an exact match, 
    to see if there is another highly similar base account they might belong to.
    """)
    st.session_state.enable_fuzzy = st.checkbox("Enable Aggressive Fuzzy Matching (Option 2)", value=st.session_state.enable_fuzzy)
    
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
                
                # Fuzzy Search if enabled
                fuzzy_df = pd.DataFrame()
                if st.session_state.enable_fuzzy:
                    status_text.text("Running Aggressive Fuzzy Search on Exact Matches...")
                    single_match_df, fuzzy_df = matcher.search_fuzzy_conflicts(single_match_df, st.session_state.base_col, similarity_threshold=st.session_state.sim_threshold)
                    
                progress_bar.progress(100)
                
                if not vector_results_df.empty:
                    pending_llm = vector_results_df[vector_results_df['Status'] == 'Pending LLM Review']
                    manual_review = vector_results_df[vector_results_df['Status'].str.contains('Manual Review|Rejected')]
                else:
                    pending_llm = pd.DataFrame()
                    manual_review = pd.DataFrame()
                    
                # 5. LLM Resolution
                status_text.text("Step 5/5: Running LLM Resolution on ambiguous records...")
                if not pending_llm.empty:
                    if st.session_state.get('gemini_api_key'):
                        ai_matches, manual_fallback = resolve_with_gemini(pending_llm, st.session_state.gemini_api_key)
                        manual_review = pd.concat([manual_review, manual_fallback], ignore_index=True)
                        # If LLM processed them, the pending bucket is now empty
                        pending_llm = pd.DataFrame() 
                    else:
                        st.warning("No Gemini API Key provided. Skipping LLM resolution.")
                        ai_matches = pd.DataFrame()
                        # We do NOT merge pending_llm into manual_review so they stay in their own bucket!
                else:
                    ai_matches = pd.DataFrame()
                    
                progress_bar.progress(100)
                
                # Save to state
                st.session_state.single = single_match_df
                st.session_state.multi = multi_match_df
                st.session_state.pending = pending_llm
                st.session_state.ai_matches = ai_matches
                st.session_state.manual = manual_review
                st.session_state.fuzzy_df = fuzzy_df
                st.session_state.processed = True
                
                status_text.empty()
                progress_bar.empty()
                st.success("Pipeline Complete!")

        if st.session_state.processed:
            st.divider()
            
            # --- Export Button ---
    st.session_state.page = page_name

for nav_option in nav_options:
    button_type = "primary" if st.session_state.page == nav_option else "secondary"
    st.sidebar.button(
        nav_option, 
        use_container_width=True, 
        type=button_type, 
        on_click=nav_to, 
        args=(nav_option,)
    )

page = st.session_state.page

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
        # Streamlit's cache_data cannot serialize a pd.ExcelFile object. 
        # Instead, we cache the extraction of sheet names and the loading of the actual dataframe.
        @st.cache_data
        def get_sheet_names(file_bytes):
            return pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names
            
        @st.cache_data
        def load_dataframe(file_bytes, sheet_name):
            return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)

        base_sheets = get_sheet_names(st.session_state.base_file_bytes)
        messy_sheets = get_sheet_names(st.session_state.messy_file_bytes)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Base Roster Mapping")
            base_sheet = st.selectbox(f"Select Sheet for Base Roster ({st.session_state.base_filename})", base_sheets)
            base_df = load_dataframe(st.session_state.base_file_bytes, base_sheet)
            st.session_state.base_col = st.selectbox("Select Canonical Name Column", base_df.columns.tolist())
            
            st.markdown("**Preview:**")
            st.dataframe(base_df.head(5))
            # Save to state for processing
            st.session_state.working_base_df = base_df.copy()
            
        with col2:
            st.subheader("Messy DB Mapping")
            messy_sheet = st.selectbox(f"Select Sheet for Messy DB ({st.session_state.messy_filename})", messy_sheets)
            messy_df = load_dataframe(st.session_state.messy_file_bytes, messy_sheet)
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
    
    st.markdown("---")
    st.subheader("Aggressive Fuzzy Matching")
    st.markdown("""
    If enabled, the engine will run a vector search even on records that found an exact match, 
    to see if there is another highly similar base account they might belong to.
    """)
    st.session_state.enable_fuzzy = st.checkbox("Enable Aggressive Fuzzy Matching (Option 2)", value=st.session_state.enable_fuzzy)
    
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
                
                # Fuzzy Search if enabled
                fuzzy_df = pd.DataFrame()
                if st.session_state.enable_fuzzy:
                    status_text.text("Running Aggressive Fuzzy Search on Exact Matches...")
                    single_match_df, fuzzy_df = matcher.search_fuzzy_conflicts(single_match_df, st.session_state.base_col, similarity_threshold=st.session_state.sim_threshold)
                    
                progress_bar.progress(100)
                
                if not vector_results_df.empty:
                    pending_llm = vector_results_df[vector_results_df['Status'] == 'Pending LLM Review']
                    manual_review = vector_results_df[vector_results_df['Status'].str.contains('Manual Review|Rejected')]
                else:
                    pending_llm = pd.DataFrame()
                    manual_review = pd.DataFrame()
                    
                # 5. LLM Resolution
                status_text.text("Step 5/5: Running LLM Resolution on ambiguous records...")
                if not pending_llm.empty:
                    if st.session_state.get('gemini_api_key'):
                        ai_matches, manual_fallback = resolve_with_gemini(pending_llm, st.session_state.gemini_api_key)
                        manual_review = pd.concat([manual_review, manual_fallback], ignore_index=True)
                        # If LLM processed them, the pending bucket is now empty
                        pending_llm = pd.DataFrame() 
                    else:
                        st.warning("No Gemini API Key provided. Skipping LLM resolution.")
                        ai_matches = pd.DataFrame()
                        # We do NOT merge pending_llm into manual_review so they stay in their own bucket!
                else:
                    ai_matches = pd.DataFrame()
                    
                progress_bar.progress(100)
                
                # Save to state
                st.session_state.single = single_match_df
                st.session_state.multi = multi_match_df
                st.session_state.pending = pending_llm
                st.session_state.ai_matches = ai_matches
                st.session_state.manual = manual_review
                st.session_state.fuzzy_df = fuzzy_df
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
                st.session_state.ai_matches.to_excel(writer, sheet_name="3_AI_Matches", index=False)
                st.session_state.manual.to_excel(writer, sheet_name="4_Manual_Review", index=False)
                st.session_state.multi.to_excel(writer, sheet_name="5_Multi_Parent_Conflicts", index=False)
                if not st.session_state.fuzzy_df.empty:
                    st.session_state.fuzzy_df.to_excel(writer, sheet_name="6_Fuzzy_Conflicts", index=False)
            
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
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Single Matches", len(st.session_state.single))
            c2.metric("Multi-Parent Conflicts", len(st.session_state.multi))
            c3.metric("Pending LLM", len(st.session_state.pending))
            c4.metric("AI Matches", len(st.session_state.ai_matches))
            c5.metric("Manual Review / Rejected", len(st.session_state.manual))
            
            # --- Interactive Preview ---
            st.subheader("Results Preview (Pending LLM & Conflicts)")
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Pending LLM Review**")
                if not st.session_state.pending.empty:
                    st.dataframe(st.session_state.pending.head(30), use_container_width=True)
                else:
                    st.info("No ambiguous records pending review.")
            with colB:
                st.markdown("**Multi-Parent Conflicts**")
                if not st.session_state.multi.empty:
                    st.dataframe(st.session_state.multi.head(30), use_container_width=True)
                else:
                    st.info("No multi-parent conflicts found.")

# --- PAGE 5: BASE ROSTER DIAGNOSTICS ---
elif page == "5. Base Roster Diagnostics":
    st.header("5. Base Roster Diagnostics")
    st.markdown("Clean your Base Database! This tool searches your Base Canonical Names against themselves to find highly similar duplicates.")
    
    if st.session_state.base_file_bytes is None:
        st.warning("Please upload your Base Roster in the Upload Data tab first.")
    elif "working_base_df" not in st.session_state:
        st.warning("Please complete the Data Previews & Mapping step so we know which column contains your canonical names.")
    else:
        st.info(f"Target Column: {st.session_state.base_col}")
        
        sim_threshold = st.slider("Similarity Threshold for Duplicates", 0.5, 1.0, 0.85, 0.05)
        
        if st.button("Run Base Self-Diagnostic", type="primary"):
            with st.spinner("Normalizing base roster and building vector index..."):
                norm_base_df = normalize_base_roster(st.session_state.working_base_df, st.session_state.base_col)
                matcher = VectorMatcher()
                matcher.build_index(norm_base_df, st.session_state.base_col)
                
            with st.spinner("Searching for internal duplicates..."):
                duplicates_df = matcher.find_base_duplicates(similarity_threshold=sim_threshold)
                
            if duplicates_df.empty:
                st.success("Great news! We found NO internal duplicates in your base database at this threshold.")
            else:
                st.warning(f"Found {len(duplicates_df)} potential internal duplicate pairs!")
                st.dataframe(duplicates_df, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    duplicates_df.to_excel(writer, sheet_name="Base_Duplicates", index=False)
                st.download_button(
                    label="📥 Download Base Duplicates Report",
                    data=output.getvalue(),
                    file_name="Base_Database_Duplicates.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
