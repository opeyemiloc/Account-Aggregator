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

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
nav_options = [
    "1. Upload Data", 
    "2. Data Previews & Mapping", 
    "3. Run & Results",
    "4. Base Roster Diagnostics"
]

if 'page' not in st.session_state:
    st.session_state.page = nav_options[0]
elif st.session_state.page == "3. Data Configuration" or st.session_state.page == "4. Run & Results" or st.session_state.page == "5. Base Roster Diagnostics":
    # Adjust state if they were on old removed pages
    if st.session_state.page == "4. Run & Results":
        st.session_state.page = "3. Run & Results"
    elif st.session_state.page == "5. Base Roster Diagnostics":
        st.session_state.page = "4. Base Roster Diagnostics"
    else:
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
            st.session_state.working_base_df = base_df.copy()
            
        with col2:
            st.subheader("Messy DB Mapping")
            messy_sheet = st.selectbox(f"Select Sheet for Messy DB ({st.session_state.messy_filename})", messy_sheets)
            messy_df = load_dataframe(st.session_state.messy_file_bytes, messy_sheet)
            st.session_state.messy_name_col = st.selectbox("Select Messy Name Column", messy_df.columns.tolist())
            st.session_state.officer_col = st.selectbox("Select Account Officer Column", messy_df.columns.tolist())
            
            st.markdown("**Preview:**")
            st.dataframe(messy_df.head(5))
            st.session_state.working_messy_df = messy_df[[st.session_state.messy_name_col, st.session_state.officer_col]].copy()
            st.session_state.working_messy_df.rename(columns={
                st.session_state.messy_name_col: 'Messy Consignee Name',
                st.session_state.officer_col: 'Account Officer'
            }, inplace=True)
            
        st.success("Mapping complete! You can now proceed to Run & Results.")

# --- PAGE 3: RUN & RESULTS ---
elif page == "3. Run & Results":
    st.header("3. Run & Results")
    
    if st.session_state.base_file_bytes is None or st.session_state.messy_file_bytes is None:
        st.warning("Please upload and map your files first.")
    elif 'working_base_df' not in st.session_state or 'working_messy_df' not in st.session_state:
        st.warning("Please complete the Data Previews & Mapping step first.")
    else:
        if st.button("Run Relational Funnel Engine", type="primary"):
            st.session_state.processed = False # Reset
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("Running Deduplication Pipeline..."):
                status_text.text("Step 1/3: Normalizing and Fingerprinting Data...")
                cleaned_messy_df = aggregate_and_clean_data(st.session_state.working_messy_df)
                norm_base_df = normalize_base_roster(st.session_state.working_base_df, st.session_state.base_col)
                progress_bar.progress(33)
                
                status_text.text("Step 2/3: Executing 5-Pass Deterministic Funnel...")
                single_match_df, multi_match_df, unmatched_df = perform_exact_match(cleaned_messy_df, norm_base_df, st.session_state.base_col)
                progress_bar.progress(66)
                
                status_text.text("Step 3/3: Running Semantic Vector Retrieval for Ambiguous Queue...")
                matcher = VectorMatcher()
                matcher.build_index(norm_base_df, st.session_state.base_col)
                ambiguous_queue_df = matcher.search_unmatched(unmatched_df, top_k=3)
                progress_bar.progress(100)
                
                st.session_state.single = single_match_df
                st.session_state.multi = multi_match_df
                st.session_state.ambiguous = ambiguous_queue_df
                st.session_state.processed = True
                
                status_text.empty()
                progress_bar.empty()
                st.success("Pipeline Complete!")

        if st.session_state.processed:
            st.divider()
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if not st.session_state.single.empty:
                    st.session_state.single.to_excel(writer, sheet_name="1_Single_Matches", index=False)
                if not st.session_state.ambiguous.empty:
                    st.session_state.ambiguous.to_excel(writer, sheet_name="2_Ambiguous_Review_Queue", index=False)
                if not st.session_state.multi.empty:
                    st.session_state.multi.to_excel(writer, sheet_name="3_Multi_Parent_Conflicts", index=False)
            
            st.download_button(
                label="📥 Download Full Excel Report",
                data=output.getvalue(),
                file_name="Deduplication_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
            st.divider()
            
            st.subheader("Pipeline Analytics")
            c1, c2, c3 = st.columns(3)
            c1.metric("1. Clean Single Matches", len(st.session_state.single))
            c2.metric("2. Ambiguous Review Queue", len(st.session_state.ambiguous))
            c3.metric("3. Multi-Parent Conflicts", len(st.session_state.multi))
            
            st.subheader("Results Preview")
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Ambiguous Review Queue (Failed Funnel)**")
                if not st.session_state.ambiguous.empty:
                    cols_to_show = [c for c in ['Messy Consignee Name', 'Account Officers', 'Top Candidate 1', 'Candidate 1 Score', 'Status'] if c in st.session_state.ambiguous.columns]
                    st.dataframe(st.session_state.ambiguous[cols_to_show].head(30), use_container_width=True)
                else:
                    st.info("No ambiguous records.")
            with colB:
                st.markdown("**Multi-Parent Conflicts**")
                if not st.session_state.multi.empty:
                    cols_to_show = [c for c in ['Messy Consignee Name', 'Account Officers', 'Failure Reason'] if c in st.session_state.multi.columns]
                    st.dataframe(st.session_state.multi[cols_to_show].head(30), use_container_width=True)
                else:
                    st.info("No multi-parent conflicts found.")

# --- PAGE 4: BASE ROSTER DIAGNOSTICS ---
elif page == "4. Base Roster Diagnostics":
    st.header("4. Base Roster Diagnostics")
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
