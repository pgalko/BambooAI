import os
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
import numpy as np

class EmbeddingClientIntegration:
    def vectorize(self, text_input):
        raise NotImplementedError

class OpenAIEmbeddingClient(EmbeddingClientIntegration):
    def __init__(self):
        self.client = OpenAI()

    def vectorize(self, text_input):
        response = self.client.embeddings.create(
            input=text_input,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

class HFSentenceTransformersClient(EmbeddingClientIntegration):
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            raise RuntimeError("Sentence Transformers library is not installed.")

    def vectorize(self, text_input):
        return self.model.encode([text_input])[0].tolist()

class PineconeWrapper:
    def __init__(self, output_manager=None):
        self.output_manager = output_manager
        self.api_key = os.getenv('PINECONE_API_KEY')
        if not self.api_key:
            return
        
        self.cloud = os.getenv('PINECONE_CLOUD', "aws")
        self.env = os.getenv('PINECONE_REGION', "us-east-1")
        self.embed_platform = os.getenv('EMBEDDING_PLATFORM', "openai") # "openai" or "hf_sentence_transformers"
        
        self.pinecone_client = Pinecone(api_key=self.api_key)
        self.embedding_client = self.initialize_embedding_client()
        if not self.embedding_client:
             # Stop initialization if embedding client failed
            if self.output_manager:
                self.output_manager.display_system_messages(f"Failed to initialize embedding client for platform: {self.embed_platform}. PineconeWrapper setup incomplete.")
            return

        self.index_name, self.dimension = self.determine_index_settings()
        if not self.index_name or not self.dimension:
            if self.output_manager:
                self.output_manager.display_system_messages(f"Could not determine index settings for platform: {self.embed_platform}. PineconeWrapper setup incomplete.")
            return

        self.index = None # Initialize before calling ensure_index_exists
        self.ensure_index_exists()

    def initialize_embedding_client(self):
        if self.embed_platform == "openai":
            return OpenAIEmbeddingClient()
        elif self.embed_platform == "hf_sentence_transformers":
            try:
                return HFSentenceTransformersClient()
            except RuntimeError as e:
                if self.output_manager:
                    self.output_manager.display_system_messages(str(e))
                return None
        else:
            message = f"Unsupported embedding platform: {self.embed_platform}"
            if self.output_manager:
                self.output_manager.display_system_messages(message)
            raise ValueError(message)
        
    def determine_index_settings(self):
        settings = {
            "hf_sentence_transformers": (os.getenv("HF_PINECONE_INDEX_NAME", "bambooai-qa-retrieval-hf"), 384),
            "openai": (os.getenv("OPENAI_PINECONE_INDEX_NAME", "bambooai-qa-retrieval-openai"), 1536)
        }
        return settings.get(self.embed_platform, (None, None))

    def vectorize_intent(self, intent_text):
        return self.embedding_client.vectorize(intent_text)

    def ensure_index_exists(self):
        if self.index_name not in self.pinecone_client.list_indexes().names():
            if self.output_manager:
                self.output_manager.display_system_messages(f"Creating a new vector db index. Please wait... {self.index_name}")
            self.pinecone_client.create_index(
                name=self.index_name,
                metric="cosine",
                dimension=self.dimension,
                spec=ServerlessSpec(cloud=self.cloud, region=self.env)
            )
        self.index = self.pinecone_client.Index(name=self.index_name)

    def query_index(self, intent_text, top_k=1):
        # Vectorize the intent
        vectorised_intent = self.vectorize_intent(intent_text)
        # Query the vector db
        results = self.index.query(
            vector=vectorised_intent, 
            top_k=top_k, 
            include_values=False,
            include_metadata=True
        )
        matches = results.get('matches', [])

        if not matches:
            if self.output_manager:
                self.output_manager.display_system_messages("I was unable to find a matching record in the vector db.")
            return None

        return matches
    
    def fetch_record(self, record_id):
        fetched_data = self.index.fetch(ids=[record_id])
        vector_data = fetched_data.get('vectors', {}).get(record_id, {})
        if not vector_data:
            if self.output_manager:
                self.output_manager.display_system_messages("No data found for this vector db id")
            return None
        return vector_data

    def check_similarity(self, match, similarity_threshold):
        similarity_score = match['score']
        
        if similarity_score < similarity_threshold:
            return False
        
        return True
    
    def cosine_similarity_np(self, vec1, vec2):
        dot_product = np.dot(vec1, vec2)
        norm_vec1 = np.linalg.norm(vec1)
        norm_vec2 = np.linalg.norm(vec2)
        if norm_vec1 == 0 or norm_vec2 == 0:
            return 0.0 # Return float for consistency
        cosine_sim = dot_product / (norm_vec1 * norm_vec2)
        return cosine_sim

    def retrieve_matching_record(self, intent_text, data_descr, similarity_threshold): # Added data_descr
        # 1. Get top N matches based on intent similarity (e.g., top_k=5)
        intent_matches = self.query_index(intent_text, top_k=5) 

        if not intent_matches: # No initial matches from Pinecone
            return None

        # 2. Filter these by the initial intent similarity threshold
        qualified_intent_matches = []
        for match in intent_matches:
            if self.check_similarity(match, similarity_threshold): # Checks intent score
                qualified_intent_matches.append(match)
        
        if not qualified_intent_matches:
            return None

        # 3. Re-rank the qualified_intent_matches based on data_descr similarity
        if not data_descr or len(qualified_intent_matches) == 1:
            best_intent_match = qualified_intent_matches[0] # Already the best by intent score
            return best_intent_match

        best_match_after_reranking = None
        highest_data_descr_similarity = -2.0 # Initialize to a value lower than any possible cosine similarity

        # Vectorize the incoming (new) data_descr once
        try:
            # Reusing vectorize_intent as it's a generic text vectorizer
            new_data_descr_vector = self.vectorize_intent(data_descr) 
        except Exception as e:
            return qualified_intent_matches[0] # Fallback to best intent match

        for match in qualified_intent_matches:
            stored_data_descr = match.get('metadata', {}).get('data_descr')

            if not stored_data_descr:
                # If a stored record has no data_descr, it cannot be effectively re-ranked by it.
                current_data_descr_similarity = -1.0 # Assign a low score if missing
            else:
                try:
                    stored_data_descr_vector = self.vectorize_intent(stored_data_descr)
                    current_data_descr_similarity = self.cosine_similarity_np(new_data_descr_vector, stored_data_descr_vector)
                except Exception as e:
                    current_data_descr_similarity = -1.0 # Assign low score on error

            if current_data_descr_similarity > highest_data_descr_similarity:
                highest_data_descr_similarity = current_data_descr_similarity
                best_match_after_reranking = match
        
        if best_match_after_reranking:
            # This will be the one with the highest data_descr similarity among those that passed the intent threshold.
            return best_match_after_reranking
        else:
            # As a final fallback, return the best intent match.
            return qualified_intent_matches[0]

    def add_record(self, chain_id, intent_text, plan, data_descr, data_model, code, new_rank, similarity_threshold_for_semantic_match, percentage_of_distance_to_add=0.5):
        new_rank = int(new_rank)
        MIN_USER_RANK_TO_CONSIDER = 6
        
        # increase the similarity threshold by a percentage of the remaining distance to 1.0
        remaining_distance = 1.0 - similarity_threshold_for_semantic_match
        strong_threshold = similarity_threshold_for_semantic_match + (remaining_distance * percentage_of_distance_to_add)
        
        if new_rank < MIN_USER_RANK_TO_CONSIDER:
            if self.output_manager:
                self.output_manager.display_system_messages(f"New rank {new_rank} is below threshold {MIN_USER_RANK_TO_CONSIDER}. Not adding record for chain ID {chain_id}.")
            return

        # Since chain_id is a timestamp, this ID will always be unique for new submissions.
        pinecone_record_id = str(chain_id) 
        vectorised_intent = self.vectorize_intent(intent_text)
        if vectorised_intent is None:
            if self.output_manager:
                self.output_manager.display_system_messages(f"Failed to vectorize intent for chain ID {chain_id}. Cannot add record.")
            return

        metadata_to_upsert = {
            "intent": intent_text,
            "data_descr": data_descr, 
            "data_model": data_model,
            "plan": plan,  
            "code": code, 
            "rank": new_rank
        }

        # Check if the new intent is semantically similar to ANY existing record. Using strong_threshold ensures we only consider strong matches.
        semantically_similar_existing_match = self.retrieve_matching_record(intent_text, data_descr, strong_threshold)

        if semantically_similar_existing_match:
            # A strong semantic match was found with an *existing different record*.
            existing_semantic_match_id = semantically_similar_existing_match['id'] # This ID is from a previous timestamp
            existing_semantic_match_rank = int(semantically_similar_existing_match['metadata']['rank'])

            if new_rank > existing_semantic_match_rank:
                # Add the new, better version
                self.index.upsert(vectors=[(pinecone_record_id, vectorised_intent, metadata_to_upsert)])
                # Delete the old, superseded version
                self.delete_record(existing_semantic_match_id) 
        else:
            # No strong semantic match found with any existing record.
            # This intent is considered novel. Add it as a new record with its unique timestamp ID.
            self.index.upsert(vectors=[(pinecone_record_id, vectorised_intent, metadata_to_upsert)])

    def delete_record(self, record_id):
        try:
            self.index.delete(ids=[str(record_id)])
        except Exception:
            if self.output_manager:
                self.output_manager.display_system_messages(f"Failed to delete record with ID {record_id} from Pinecone index.")