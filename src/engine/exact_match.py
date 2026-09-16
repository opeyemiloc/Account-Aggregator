import pandas as pd

def perform_exact_match(messy_df: pd.DataFrame, base_roster_df: pd.DataFrame, base_name_col: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Performs the progressive 5-pass deterministic funnel.
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
    multi_parent_conflicts = []

    for _, row in messy_df.iterrows():
        clean_m = row['Clean Messy']
        core_m = row['Core Messy']
        fp_m = row['Fingerprint Messy']
        
        matched_canonical = None
        conflict = False
        failure_reason = ""
        
        # --- PASS 1: Direct Normalized Equality ---
        if clean_m in clean_to_base:
            bases = clean_to_base[clean_m]
            if len(bases) == 1:
                matched_canonical = list(bases)[0]
            else:
                conflict = True

        # --- PASS 2: Core Brand Match ---
        if not matched_canonical and not conflict:
            if core_m in core_to_base:
                bases = core_to_base[core_m]
                if len(bases) == 1:
                    matched_canonical = list(bases)[0]
                else:
                    conflict = True

        # --- PASS 3: Whitespace Fingerprint Match ---
        if not matched_canonical and not conflict:
            if fp_m in fingerprint_to_base:
                bases = fingerprint_to_base[fp_m]
                if len(bases) == 1:
                    matched_canonical = list(bases)[0]
                else:
                    conflict = True

        # --- PASS 4: Token-Set Containment ---
        if not matched_canonical and not conflict:
            m_tokens = set(core_m.split())
            if len(m_tokens) >= 2:
                containment_matches = set()
                for b_core in unique_base_cores:
                    b_tokens = set(b_core.split())
                    if len(b_tokens) >= 2:
                        if m_tokens.issubset(b_tokens) or b_tokens.issubset(m_tokens):
                            containment_matches.update(core_to_base[b_core])
                
                if len(containment_matches) == 1:
                    matched_canonical = list(containment_matches)[0]
                elif len(containment_matches) > 1:
                    conflict = True

        # --- PASS 5: Prefix Truncation ---
        if not matched_canonical and not conflict:
            m_tokens = core_m.split()
            trunc_matches = set()
            
            for b_core in unique_base_cores:
                b_tokens = b_core.split()
                if len(m_tokens) == len(b_tokens) and len(m_tokens) > 0:
                    is_match = True
                    for mt, bt in zip(m_tokens, b_tokens):
                        if mt == bt:
                            continue
                        if len(mt) > 7 and bt.startswith(mt):
                            continue
                        if len(bt) > 7 and mt.startswith(bt):
                            continue
                        is_match = False
                        break
                    
                    if is_match:
                        trunc_matches.update(core_to_base[b_core])
                        
            if len(trunc_matches) == 1:
                matched_canonical = list(trunc_matches)[0]
            elif len(trunc_matches) > 1:
                conflict = True
                
        # --- Route the Record ---
        row_dict = row.to_dict()
        if conflict:
            row_dict['Failure Reason'] = "Multi-Parent Conflict in Funnel"
            multi_parent_conflicts.append(row_dict)
        elif matched_canonical:
            row_dict['Resolved Canonical'] = matched_canonical
            resolved_records.append(row_dict)
        else:
            row_dict['Failure Reason'] = "Failed all 5 deterministic passes"
            unmatched_records.append(row_dict)

    # Convert results back to dataframes
    unmatched_df = pd.DataFrame(unmatched_records)
    # multi_parent_conflicts normally go to the end, but wait, the prompt says they go to Ambiguous Queue!
    # I will add the conflicts to unmatched_df so they go to Vector Search/Review Queue
    if multi_parent_conflicts:
        unmatched_df = pd.concat([unmatched_df, pd.DataFrame(multi_parent_conflicts)], ignore_index=True)
        
    if not resolved_records:
        return pd.DataFrame(), pd.DataFrame(), unmatched_df
        
    resolved_df = pd.DataFrame(resolved_records)
    
    # Pivot the matched records
    pivot_data = resolved_df.groupby('Resolved Canonical')['Messy_With_Officer'].apply(list).reset_index()
    
    # Expand list into MATCH 1, MATCH 2 columns
    max_len = pivot_data['Messy_With_Officer'].apply(len).max()
    match_cols = [f'MATCH {i+1}' for i in range(max_len)]
    
    expanded_matches = pd.DataFrame(pivot_data['Messy_With_Officer'].tolist(), columns=match_cols)
    
    final_matched = pd.concat([
        pivot_data[['Resolved Canonical']],
        expanded_matches
    ], axis=1)
    
    final_matched.rename(columns={'Resolved Canonical': 'Base account db'}, inplace=True)
    
    # In this new architecture, single matches are EVERYTHING that successfully survived the funnel 
    # without hitting a multi-parent conflict.
    single_match_df = final_matched
    multi_match_df = pd.DataFrame() # We routed multi-parent conflicts to the unmatched queue as requested
    
    return single_match_df, multi_match_df, unmatched_df
