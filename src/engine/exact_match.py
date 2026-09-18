import pandas as pd

def perform_exact_match(messy_df: pd.DataFrame, base_roster_df: pd.DataFrame, base_name_col: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Performs the progressive 5-pass deterministic funnel exhaustively.
    Collects all matching base canonicals for each messy record, preventing premature drops.
    Pivots multiple messy variations into MATCH 1, MATCH 2 columns.
    
    Returns:
        tuple: (single_match_df, multi_match_df, unmatched_df)
    """
    if messy_df.empty or base_roster_df.empty:
        return pd.DataFrame(), pd.DataFrame(), messy_df.copy()

    # Build fast lookup dictionaries
    clean_to_base = {}
    core_to_base = {}
    fingerprint_to_base = {}
    
    for _, row in base_roster_df.iterrows():
        base_canon = row[base_name_col]
        clean_to_base.setdefault(row['Clean Base'], set()).add(base_canon)
        core_to_base.setdefault(row['Core Base'], set()).add(base_canon)
        fingerprint_to_base.setdefault(row['Fingerprint Base'], set()).add(base_canon)
        
    unique_base_cores = list(core_to_base.keys())

    messy_df = messy_df.copy()
    messy_df['Messy_With_Officer'] = messy_df.apply(
        lambda row: f"{row['Messy Consignee Name']} ({row['Account Officers']})", axis=1
    )
    
    resolved_records = []
    unmatched_records = []

    for _, row in messy_df.iterrows():
        clean_m = row['Clean Messy']
        core_m = row['Core Messy']
        fp_m = row['Fingerprint Messy']
        
        matched_bases = set()
        
        # --- PASS 1: Direct Normalized Equality ---
        if clean_m in clean_to_base:
            matched_bases.update(clean_to_base[clean_m])

        # --- PASS 2: Core Brand Match ---
        if core_m in core_to_base:
            matched_bases.update(core_to_base[core_m])

        # --- PASS 3: Whitespace Fingerprint Match ---
        if fp_m in fingerprint_to_base:
            matched_bases.update(fingerprint_to_base[fp_m])

        # --- PASS 4: Token-Set Containment ---
        m_tokens = set(core_m.split())
        if len(m_tokens) >= 2:
            for b_core in unique_base_cores:
                b_tokens = set(b_core.split())
                if len(b_tokens) >= 2:
                    if m_tokens.issubset(b_tokens) or b_tokens.issubset(m_tokens):
                        matched_bases.update(core_to_base[b_core])

        # --- PASS 5: Prefix Truncation ---
        m_tokens_list = core_m.split()
        if len(m_tokens_list) > 0:
            for b_core in unique_base_cores:
                b_tokens_list = b_core.split()
                if len(m_tokens_list) == len(b_tokens_list):
                    is_match = True
                    for mt, bt in zip(m_tokens_list, b_tokens_list):
                        if mt == bt:
                            continue
                        if len(mt) > 7 and bt.startswith(mt):
                            continue
                        if len(bt) > 7 and mt.startswith(bt):
                            continue
                        is_match = False
                        break
                    
                    if is_match:
                        matched_bases.update(core_to_base[b_core])
                
        # --- Route the Record ---
        if matched_bases:
            for base in matched_bases:
                row_dict = row.to_dict()
                row_dict['Resolved Canonical'] = base
                resolved_records.append(row_dict)
        else:
            unmatched_records.append(row.to_dict())

    unmatched_df = pd.DataFrame(unmatched_records)
    
    if not resolved_records:
        return pd.DataFrame(), pd.DataFrame(), unmatched_df
        
    resolved_df = pd.DataFrame(resolved_records)
    
    # --- Pivot and Grouping ---
    # Determine which messy roots mapped to >1 distinct canonical base
    counts = resolved_df.groupby('Core Messy')['Resolved Canonical'].nunique()
    multi_parent_cores = counts[counts > 1].index

    # Group all officers/variations for a given messy root
    pivot_data = resolved_df.groupby('Core Messy')['Messy_With_Officer'].apply(lambda x: list(set(x))).reset_index()
    
    # Rejoin with the canonical bases so each base gets a row with the full horizontal pivot
    pivot_merged = pd.merge(
        pivot_data, 
        resolved_df[['Core Messy', 'Resolved Canonical']].drop_duplicates(), 
        on='Core Messy', 
        how='inner'
    )
    
    # Expand list into MATCH 1, MATCH 2 columns
    max_len = pivot_merged['Messy_With_Officer'].apply(len).max()
    match_cols = [f'MATCH {i+1}' for i in range(max_len)]
    
    expanded_matches = pd.DataFrame(pivot_merged['Messy_With_Officer'].tolist(), columns=match_cols)
    
    final_matched = pd.concat([
        pivot_merged[['Resolved Canonical', 'Core Messy']],
        expanded_matches
    ], axis=1)
    
    final_matched.rename(columns={
        'Resolved Canonical': 'ORIGINAL NAME',
        'Core Messy': 'BASE NAME'
    }, inplace=True)
    
    # Split into Single Matches and Multi-Parent Conflicts
    single_match_df = final_matched[~final_matched['BASE NAME'].isin(multi_parent_cores)].copy()
    multi_match_df = final_matched[final_matched['BASE NAME'].isin(multi_parent_cores)].copy()
    
    # For multi_match_df, add a Failure Reason to clarify why it's here
    if not multi_match_df.empty:
        multi_match_df['Failure Reason'] = "Mapped to multiple bases via Relational Funnel"
    
    return single_match_df, multi_match_df, unmatched_df
