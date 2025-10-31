import os
import uuid
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from qdrant_client import QdrantClient, models
import numpy as np


class EmbeddingClientIntegration:
    def vectorize(self, text_input):
        raise NotImplementedError


class OpenAIEmbeddingClient(EmbeddingClientIntegration):
    def __init__(self):
        self.client = OpenAI()

    def vectorize(self, text_input):
        response = self.client.embeddings.create(
            input=text_input, model="text-embedding-3-small"
        )
        return response.data[0].embedding


class HFSentenceTransformersClient(EmbeddingClientIntegration):
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            raise RuntimeError("Sentence Transformers library is not installed.")

    def vectorize(self, text_input):
        return self.model.encode([text_input])[0].tolist()


class BaseVectorDBWrapper:
    """Base class for vector database wrappers with common functionality"""

    def __init__(self, output_manager=None):
        self.output_manager = output_manager
        self.embed_platform = os.getenv("EMBEDDING_PLATFORM", "openai")

        self.embedding_client = self.initialize_embedding_client()
        if not self.embedding_client:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Failed to initialize embedding client for platform: {self.embed_platform}. {self.__class__.__name__} setup incomplete."
                )
            return

        self.collection_name, self.dimension = self.determine_collection_settings()
        if not self.collection_name or not self.dimension:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Could not determine collection settings for platform: {self.embed_platform}. {self.__class__.__name__} setup incomplete."
                )
            return

        self.initialize_database()
        self.ensure_collection_exists()

    def initialize_embedding_client(self):
        """Initialize the embedding client based on platform"""
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

    def vectorize_intent(self, intent_text):
        """Vectorize text using the embedding client"""
        return self.embedding_client.vectorize(intent_text)

    def check_similarity(self, match, similarity_threshold):
        """Check if a match meets the similarity threshold"""
        similarity_score = match["score"]
        return similarity_score >= similarity_threshold

    def cosine_similarity_np(self, vec1, vec2):
        """Calculate cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm_vec1 = np.linalg.norm(vec1)
        norm_vec2 = np.linalg.norm(vec2)
        if norm_vec1 == 0 or norm_vec2 == 0:
            return 0.0
        cosine_sim = dot_product / (norm_vec1 * norm_vec2)
        return cosine_sim

    def retrieve_matching_record(self, intent_text, data_descr, similarity_threshold):
        """Retrieve the best matching record based on intent and data description similarity"""
        intent_matches = self.query_index(intent_text, top_k=5)

        if not intent_matches:
            return None

        qualified_intent_matches = []
        for match in intent_matches:
            if self.check_similarity(match, similarity_threshold):
                qualified_intent_matches.append(match)

        if not qualified_intent_matches:
            return None

        if not data_descr or len(qualified_intent_matches) == 1:
            return qualified_intent_matches[0]

        best_match_after_reranking = None
        highest_data_descr_similarity = -2.0

        try:
            new_data_descr_vector = self.vectorize_intent(data_descr)
        except Exception as e:
            return qualified_intent_matches[0]

        for match in qualified_intent_matches:
            stored_data_descr = match.get("metadata", {}).get("data_descr")

            if not stored_data_descr:
                current_data_descr_similarity = -1.0
            else:
                try:
                    stored_data_descr_vector = self.vectorize_intent(stored_data_descr)
                    current_data_descr_similarity = self.cosine_similarity_np(
                        new_data_descr_vector, stored_data_descr_vector
                    )
                except Exception as e:
                    current_data_descr_similarity = -1.0

            if current_data_descr_similarity > highest_data_descr_similarity:
                highest_data_descr_similarity = current_data_descr_similarity
                best_match_after_reranking = match

        return best_match_after_reranking or qualified_intent_matches[0]

    def add_record(
        self,
        chain_id,
        intent_text,
        plan,
        data_descr,
        data_model,
        code,
        new_rank,
        similarity_threshold_for_semantic_match,
        percentage_of_distance_to_add=0.7,
    ):
        """Add a new record to the vector database"""
        new_rank = int(new_rank)
        MIN_USER_RANK_TO_CONSIDER = 6

        remaining_distance = 1.0 - similarity_threshold_for_semantic_match
        strong_threshold = similarity_threshold_for_semantic_match + (
            remaining_distance * percentage_of_distance_to_add
        )

        if new_rank < MIN_USER_RANK_TO_CONSIDER:
            return

        record_id = str(chain_id)
        vectorised_intent = self.vectorize_intent(intent_text)
        if vectorised_intent is None:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Failed to vectorize intent for chain ID {chain_id}. Cannot add record."
                )
            return

        metadata = {
            "intent": intent_text,
            "data_descr": data_descr,
            "data_model": data_model,
            "plan": plan,
            "code": code,
            "rank": new_rank,
        }

        semantically_similar_existing_match = self.retrieve_matching_record(
            intent_text, data_descr, strong_threshold
        )

        if semantically_similar_existing_match:
            existing_semantic_match_id = semantically_similar_existing_match["id"]
            existing_semantic_match_rank = int(
                semantically_similar_existing_match["metadata"]["rank"]
            )

            if new_rank > existing_semantic_match_rank:
                self.upsert_record(record_id, vectorised_intent, metadata)
                self.delete_record(existing_semantic_match_id)
        else:
            self.upsert_record(record_id, vectorised_intent, metadata)

    def initialize_database(self):
        """Initialize database-specific client and settings"""
        raise NotImplementedError

    def determine_collection_settings(self):
        """Determine collection/index name and dimension based on embedding platform"""
        raise NotImplementedError

    def ensure_collection_exists(self):
        """Ensure the collection/index exists, create if it doesn't"""
        raise NotImplementedError

    def query_index(self, intent_text, top_k=1):
        """Query the vector database for similar records"""
        raise NotImplementedError

    def fetch_record(self, record_id):
        """Fetch a specific record by ID"""
        raise NotImplementedError

    def upsert_record(self, record_id, vector, metadata):
        """Upsert a record with vector and metadata"""
        raise NotImplementedError

    def delete_record(self, record_id):
        """Delete a record by ID"""
        raise NotImplementedError

    def search_for_results(self, query_text, top_k=10):
        """Search for results matching query text"""
        raise NotImplementedError


