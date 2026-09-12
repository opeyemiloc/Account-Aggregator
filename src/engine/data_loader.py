import pandas as pd
from typing import List, Optional

def extract_messy_database(file_path: str, selected_sheets: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Extracts the messy database from an Excel file and standardizes it into a two-column DataFrame.
    Supports files with a single sheet or multiple sheets (where sheet names act as Account Officers).
    
    Returns a DataFrame with columns: ["Messy Consignee Name", "Account Officer"]
    """
    # Load the Excel file to inspect its sheets
    xls = pd.ExcelFile(file_path)
    
    # Determine which sheets to process
    sheets_to_process = selected_sheets if selected_sheets else xls.sheet_names
    
    all_data = []
    
    for sheet_name in sheets_to_process:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        
        # Clean up column names to make matching easier (strip whitespace, lowercase)
        original_cols = df.columns
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Try to identify the Account Name column
        # Look for common column names representing the messy consignee name
        name_col = None
        for col in df.columns:
            if any(keyword in col for keyword in ['account name', 'consignee', 'name', 'customer']):
                name_col = col
                break
                
        # If we can't find a clear name column, assume it's the first column
        if not name_col and len(df.columns) > 0:
            name_col = df.columns[0]
            
        # Try to identify the Account Officer column
        officer_col = None
        for col in df.columns:
            if any(keyword in col for keyword in ['officer', 'handler', 'account manager']):
                officer_col = col
                break
                
        if name_col:
            # Extract just the relevant data
            extracted_df = pd.DataFrame()
            extracted_df["Messy Consignee Name"] = df[name_col]
            
            if officer_col:
                # If an officer column exists in the sheet, use it
                extracted_df["Account Officer"] = df[officer_col]
            else:
                # If no officer column exists, use the sheet tab name as the officer
                extracted_df["Account Officer"] = sheet_name
                
            all_data.append(extracted_df)
            
    # Combine all sheets into a single master dataframe
    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)
        # Drop rows where the Consignee Name is empty/NaN
        master_df = master_df.dropna(subset=["Messy Consignee Name"])
        # Ensure data types are strings
        master_df["Messy Consignee Name"] = master_df["Messy Consignee Name"].astype(str)
        master_df["Account Officer"] = master_df["Account Officer"].astype(str)
        return master_df
    else:
        # Return empty dataframe with correct structure if nothing was found
        return pd.DataFrame(columns=["Messy Consignee Name", "Account Officer"])
