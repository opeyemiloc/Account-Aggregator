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
        Embeds the Core Base names and stores them in memory for fast similarity search.
        """
        if base_roster_df.empty:
            return

        # Extract unique normalized names and their corresponding original canonical names
        mapping = base_roster_df[['Core Base', base_name_col]].drop_duplicates()
        mapping = mapping.dropna(subset=['Core Base'])
        
        self.base_names = mapping['Core Base'].tolist()
        self.canonical_names = mapping[base_name_col].tolist()

        if not self.base_names:
            return

        # Generate corpus embeddings (PyTorch tensors)
        self.corpus_embeddings = self.model.encode(self.base_names, convert_to_tensor=True)

    def search_unmatched(self, unmatched_df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
        """
        Searches the Vector DB for the unmatched messy names.
        No threshold drops, no acronym drops. Outputs to Ambiguous Review Queue structure.
        """
        if unmatched_df.empty or self.corpus_embeddings is None or len(self.base_names) == 0:
            return unmatched_df.copy()

        queries = unmatched_df['Core Messy'].tolist()
        
        # Generate embeddings for the queries
        query_embeddings = self.model.encode(queries, convert_to_tensor=True)

        search_results = util.semantic_search(query_embeddings, self.corpus_embeddings, top_k=top_k)

        results = []
        for i, (original_idx, row) in enumerate(unmatched_df.iterrows()):
            row_data = row.to_dict()
            
            top_cand = ""
            top_score = 0.0
            alts = []
            
            # Parse the search results for this specific query
            for rank, hit in enumerate(search_results[i]):
                corpus_id = int(hit['corpus_id'])
                score = float(hit['score'])
                
                if 0 <= corpus_id < len(self.canonical_names):
                    canon_name = self.canonical_names[corpus_id]
                    if rank == 0:
                        top_cand = canon_name
                        top_score = score
                    else:
                        alts.append(f"{canon_name} ({score:.2f})")
            
            row_data['Top Candidate 1'] = top_cand
            row_data['Candidate 1 Score'] = top_score
            row_data['Alternative Candidates'] = ", ".join(alts)
            row_data['Status'] = 'Pending Human Review'
            
            results.append(row_data)

        return pd.DataFrame(results)

    def search_fuzzy_conflicts(self, exact_matches_df: pd.DataFrame, base_name_col: str, similarity_threshold: float = 0.85) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Takes the Single Matches and runs them against the vector DB to find if there is a SECOND 
        highly similar canonical name, indicating a fuzzy conflict.
        Returns (clean_single_matches, fuzzy_conflicts).
        """
        if exact_matches_df.empty or self.corpus_embeddings is None:
            return exact_matches_df, pd.DataFrame()
            
        queries = exact_matches_df['Normalized Name'].tolist()
        query_embeddings = self.model.encode(queries, convert_to_tensor=True)
        search_results = util.semantic_search(query_embeddings, self.corpus_embeddings, top_k=3)
        
        clean_singles = []
        fuzzy_conflicts = []
        
        for i, (idx, row) in enumerate(exact_matches_df.iterrows()):
            row_data = row.to_dict()
            matched_canonical = row['Match 1']
            
            conflicts = []
            for hit in search_results[i]:
                corpus_id = int(hit['corpus_id'])
                score = hit['score']
                candidate_canonical = self.canonical_names[corpus_id]
                
                # If we find a HIGHLY similar canonical name that is DIFFERENT from the one it exactly matched
                if score >= similarity_threshold and candidate_canonical != matched_canonical:
                    conflicts.append({
                        'canonical_name': candidate_canonical,
                        'normalized_name': self.base_names[corpus_id],
                        'score': float(score)
                    })
            
            if conflicts:
                row_data['Status'] = 'Fuzzy Conflict'
                row_data['Exact Match'] = matched_canonical
                row_data['Fuzzy Alternatives'] = conflicts
                fuzzy_conflicts.append(row_data)
            else:
                clean_singles.append(row_data)
                
        return pd.DataFrame(clean_singles), pd.DataFrame(fuzzy_conflicts)
        
    def find_base_duplicates(self, similarity_threshold: float = 0.85) -> pd.DataFrame:
        """
        Searches the base index against itself to find highly similar internal duplicates.
        """
        if self.corpus_embeddings is None or len(self.base_names) < 2:
            return pd.DataFrame()
            
        # Search corpus against itself
        search_results = util.semantic_search(self.corpus_embeddings, self.corpus_embeddings, top_k=5)
        
        duplicates = []
        seen_pairs = set()
        
        for i, hits in enumerate(search_results):
            name_a = self.canonical_names[i]
            norm_a = self.base_names[i]
            
            for hit in hits:
                j = int(hit['corpus_id'])
                score = float(hit['score'])
                
                # Ignore exact same index or low scores
                if i == j or score < similarity_threshold:
                    continue
                    
                name_b = self.canonical_names[j]
                
                # Create a canonical pair tuple to avoid A->B and B->A duplicates
                pair = tuple(sorted([name_a, name_b]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    duplicates.append({
                        'Canonical Name A': name_a,
                        'Normalized A': norm_a,
                        'Canonical Name B': name_b,
                        'Normalized B': self.base_names[j],
                        'Similarity Score': score
                    })
                    
        # Sort by highest similarity first
        if duplicates:
            df = pd.DataFrame(duplicates)
            return df.sort_values(by='Similarity Score', ascending=False)
        return pd.DataFrame()