class PineconeWrapper(BaseVectorDBWrapper):
    """Pinecone based implementation of vector database wrapper"""

    def initialize_database(self):
        self.api_key = os.getenv("PINECONE_API_KEY")
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY environment variable not found")

        self.cloud = os.getenv("PINECONE_CLOUD", "aws")
        self.env = os.getenv("PINECONE_REGION", "us-east-1")
        self.pinecone_client = Pinecone(api_key=self.api_key)
        self.index = None

    def determine_collection_settings(self):
        settings = {
            "hf_sentence_transformers": (
                os.getenv("HF_PINECONE_INDEX_NAME", "bambooai-qa-retrieval-hf"),
                384,
            ),
            "openai": (
                os.getenv("OPENAI_PINECONE_INDEX_NAME", "bambooai-qa-retrieval-openai"),
                1536,
            ),
        }
        return settings.get(self.embed_platform, (None, None))

    def ensure_collection_exists(self):
        if self.collection_name not in self.pinecone_client.list_indexes().names():
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Creating a new vector db index. Please wait... {self.collection_name}"
                )
            self.pinecone_client.create_index(
                name=self.collection_name,
                metric="cosine",
                dimension=self.dimension,
                spec=ServerlessSpec(cloud=self.cloud, region=self.env),
            )
        self.index = self.pinecone_client.Index(name=self.collection_name)

    def query_index(self, intent_text, top_k=1):
        vectorised_intent = self.vectorize_intent(intent_text)
        results = self.index.query(
            vector=vectorised_intent,
            top_k=top_k,
            include_values=False,
            include_metadata=True,
        )
        matches = results.get("matches", [])
        return matches if matches else None

    def fetch_record(self, record_id):
        fetched_data = self.index.fetch(ids=[record_id])
        vector_data = fetched_data.get("vectors", {}).get(record_id, {})
        return vector_data if vector_data else None

    def upsert_record(self, record_id, vector, metadata):
        self.index.upsert(vectors=[(record_id, vector, metadata)])

    def delete_record(self, record_id):
        try:
            self.index.delete(ids=[str(record_id)])
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Failed to delete record with ID {record_id} from vector database: {str(e)}"
                )

    def search_for_results(self, query_text, top_k=10):
        threshold = 0.2

        if not self.index:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    "Vector database is not available for search."
                )
            return []

        try:
            vectorised_query = self.vectorize_intent(query_text)
            results = self.index.query(
                vector=vectorised_query,
                top_k=top_k,
                include_values=False,
                include_metadata=False,
            )

            matches = results.get("matches", [])
            search_results = [
                {"id": match["id"], "score": match["score"]}
                for match in matches
                if match["score"] > threshold
            ]

            return search_results
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"An error occurred during the search: {str(e)}"
                )
            return []


