import hashlib
import os
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
import numpy as np

class EmbeddingClientIntegration:
    def vectorize(self):
        raise NotImplementedError
    

class OpenAIEmbeddingClient(EmbeddingClientIntegration):
    def __init__(self):
        self.client = OpenAI()

    def vectorize(self, question):
        response = self.client.embeddings.create(
            input=question,
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

    def vectorize(self, question):
        return self.model.encode([question])[0].tolist()
    

class PineconeWrapper:
    def __init__(self, output_manager=None):
        self.output_manager = output_manager
        self.api_key = os.getenv('PINECONE_API_KEY')
        if not self.api_key:
            return
        
        self.cloud = "aws"
        self.env = "us-east-1"
        self.embed_platform = "openai"  # "openai" or "hf_sentence_transformers"
        self.pinecone_client = Pinecone(api_key=self.api_key)
        self.embedding_client = self.initialize_embedding_client()
        self.index_name, self.dimension = self.determine_index_settings()
        self.ensure_index_exists()

    def initialize_embedding_client(self):
        if self.embed_platform == "openai":
            return OpenAIEmbeddingClient()
        elif self.embed_platform == "hf_sentence_transformers":
            try:
                return HFSentenceTransformersClient()
            except RuntimeError as e:
                self.output_manager.display_system_messages(e)
        else:
            raise ValueError("Unsupported embedding platform")
        
    def determine_index_settings(self):
        settings = {
            "hf_sentence_transformers": ("bambooai-qa-retrieval", 384),
            "openai": ("bambooai-qa-retrieval", 1536)
        }
        return settings.get(self.embed_platform, (None, None))

    def vectorize_question(self, question):
        return self.embedding_client.vectorize(question)

    def ensure_index_exists(self):
        if self.index_name not in self.pinecone_client.list_indexes().names():
            self.output_manager.display_system_messages(f"Creating a new vector db index. Please wait... {self.index_name}")
            self.pinecone_client.create_index(
                name=self.index_name,
                metric="cosine",
                dimension=self.dimension,
                spec=ServerlessSpec(cloud=self.cloud, region=self.env)
            )
        self.index = self.pinecone_client.Index(name=self.index_name)

    def query_index(self, question):
        # Vectorize the question
        vectorised_question = self.vectorize_question(question)
        # Query the vector db
        results = self.index.query(vector=vectorised_question, top_k=5, include_values=True)
        matches = results.get('matches', [])

        if not matches:
            self.output_manager.display_system_messages("I was unable to find a matching record in the vector db.")
            return None

        return matches
    
    def fetch_record(self, id):
        fetched_data = self.index.fetch(ids=[id])
        vector_data = fetched_data.get('vectors', {}).get(id, {})
        if not vector_data:
            self.output_manager.display_system_messages("No data found for this vector db id")
            return None
        return vector_data

    def check_similarity(self, match, similarity_threshold):
        match_id = match['id']
        similarity_score = match['score']
        #self.output_manager.display_system_messages(f"\nClosest match vector db record: {match_id}, Similarity score: {similarity_score}\n")
        
        # Check if the similarity score is above the threshold
        if similarity_score < similarity_threshold:
            #self.output_manager.display_system_messages(f"Query similarity score {match['score']} for record {match_id} is below the threshold. Will ignore this match")
            return False
        
        return True
    
    def cosine_similarity_np(self, vec1, vec2):
        dot_product = np.dot(vec1, vec2)
        norm_vec1 = np.linalg.norm(vec1)
        norm_vec2 = np.linalg.norm(vec2)
        if norm_vec1 == 0 or norm_vec2 == 0:
            # Handle the case where one or both vectors are zero-vectors.
            return 0
        cosine_sim = dot_product / (norm_vec1 * norm_vec2)
        return cosine_sim

    def retrieve_matching_record(self, question, condition, df_columns, similarity_threshold, match_df=True,):
        retrieved_matches = self.query_index(question)
        highest_similarity_score = 0.80
        closest_match = None

        if not retrieved_matches:
            return None
        for match in retrieved_matches:
            if match and self.check_similarity(match,similarity_threshold):
                match_data = self.fetch_record(match['id'])
                if not match_data:
                    continue
                metadata = match_data['metadata']
                #Vectorise the condition and metadata['query_condition'] and compute the score
                query_condition_vector = self.vectorize_question(condition)
                retrieved_query_condition_vector = self.vectorize_question(metadata['query_condition'])
                # Compute the cosine similarity score
                similarity_score = self.cosine_similarity_np(query_condition_vector, retrieved_query_condition_vector)
                if similarity_score > highest_similarity_score:
                    highest_similarity_score = similarity_score
                    closest_match = match_data

        # Check if the dataframe columns match
        if match_df and closest_match:
            if metadata['df_col'] == df_columns:
                self.output_manager.display_system_messages(f"Found a matching record. Similarity Score: {highest_similarity_score}.")
                return closest_match
            else:
                self.output_manager.display_system_messages("The dataframe columns do not match. I will not use this record.")
                return None
        else:
            return closest_match

    def add_record(self, question, condition, plan, df_columns, data_model, code, new_rank, similarity_threshold):
        new_rank = int(new_rank)

        if new_rank < 8:
            self.output_manager.display_system_messages("The new rank is below the threshold. Not adding/updating the vector db record.")
            return
        
        # Generate a unique id for the record.
        id = hashlib.sha256(question.encode()).hexdigest() # Placeholder

        # Vectorize the question
        vectorised_question = self.vectorize_question(question)

        # Fetch the record with closest match to the question
        vector_data = self.retrieve_matching_record(question, condition, df_columns, similarity_threshold)

        vector_rank = -1 # Default rank if the record does not exist  

        if vector_data:
            vector_rank = vector_data['metadata']['rank']
            id = vector_data['id']
        # If the new rank is higher, add/update the record
        if vector_rank < new_rank:
            metadata = {"query_unknown": question, "query_condition": condition, "df_col": df_columns, "data_model": data_model,"plan": plan,  "code": code, "rank": new_rank}
            vectors = [(id, vectorised_question, metadata)]
            self.index.upsert(vectors=vectors)
            self.output_manager.display_system_messages(f"Added/Updated the vector db record.")
        else:
            self.output_manager.display_system_messages(f"Existing rank {vector_rank} is higher or equal to the new rank. I am not updating the existing vector db record.")
