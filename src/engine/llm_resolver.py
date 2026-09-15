import json
import time
import pandas as pd
from tenacity import retry, wait_exponential, stop_after_attempt
from google import genai
from pydantic import BaseModel, Field

# Define schema for the LLM output
class LLMMatchDecision(BaseModel):
    matched: bool = Field(description="True if the cleaned name represents the exact same company as the master name")
    resolved_master_name: str | None = Field(description="The master name it matched to, if matched is True")
    confidence_score: int = Field(description="Integer from 0 to 100 representing confidence")
    reasoning: str = Field(description="Brief explanation of why they are or are not the same company")

@retry(wait=wait_exponential(multiplier=2, min=5, max=60), stop=stop_after_attempt(5))
def _call_gemini_with_retry(client, model_name, prompt):
    return client.models.generate_content(
        model=model_name,
        contents=prompt
    )

def resolve_with_gemini(pending_df: pd.DataFrame, api_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Takes the Pending LLM DataFrame, runs it through Gemini in batches,
    and returns (ai_matches_df, manual_fallback_df).
    """
    if pending_df.empty:
        return pd.DataFrame(), pd.DataFrame()
        
    client = genai.Client(api_key=api_key)
    model_name = 'gemini-2.5-flash'
    batch_size = 5
    
    ai_matches = []
    manual_fallback = []
    
    # Convert dataframe to list of dicts for processing
    records = pending_df.to_dict('records')
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        
        system_prompt = f"""You are a master data analyst processing a batch of ambiguous shipping names. 
For each 'Messy Name' in the batch, determine if it is the EXACT SAME COMPANY as the 'Suggested Base Name'.

RULES:
1. If the messy name contains the base name plus extra corporate words (like 'LIMITED', 'PLC', 'ENTERPRISE'), IT IS A MATCH.
2. If the core brand entity is the same, IT IS A MATCH.
3. If they are clearly different companies, return matched: false.

Output strictly valid JSON matching this exact schema for EACH input, and return the results as a JSON ARRAY of objects:
[
  {json.dumps(LLMMatchDecision.model_json_schema(), indent=4)}
]

Ensure you return EXACTLY ONE decision object for every input provided, in the exact same order they were given. Do NOT include markdown code blocks like ```json."""

        prompt_lines = [system_prompt, "\n\nBATCH INPUT:"]
        for idx, row in enumerate(batch):
            # Parse candidate list safely
            candidates_str = str(row.get('Candidates', '[]'))
            
            prompt_lines.append(f"--- Record {idx+1} ---")
            prompt_lines.append(f"Messy Name: \"{row.get('Messy Consignee Name', '')}\"")
            prompt_lines.append(f"Normalized Messy Name: \"{row.get('Normalized Name', '')}\"")
            prompt_lines.append(f"Suggested Base Name: \"{row.get('Match 1', '')}\"")
            prompt_lines.append(f"All Candidate Data: {candidates_str}\n")
            
        prompt = "\n".join(prompt_lines)
        
        try:
            response = _call_gemini_with_retry(client, model_name, prompt)
            
            output_text = (response.text or "").strip()
            if output_text.startswith("```json"):
                output_text = output_text[7:]
            if output_text.startswith("```"):
                output_text = output_text[3:]
            if output_text.endswith("```"):
                output_text = output_text[:-3]
                
            data_array = json.loads(output_text.strip())
            
            if not isinstance(data_array, list):
                data_array = [data_array]
                
            for idx, item in enumerate(data_array):
                if idx < len(batch):
                    row = batch[idx].copy()
                    matched = item.get('matched', False)
                    row['LLM Confidence'] = item.get('confidence_score', 0)
                    row['LLM Reasoning'] = item.get('reasoning', '')
                    
                    if matched:
                        row['Status'] = 'AI Resolved'
                        row['Final Master Name'] = item.get('resolved_master_name') or row['Match 1']
                        ai_matches.append(row)
                    else:
                        row['Status'] = 'Manual Review Required'
                        manual_fallback.append(row)
                        
        except Exception as e:
            # If batch fails, push to manual review
            error_msg = str(e)
            for row in batch:
                row_copy = row.copy()
                row_copy['Status'] = 'Manual Review Required (API Error)'
                row_copy['LLM Reasoning'] = f"Error: {error_msg}"
                manual_fallback.append(row_copy)
                
        if i + batch_size < len(records):
            time.sleep(2)
            
    return pd.DataFrame(ai_matches), pd.DataFrame(manual_fallback)
