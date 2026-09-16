import re

def normalize_company_name(name: str) -> dict:
    """
    Normalizes a company name into three distinct formats for the deterministic funnel:
    1. clean_name: Punctuation handled.
    2. core_name: Corporate suffixes removed.
    3. fingerprint: Whitespace removed.
    """
    if not isinstance(name, str) or not name.strip():
        return {"clean_name": "", "core_name": "", "fingerprint": ""}
        
    # 1. Convert to uppercase
    raw_name = name.upper()
    
    # --- CLEAN NAME ---
    # Contractions rule: delete ', ", and ` so words fuse (INT'L -> INTL)
    clean_name = re.sub(r'[\'"`]', '', raw_name)
    
    # Bridges rule: replace -, /, ., &, (, ) and other non-alphanumeric with a space
    clean_name = re.sub(r'[^A-Z0-9]', ' ', clean_name)
    
    # Trim extra whitespace
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    # --- CORE NAME ---
    core_name = clean_name
    suffixes_to_remove = [
        r'\bLTD\b', r'\bLIMITED\b', 
        r'\bPLC\b', 
        r'\bINC\b', r'\bINCORPORATED\b',
        r'\bLLC\b', r'\bCORP\b', r'\bCORPORATION\b',
        r'\bNIGERIA\b', r'\bNIG\b',
        r'\bENTERPRISES\b', r'\bENTERPRISE\b', r'\bENT\b',
        r'\bCOMPANY\b', r'\bCO\b',
        r'\bMANUFACTURING\b', r'\bMFG\b',
        r'\bVENTURES\b', r'\bGLOBAL\b', r'\bINTL\b', r'\bINTERNATIONAL\b',
        r'\bAUTO\b', r'\bAUTOS\b', r'\bMULTIPURPOSE\b', r'\bINDUSTRIES\b'
    ]
    
    for suffix in suffixes_to_remove:
        core_name = re.sub(suffix, '', core_name)
        
    core_name = re.sub(r'\s+', ' ', core_name).strip()
    
    # --- FINGERPRINT ---
    fingerprint = core_name.replace(" ", "")
    
    return {
        "clean_name": clean_name,
        "core_name": core_name,
        "fingerprint": fingerprint
    }
