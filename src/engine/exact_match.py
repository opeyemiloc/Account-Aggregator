import pandas as pd

def perform_exact_match(messy_df: pd.DataFrame, base_roster_df: pd.DataFrame, base_name_col: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Performs an exact string match between the normalized messy names and the normalized base names.
    Pivots multiple messy variations into MATCH 1, MATCH 2 columns.
    
    Returns:
        tuple: (single_match_df, multi_match_df, unmatched_df)
    """
    if messy_df.empty or base_roster_df.empty:
        return pd.DataFrame(), pd.DataFrame(), messy_df.copy()

    if 'Normalized Base Name' not in base_roster_df.columns:
        raise ValueError("Base roster must have a 'Normalized Base Name' column.")

    mapping_df = base_roster_df[[base_name_col, 'Normalized Base Name']].drop_duplicates()

    # Create the combined Messy Name (Officer) string
    messy_df = messy_df.copy()
    messy_df['Messy_With_Officer'] = messy_df.apply(
        lambda row: f"{row['Messy Consignee Name']} ({row['Account Officers']})", axis=1
    )

    # First, find which messy records are completely unmatched to pass to Vector Search
    merged_original = pd.merge(
        messy_df, 
        mapping_df, 
        left_on='Normalized Name', 
        right_on='Normalized Base Name', 
        how='left'
    )
    
    unmatched_df = merged_original[merged_original[base_name_col].isna()].copy()
    unmatched_df.drop(columns=[base_name_col, 'Normalized Base Name', 'Messy_With_Officer'], inplace=True, errors='ignore')

    # Now handle the matches and pivot them
    matched_original = merged_original[merged_original[base_name_col].notna()].copy()
    
    if matched_original.empty:
        return pd.DataFrame(), pd.DataFrame(), unmatched_df
        
    # Group the messy records by Normalized Name to build the list of matches
    # We use the original messy_df so we don't duplicate matches if a name hit multiple bases
    pivot_data = messy_df[messy_df['Normalized Name'].isin(matched_original['Normalized Name'])].groupby('Normalized Name')['Messy_With_Officer'].apply(list).reset_index()

    # Merge with the base roster mapping
    pivot_merged = pd.merge(
        pivot_data,
        mapping_df,
        left_on='Normalized Name',
        right_on='Normalized Base Name',
        how='inner'
    )

    # Expand the list of messy matches into columns
    max_len = pivot_merged['Messy_With_Officer'].apply(len).max()
    match_cols = [f'MATCH {i+1}' for i in range(max_len)]
    
    expanded_matches = pd.DataFrame(pivot_merged['Messy_With_Officer'].tolist(), columns=match_cols)
    
    # Assemble the final pivoted dataframe
    final_matched = pd.concat([
        pivot_merged[['Normalized Name', base_name_col]], 
        expanded_matches
    ], axis=1)
    
    final_matched.rename(columns={base_name_col: 'Base account db', 'Normalized Name': 'Normalised name'}, inplace=True)
    
    # Identify multi-parent conflicts (where one normalized name matched multiple distinct base names)
    counts = final_matched['Normalised name'].value_counts()
    multiple_match_names = counts[counts > 1].index
    
    multi_match_df = final_matched[final_matched['Normalised name'].isin(multiple_match_names)].copy()
    single_match_df = final_matched[~final_matched['Normalised name'].isin(multiple_match_names)].copy()
    
    return single_match_df, multi_match_df, unmatched_df
