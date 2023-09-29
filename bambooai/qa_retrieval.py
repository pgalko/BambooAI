import pinecone
from sentence_transformers import SentenceTransformer
import os
import hashlib

try:
    # Attempt package-relative import
    from . import output_manager
except ImportError:
    # Fall back to script-style import
    import output_manager

output_manager = output_manager.OutputManager()

def init_pinecone():
    # Get the PINECONE_API_KEY and PINECONE_ENV environment variables
    PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
    PINECONE_ENV = os.getenv('PINECONE_ENV')

    if PINECONE_API_KEY is None or PINECONE_ENV is None:
        output_manager.print_wrapper("Warning: PINECONE_API_KEY or PINECONE_ENV environment variable not found.")
        return None, None

    # Initialize Pinecone
    pinecone.init(api_key=PINECONE_API_KEY,environment=PINECONE_ENV)

    # Load sentence transformer model
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Create a new Pinecone index if it doesnt exist
    index_name = "bambooai-qa-retrieval"
    if index_name not in pinecone.list_indexes():
        output_manager.print_wrapper(f"Creating a new vector db index. Please wait... {index_name}")
        pinecone.create_index(name=index_name, metric="cosine", shards=1, dimension=384)

    # Instantiate Pinecone index
    index = pinecone.Index(index_name=index_name)

    return model, index

def add_question_answer_pair(question, df_columns, code, new_rank):
    model, index = init_pinecone()
    # Check if the new rank is above the threshold
    new_rank=int(new_rank)
    if new_rank < 8:
        output_manager.print_wrapper("The new rank is below the threshold. Not adding/updating the vector db record.")
        return

    # Hash the question to be used as id
    id = hashlib.sha256(question.encode()).hexdigest()

    # Vectorize the question
    xq = model.encode([question])[0].tolist()  # Convert the vector to a 1D list

    # Fetch the existing data, if any
    existing_data = index.fetch(ids=[id])
    
    # If the question already exists, get the existing rank
    if existing_data and 'vectors' in existing_data and id in existing_data['vectors']:
        existing_rank = existing_data['vectors'][id]['metadata']['rank']
    else:
        existing_rank = -1

    # If the existing rank is less than the new rank, add or update the question vector and associated data
    if existing_rank < new_rank:
        metadata = {"df_col":df_columns,"question_txt":question,"code":code,"rank": new_rank}
        vectors = [(id,xq,metadata)]
        index.upsert(vectors=vectors)
        output_manager.print_wrapper(f"Added/Updated the vector db record with id: {id}")
    else:
        output_manager.print_wrapper(f"Existing rank {existing_rank} is higher or equal to the new rank. I am not updating the existing vector db record.")


def retrieve_answer(question, df_columns, match_df=True, similarity_threshold=0.9):
    model, index = init_pinecone()
    # Vectorize the question
    vector = model.encode([question])[0].tolist()  # Convert the vector to a 1D list
    
    # Query the Pinecone index for the closest matching question
    results = index.query(queries=[vector], top_k=1)

    matches = results.get('results', [{}])[0].get('matches', [])

    if not matches:
        output_manager.print_wrapper("No vector db match found")
        return None

    match = matches[0]
    closest_match_id = match['id']
    similarity_score = match['score']
    output_manager.print_wrapper(f"Closest match vector db record: {closest_match_id}, Similarity score: {similarity_score}")
    
    # Check if the similarity score is above the threshold
    if similarity_score < similarity_threshold:
        output_manager.print_wrapper(f"Similarity score {similarity_score} is below the threshold {similarity_threshold}")
        return None

    fetched_data = index.fetch(ids=[closest_match_id])
    vector_data = fetched_data.get('vectors', {}).get(closest_match_id, {})

    if not vector_data:
        output_manager.print_wrapper("No data found for this vector db id")
        return None

    # Get the metadata
    metadata = vector_data['metadata']
    # Check if the dataframe columns match
    if match_df:
        if metadata['df_col'] == df_columns:
            code = metadata['code']
        else:
            output_manager.print_wrapper("The dataframe columns do not match. I will not use this record.")
            return None
    # Return the matadata withouth checking the dataframe columns
    else:
        code = metadata['code']

    return code


