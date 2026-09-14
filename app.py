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
                label="π“¥ Download Full Excel Report",
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

 #   - - -   P A G E   5 :   B A S E   R O S T E R   D I A G N O S T I C S   - - - 
 e l i f   p a g e   = =   " 5 .   B a s e   R o s t e r   D i a g n o s t i c s " : 
         s t . h e a d e r ( " 5 .   B a s e   R o s t e r   D i a g n o s t i c s " ) 
         s t . m a r k d o w n ( " C l e a n   y o u r   B a s e   D a t a b a s e !   T h i s   t o o l   s e a r c h e s   y o u r   B a s e   C a n o n i c a l   N a m e s   a g a i n s t   t h e m s e l v e s   t o   f i n d   h i g h l y   s i m i l a r   d u p l i c a t e s . " ) 
         
         i f   s t . s e s s i o n _ s t a t e . b a s e _ f i l e _ b y t e s   i s   N o n e : 
                 s t . w a r n i n g ( " P l e a s e   u p l o a d   y o u r   B a s e   R o s t e r   i n   t h e   U p l o a d   D a t a   t a b   f i r s t . " ) 
         e l i f   " w o r k i n g _ b a s e _ d f "   n o t   i n   s t . s e s s i o n _ s t a t e : 
                 s t . w a r n i n g ( " P l e a s e   c o m p l e t e   t h e   D a t a   P r e v i e w s   &   M a p p i n g   s t e p   s o   w e   k n o w   w h i c h   c o l u m n   c o n t a i n s   y o u r   c a n o n i c a l   n a m e s . " ) 
         e l s e : 
                 s t . i n f o ( f " T a r g e t   C o l u m n :   { s t . s e s s i o n _ s t a t e . b a s e _ c o l } " ) 
                 
                 s i m _ t h r e s h o l d   =   s t . s l i d e r ( " S i m i l a r i t y   T h r e s h o l d   f o r   D u p l i c a t e s " ,   0 . 5 ,   1 . 0 ,   0 . 8 5 ,   0 . 0 5 ) 
                 
                 i f   s t . b u t t o n ( " R u n   B a s e   S e l f - D i a g n o s t i c " ,   t y p e = " p r i m a r y " ) : 
                         w i t h   s t . s p i n n e r ( " N o r m a l i z i n g   b a s e   r o s t e r   a n d   b u i l d i n g   v e c t o r   i n d e x . . . " ) : 
                                 n o r m _ b a s e _ d f   =   n o r m a l i z e _ b a s e _ r o s t e r ( s t . s e s s i o n _ s t a t e . w o r k i n g _ b a s e _ d f ,   s t . s e s s i o n _ s t a t e . b a s e _ c o l ) 
                                 m a t c h e r   =   V e c t o r M a t c h e r ( ) 
                                 m a t c h e r . b u i l d _ i n d e x ( n o r m _ b a s e _ d f ,   s t . s e s s i o n _ s t a t e . b a s e _ c o l ) 
                                 
                         w i t h   s t . s p i n n e r ( " S e a r c h i n g   f o r   i n t e r n a l   d u p l i c a t e s . . . " ) : 
                                 d u p l i c a t e s _ d f   =   m a t c h e r . f i n d _ b a s e _ d u p l i c a t e s ( s i m i l a r i t y _ t h r e s h o l d = s i m _ t h r e s h o l d ) 
                                 
                         i f   d u p l i c a t e s _ d f . e m p t y : 
                                 s t . s u c c e s s ( " G r e a t   n e w s !   W e   f o u n d   N O   i n t e r n a l   d u p l i c a t e s   i n   y o u r   b a s e   d a t a b a s e   a t   t h i s   t h r e s h o l d . " ) 
                         e l s e : 
                                 s t . w a r n i n g ( f " F o u n d   { l e n ( d u p l i c a t e s _ d f ) }   p o t e n t i a l   i n t e r n a l   d u p l i c a t e   p a i r s ! " ) 
                                 s t . d a t a f r a m e ( d u p l i c a t e s _ d f ,   u s e _ c o n t a i n e r _ w i d t h = T r u e ) 
                                 
                                 o u t p u t   =   i o . B y t e s I O ( ) 
                                 w i t h   p d . E x c e l W r i t e r ( o u t p u t ,   e n g i n e = " o p e n p y x l " )   a s   w r i t e r : 
                                         d u p l i c a t e s _ d f . t o _ e x c e l ( w r i t e r ,   s h e e t _ n a m e = " B a s e _ D u p l i c a t e s " ,   i n d e x = F a l s e ) 
                                 s t . d o w n l o a d _ b u t t o n ( 
                                         l a b e l = " =Ψεά  D o w n l o a d   B a s e   D u p l i c a t e s   R e p o r t " , 
                                         d a t a = o u t p u t . g e t v a l u e ( ) , 
                                         f i l e _ n a m e = " B a s e _ D a t a b a s e _ D u p l i c a t e s . x l s x " , 
                                         m i m e = " a p p l i c a t i o n / v n d . o p e n x m l f o r m a t s - o f f i c e d o c u m e n t . s p r e a d s h e e t m l . s h e e t " , 
                                         t y p e = " p r i m a r y " 
                                 ) 
  
 