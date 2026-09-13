import re

def normalize_company_name(name: str) -> str:
    """
    Normalizes a company name for exact matching by standardizing formatting,
    removing punctuation, and stripping common legal suffixes.
    """
    if not isinstance(name, str) or not name.strip():
        return ""
        
    # 1. Convert to uppercase
    clean_name = name.upper()
    
    # 2. Remove " AND " and "&" entirely to normalize A&B, A AND B, and A B to just A B
    clean_name = clean_name.replace(" AND ", " ")
    clean_name = clean_name.replace("&", " ")
    
    # 3. Remove punctuation
    # Replaces everything that isn't an alphanumeric character, space, or ampersand with a space
    clean_name = re.sub(r'[^A-Z0-9\s&]', ' ', clean_name)
    
    # 4. Strip out common legal suffixes
    # We use word boundaries \b to ensure we don't strip parts of actual words 
    # (e.g., matching "LTD" but not "MELTDOWN")
    suffixes_to_remove = [
        r'\bLTD\b', r'\bLIMITED\b', 
        r'\bPLC\b', 
        r'\bINC\b', r'\bINCORPORATED\b',
        r'\bLLC\b', r'\bCORP\b', r'\bCORPORATION\b',
        r'\bNIGERIA\b', r'\bNIG\b',
        r'\bENTERPRISES\b', r'\bENT\b',
        r'\bCOMPANY\b', r'\bCO\b',
        r'\bVENTURES\b', r'\bGLOBAL\b', r'\bINTL\b', r'\bINTERNATIONAL\b'
    ]
    
    for suffix in suffixes_to_remove:
        clean_name = re.sub(suffix, '', clean_name)
        
    # 5. Trim extra whitespace (including multiple spaces created by removing words/punctuation)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name
