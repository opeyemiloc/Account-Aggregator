import re

with open('app.py', 'rb') as f:
    raw = f.read()

# Find the end of the valid UTF-8 part (before the corrupted PowerShell append)
# The corrupted part starts around the word "PAGE 5"
try:
    # We look for the last valid part. The original file ended after the download_button
    # Let's just decode ignoring errors, then truncate at the weird characters.
    text = raw.decode('utf-8', errors='ignore')
    
    # The corrupted append started exactly at: \n# --- PAGE 5: BASE ROSTER DIAGNOSTICS ---
    # In UTF-16LE, this looks like \x00 characters everywhere.
    # Let's find the string "Deduplication_Results.xlsx" which was the last valid thing.
    
    valid_text = ""
    for line in text.split('\n'):
        if "BASE ROSTER DIAGNOSTICS" in line or "\x00" in line:
            break
        valid_text += line + "\n"
        
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(valid_text.strip() + "\n")
        
    print("Fixed!")
except Exception as e:
    print(f"Error: {e}")
