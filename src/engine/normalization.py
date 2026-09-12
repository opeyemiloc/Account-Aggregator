import pandas as pd
from src.utils.text_cleaner import normalize_company_name

def aggregate_and_clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes the raw 2-column DataFrame from the data loader, aggregates the Account Officers
    by Messy Consignee Name, and applies text normalization to create a 'Normalized Name' column.
    """
    if df.empty:
        return pd.DataFrame(columns=["Messy Consignee Name", "Account Officers", "Normalized Name"])
        
    # Group by Messy Consignee Name and aggregate Account Officers into a unique, comma-separated string
    aggregated_df = df.groupby('Messy Consignee Name', as_index=False).agg(
        {'Account Officer': lambda x: ', '.join(sorted(set(str(o).strip() for o in x if pd.notna(o) and str(o).strip())))}
    )
    
    # Rename the aggregated column to reflect that it can contain multiple officers
    aggregated_df.rename(columns={'Account Officer': 'Account Officers'}, inplace=True)
    
    # Apply the text cleaner to generate the Normalized Name column for Exact Matching later
    aggregated_df['Normalized Name'] = aggregated_df['Messy Consignee Name'].apply(normalize_company_name)
    
    return aggregated_df

def normalize_base_roster(base_df: pd.DataFrame, name_col: str) -> pd.DataFrame:
    """
    Applies text normalization to the Base Roster (the clean canonical names).
    Generates a 'Normalized Base Name' column used for Exact Matching.
    """
    if base_df.empty or name_col not in base_df.columns:
        return base_df
        
    base_df = base_df.copy()
    base_df['Normalized Base Name'] = base_df[name_col].astype(str).apply(normalize_company_name)
    return base_df
