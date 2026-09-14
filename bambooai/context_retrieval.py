import os
import pandas as pd
import json
import time
import threading
import logging
from bambooai.messages.prompts import PromptManager

# Configure logging for debugging
from logger_config import get_logger
logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# consult_assistant call cap (per query / chain_id)
#
# The Socratic assistant is deliberately non-terminal: it returns only questions
# and never resolves, which drives tool-eager models (e.g. Grok) into repeated
# consultations. We cap the number of ACTUAL consultations per chain. Calls beyond
# the cap short-circuit with a firm directive to proceed and do NOT invoke the
# assistant model, so the expensive part happens at most `CONSULT_ASSISTANT_MAX_CALLS`
# times regardless of the calling model's temperament. This lives here (the single
# function every provider loop calls) rather than in each provider's tool loop.
# ──────────────────────────────────────────────────────────────────────────
CONSULT_ASSISTANT_MAX_CALLS = 1
_consult_counts = {}
_consult_lock = threading.Lock()
_CONSULT_COUNTS_MAX_ENTRIES = 10000  # simple bound to avoid unbounded growth on long-lived servers


def _register_consult_call(chain_id):
    """Increment and return the running consult count for this chain_id."""
    with _consult_lock:
        if len(_consult_counts) > _CONSULT_COUNTS_MAX_ENTRIES:
            _consult_counts.clear()
        n = _consult_counts.get(chain_id, 0) + 1
        _consult_counts[chain_id] = n
        return n


def reset_consult_count(chain_id=None):
    """Reset the consult counter for one chain, or all chains when chain_id is None.
    Optional hook if a caller wants to clear state between queries explicitly."""
    with _consult_lock:
        if chain_id is None:
            _consult_counts.clear()
        else:
            _consult_counts.pop(chain_id, None)


def request_user_context(output_manager, log_and_call_manager, chain_id, query_clarification, context_needed):
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
        return _format_feedback_response(feedback)

    # Running in web mode
    # Construct feedback file path
    user_id = log_and_call_manager.user_id
    feedback_file = os.path.join('temp', user_id,f'feedback_{chain_id}.json') if user_id else os.path.join('temp', f'feedback_{chain_id}.json')

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
                        return _format_feedback_response(feedback)
            except (json.JSONDecodeError, KeyError, IOError) as e:
                logger.warning(f'Error reading {feedback_file}: {str(e)}. Continuing to poll.')
        else:
            logger.debug(f'Feedback file {feedback_file} does not exist yet.')
        time.sleep(poll_interval)

    return _format_feedback_response("No user feedback received within timeout period. Proceeding with default assumptions.")


def _format_feedback_response(feedback: str) -> str:
    """Wrap user feedback with instruction to produce final structured output."""
    return (
        f"User feedback: {feedback}\n\n"
        "Incorporate the user's feedback and now provide your final response "
        "in the required output format as specified in your system instructions."
    )


def consult_assistant(output_manager, log_and_call_manager, chain_id,
                      analytical_goal, data_context, decision_point,
                      options_considered, plan_constraints=None, reasoning_models=None, api_keys=None):
    """
    Requests a second opinion from a fast Socratic assistant model (Default "Gemini 3.0 Flash).

    Capped at CONSULT_ASSISTANT_MAX_CALLS consultations per chain_id: calls beyond the
    cap return a firm proceed directive without invoking the assistant model.
    """
    from bambooai.models import ModelManager
    from bambooai.messages.prompts import PromptManager

    # --- Enforce the per-chain consultation cap BEFORE any work/UI/model call ---
    call_number = _register_consult_call(chain_id)
    if call_number > CONSULT_ASSISTANT_MAX_CALLS:
        logger.info(
            "consult_assistant call #%s for chain %s exceeds cap of %s; returning proceed directive "
            "(assistant not invoked).",
            call_number, chain_id, CONSULT_ASSISTANT_MAX_CALLS,
        )
        return (
            "You have already consulted the assistant the maximum number of times allowed for this "
            "task. Do NOT call consult_assistant again. You have enough to proceed — generate the "
            "final, complete Python code now in the required output format."
        )

    prompt_manager = PromptManager(custom_prompt_file_path=None)

    # Display the tool call element FIRST (this creates the collapsible UI element)
    output_manager.display_tool_info(
        'Consulting Assistant',
        f"Seeking second opinion on: {decision_point}",
        chain_id=chain_id
    )

    # Build the consultation prompt
    consultation_prompt = _build_consultation_prompt(
        analytical_goal,
        data_context,
        decision_point,
        options_considered,
        plan_constraints
    )

    # Prepare messages for the assistant
    assistant_messages = [
        {"role": "system", "content": prompt_manager.socratic_assistant_system},
        {"role": "user", "content": consultation_prompt}
    ]

    try:
        # Initialize ModelManager
        models = ModelManager(log_and_call_manager.user_id, api_keys=api_keys)

        # Enable silent mode to capture output without displaying
        output_manager.set_silent(True)

        try:
            # Call the Socratic Assistant agent
            response_content = models.llm_stream(
                prompt_manager=prompt_manager,
                log_and_call_manager=log_and_call_manager,
                output_manager=output_manager,
                reasoning_models=reasoning_models,
                reasoning_effort="low",
                messages=assistant_messages,
                agent='Socratic Assistant',
                chain_id=chain_id,
                tools=None
            )

            # Get captured output if response is empty
            if not response_content or (isinstance(response_content, str) and response_content.strip() == ''):
                response_content = output_manager.get_captured_output()

        finally:
            # Always disable silent mode when done
            output_manager.set_silent(False)

        # Send structured consultation result to populate the tool call element
        output_manager.send_assistant_consultation(
            chain_id=chain_id,
            query_summary=decision_point,
            response_content=response_content
        )

        return response_content

    except Exception as e:
        # Ensure silent mode is off even on error
        output_manager.set_silent(False)

        error_msg = f"Error consulting assistant: {str(e)}"
        logger.warning(error_msg)
        output_manager.display_error(error_msg, chain_id=chain_id)
        return f"Unable to get assistant perspective: {str(e)}. Proceeding with your current reasoning."


def _build_consultation_prompt(analytical_goal, data_context, decision_point,
                                options_considered, plan_constraints=None):
    """
    Builds a structured prompt for the Socratic assistant.
    """
    prompt_parts = [
        "I'm implementing a data analysis solution and would like your perspective on a decision I'm facing.",
        "",
        "## ANALYTICAL GOAL",
        analytical_goal,
        "",
        "## DATA CONTEXT",
        data_context,
        "",
        "## DECISION POINT",
        decision_point,
        "",
        "## OPTIONS I'M CONSIDERING",
        options_considered,
    ]

    if plan_constraints and plan_constraints.lower() != 'none':
        prompt_parts.extend([
            "",
            "## CONSTRAINTS FROM THE PLAN",
            plan_constraints
        ])

    prompt_parts.extend([
        "",
        "What considerations might I be overlooking? Are there edge cases or potential issues with my current thinking?"
    ])

    return "\n".join(prompt_parts)


def _truncate_response(text, max_length):
    """Truncates text for display purposes."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."