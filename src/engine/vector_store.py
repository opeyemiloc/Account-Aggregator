import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer, util
from typing import List, Dict, Any

class VectorMatcher:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initializes the sentence transformer model.
        'all-MiniLM-L6-v2' is a great, fast default for semantic text matching.
        """
        self.model = SentenceTransformer(model_name)
        self.corpus_embeddings = None
        self.base_names = []
        self.canonical_names = []

    def build_index(self, base_roster_df: pd.DataFrame, base_name_col: str):
        """
        Embeds the normalized base names and stores them in memory for fast similarity search.
        """
        if base_roster_df.empty:
            return

        # Extract unique normalized names and their corresponding original canonical names
        mapping = base_roster_df[['Normalized Base Name', base_name_col]].drop_duplicates()
        mapping = mapping.dropna(subset=['Normalized Base Name'])
        
        self.base_names = mapping['Normalized Base Name'].tolist()
        self.canonical_names = mapping[base_name_col].tolist()

        if not self.base_names:
            return

        # Generate corpus embeddings (PyTorch tensors)
        self.corpus_embeddings = self.model.encode(self.base_names, convert_to_tensor=True)

    def search_unmatched(self, unmatched_df: pd.DataFrame, top_k: int = 5, similarity_threshold: float = 0.5) -> pd.DataFrame:
        """
        Searches the Vector DB for the unmatched messy names. 
        Applies threshold cutoffs and identifies short acronyms to prevent wasting LLM tokens.
        """
        if unmatched_df.empty or self.corpus_embeddings is None or len(self.base_names) == 0:
            return unmatched_df.copy()

        queries = unmatched_df['Normalized Name'].tolist()
        
        # Generate embeddings for the queries
        query_embeddings = self.model.encode(queries, convert_to_tensor=True)

        # Perform the semantic search using sentence-transformers built-in utility
        # Returns a list of lists containing dicts like: {'corpus_id': 123, 'score': 0.85}
        search_results = util.semantic_search(query_embeddings, self.corpus_embeddings, top_k=top_k)

        results = []
        for i, (original_idx, row) in enumerate(unmatched_df.iterrows()):
            query_name = row['Normalized Name']
            row_data = row.to_dict()
            
            # Rule 1: If it's a short 3-letter acronym that failed exact matching, route straight to manual review
            if len(str(query_name).strip()) <= 3:
                row_data['Candidates'] = []
                row_data['Status'] = 'Manual Review (Acronym)'
                results.append(row_data)
                continue

            candidates = []
            # Parse the search results for this specific query
            for hit in search_results[i]:
                corpus_id = int(hit['corpus_id'])
                score = hit['score']

                # Rule 2: Apply similarity cutoff threshold. Ignore wildly incorrect vector matches.
                if score >= similarity_threshold and 0 <= corpus_id < len(self.canonical_names):
                    candidates.append({
                        'canonical_name': self.canonical_names[corpus_id],
                        'normalized_name': self.base_names[corpus_id],
                        'score': float(score)
                    })
            
            row_data['Candidates'] = candidates
            
            if not candidates:
                row_data['Status'] = 'Rejected (Low Similarity)'
            else:
                row_data['Status'] = 'Pending LLM Review'
                
            results.append(row_data)

        return pd.DataFrame(results)