class QdrantWrapper(BaseVectorDBWrapper):
    """Qdrant based implementation of vector database wrapper"""

    def initialize_database(self):
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = os.getenv("QDRANT_API_KEY")

        self.qdrant_client = QdrantClient(url=url, api_key=api_key)
        self.collection = None

    def determine_collection_settings(self):
        settings = {
            "hf_sentence_transformers": (
                os.getenv("HF_QDRANT_COLLECTION_NAME", "bambooai-qa-retrieval-hf"),
                384,
            ),
            "openai": (
                os.getenv(
                    "OPENAI_QDRANT_COLLECTION_NAME", "bambooai-qa-retrieval-openai"
                ),
                1536,
            ),
        }
        return settings.get(self.embed_platform, (None, None))

    def ensure_collection_exists(self):
        try:
            if not self.qdrant_client.collection_exists(self.collection_name):
                if self.output_manager:
                    self.output_manager.display_system_messages(
                        f"Creating a new vector db collection. Please wait... {self.collection_name}"
                    )

                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimension, distance=models.Distance.COSINE
                    ),
                )

            self.collection = self.collection_name
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Error creating vector database collection: {str(e)}"
                )

    def _generate_uuid_from_id(self, original_id):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(original_id)))

    def _extract_original_id(self, payload):
        return payload.get("original_id", payload.get("id"))

    def _prepare_qdrant_metadata(self, metadata):
        if "original_id" not in metadata:
            metadata["original_id"] = metadata.get("id")
        return metadata

    def query_index(self, intent_text, top_k=1):
        vectorised_intent = self.vectorize_intent(intent_text)

        results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=vectorised_intent,
            limit=top_k,
            with_payload=True,
        ).points

        if not results:
            return None

        matches = []
        for result in results:
            original_id = self._extract_original_id(result.payload)
            matches.append(
                {
                    "id": original_id or str(result.id),
                    "score": result.score,
                    "metadata": result.payload,
                }
            )

        return matches

    def fetch_record(self, record_id):
        try:
            uuid_id = self._generate_uuid_from_id(record_id)
            result = self.qdrant_client.retrieve(
                collection_name=self.collection_name, ids=[uuid_id], with_payload=True
            )
            if result and len(result) > 0:
                original_id = self._extract_original_id(result[0].payload)
                return {
                    "id": original_id or str(result[0].id),
                    "payload": result[0].payload,
                }
            return None
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Error fetching record {record_id}: {str(e)}"
                )
            return None

    def upsert_record(self, record_id, vector, metadata):
        uuid_id = self._generate_uuid_from_id(record_id)
        prepared_metadata = self._prepare_qdrant_metadata(metadata.copy())

        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(id=uuid_id, vector=vector, payload=prepared_metadata)
            ],
        )

    def delete_record(self, record_id):
        try:
            uuid_id = self._generate_uuid_from_id(record_id)
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[uuid_id]),
            )
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"Failed to delete record with ID {record_id} from vector database: {str(e)}"
                )

    def search_for_results(self, query_text, top_k=10):
        threshold = 0.2

        if not self.collection:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    "Vector database is not available for search."
                )
            return []

        try:
            vectorised_query = self.vectorize_intent(query_text)
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=vectorised_query,
                limit=top_k,
                with_payload=True,
            )

            search_results = []
            for result in results:
                if result.score > threshold:
                    original_id = self._extract_original_id(result.payload)
                    search_results.append(
                        {"id": original_id or str(result.id), "score": result.score}
                    )

            return search_results
        except Exception as e:
            if self.output_manager:
                self.output_manager.display_system_messages(
                    f"An error occurred during the search: {str(e)}"
                )
            return []
