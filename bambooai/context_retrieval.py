import os
import pandas as pd
import json
import time
import logging

# Configure logging for debugging
logging.basicConfig(level=logging.WARNING,)
logger = logging.getLogger(__name__)
    
def request_user_context(output_manager, chain_id, query_clarification, context_needed):
    """
    Requests user feedback and waits for the response.
    
    Args:
        output_manager: The output manager to handle displaying information.
        chain_id: The ID of the current chain.
        query_clarification: The question to ask the user.
        context_needed: The type of context required.
        
    Returns:
        str: The user's feedback or a default message if timed out.
    """

    output_manager.display_tool_info(
        'Feedback Request',
        f"The model needs clarification on your query",
        chain_id=chain_id
    )

    # Send feedback request to UI or CLI, depending on the mode
    feedback = output_manager.request_user_feedback(
                    chain_id=chain_id,
                    query_clarification=query_clarification,
                    context_needed=context_needed
                )
    
    # Running in Notebook or CLI mode
    if feedback is not None:
        return feedback
    
    # Running in web mode
    # Construct feedback file path

    feedback_file = os.path.join('temp', f'feedback_{chain_id}.json')

    # Poll for feedback
    timeout = 300  # 5 minutes
    poll_interval = 2  # Check every 2 seconds
    start_time = time.time()
    initial_delay = True

    while time.time() - start_time < timeout:
        if initial_delay:
            time.sleep(0.5)  # Brief delay to allow file write
            initial_delay = False

        if os.path.exists(feedback_file):
            try:
                with open(feedback_file, 'r') as f:
                    feedback_list = json.load(f)
                # Find feedback matching query_clarification
                for feedback_entry in feedback_list:
                    if feedback_entry['query_clarification'] == query_clarification:
                        feedback = feedback_entry['feedback']
                        # Delete the file
                        try:
                            os.remove(feedback_file)
                        except OSError as e:
                            logger.warning(f'Failed to delete {feedback_file}: {str(e)}')
                        return feedback
            except (json.JSONDecodeError, KeyError, IOError) as e:
                logger.warning(f'Error reading {feedback_file}: {str(e)}. Continuing to poll.')
        else:
            logger.debug(f'Feedback file {feedback_file} does not exist yet.')
        time.sleep(poll_interval)

    return "No user feedback received within timeout period. Proceeding with default assumptions."
