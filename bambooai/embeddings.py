"""
Embedding clients for the memory pack's hook retrieval.

Lifted verbatim from the retired qa_retrieval module (step 23): the
QA store died with the old episodic memory, but the embedders
outlive it - the pack's semantic retrieval over card hooks is their new
and only consumer. Selection follows the same convention the QA layer
used: EMBEDDING_PLATFORM chooses "openai" (text-embedding-3-small) or
"hf_sentence_transformers"; any failure to construct a client leaves the
caller on its deterministic lexical fallback.
"""

import os

from logger_config import get_logger

logger = get_logger(__name__)


class EmbeddingClientIntegration:
    def vectorize(self, text_input):
        raise NotImplementedError


class OpenAIEmbeddingClient(EmbeddingClientIntegration):
    def __init__(self, api_key=None):
        """
        Initialize OpenAI client with API key precedence:
        1. Use provided api_key parameter
        2. Fall back to environment variable
        """
        from openai import OpenAI
        client_api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if client_api_key is None:
            raise ValueError("OpenAI API key not provided and OPENAI_API_KEY "
                             "environment variable not set")
        self.client = OpenAI(api_key=client_api_key)

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
            raise RuntimeError("Sentence Transformers library is not "
                               "installed.")

    def vectorize(self, text_input):
        return self.model.encode([text_input])[0].tolist()


def build_embedding_client():
    """The platform-selected client, or None when construction fails -
    callers degrade to lexical matching, never binarily."""
    platform = os.getenv('EMBEDDING_PLATFORM', 'openai')
    try:
        if platform == 'hf_sentence_transformers':
            return HFSentenceTransformersClient()
        return OpenAIEmbeddingClient()
    except Exception as exc:                                    # noqa: BLE001
        logger.info("No embedding client (%s): lexical fallback in use", exc)
        return None