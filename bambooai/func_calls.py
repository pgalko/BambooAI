# func_calls.py

openai_tools_definition = [
  {
    "type": "function",
    "function": {
      "name": "google_search",
      "description": "This function executes a Google search and delivers results by identifying and summarizing the most relevant documents from the returned search results. Use this function only if user specficly requests to use Google search.",
      "parameters": {
        "type": "object",
        "properties": {
          "search_query": {
            "type": "string",
            "description": "A full query string to search for, including all required details."
          }
        },
        "required": ["search_query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_auxiliary_dataset",
      "description": "Retrieves path to and the preview (head) of a auxiliary dataset containing data that adds additional context to the main dataset.",
      "parameters": {
        "type": "object",
        "properties": {
            "file_format": {
                "type": "string",
                "description": "Desired format for the dataset file",
                "enum": ["csv"]
            }
        },
        "required": ["file_format"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "request_user_context",
      "description": "Call this function whenever the user's query is ambiguous, incomplete, lacks specific details, or could benefit from additional context to provide a more accurate or tailored response. This includes cases where user intent is unclear, key information is missing, or assumptions might lead to suboptimal answers. The function prompts the user to provide clarification or supplementary details.",
      "parameters": {
        "type": "object",
        "properties": {
          "query_clarification": {
          "type": "string",
          "description": "A clear, concise question or prompt to ask the user to elicit the needed context. Tailor the prompt to the specific ambiguity or gap in the original query."
          },
          "context_needed": {
          "type": "string",
          "enum": [
            "clarify_intent",
            "missing_details",
            "specific_example",
            "user_preferences",
            "other"
          ],
          "description": "The type of context required. Use 'clarify_intent' for unclear goals, 'missing_details' for absent specifics, 'specific_example' for illustrative cases, 'user_preferences' for personalized needs, or 'other' for miscellaneous gaps."
        }
      },
      "required": ["query_clarification","context_needed"]
      } 
    }
  }
]

anthropic_tools_definition = [
   {
      "name": "google_search",
      "description": "This function executes a Google search and delivers results by identifying and summarizing the most relevant documents from the returned search results. Use this function only if user specficly requests to use Google search.",
      "input_schema": {
          "type": "object",
          "properties": {
              "search_query": {
                  "type": "string", 
                  "description": "A full query string to search for, including all required details."
              }
          },
          "required": ["search_query"]
      }
   },
   {
      "name": "get_auxiliary_dataset",
      "description": "Retrieves path to and the preview (head) of a auxiliary dataset containing data that adds additional context to the main dataset.",
      "input_schema": {
          "type": "object",
          "properties": {
              "file_format": {
                  "type": "string",
                  "description": "Desired format for the dataset file",
                  "enum": ["csv"]
              }
          },
          "required": ["file_format"]
      }
   },
   {
      "name": "request_user_context",
      "description": "Call this function whenever the user's query is ambiguous, incomplete, lacks specific details, or could benefit from additional context to provide a more accurate or tailored response. This includes cases where user intent is unclear, key information is missing, or assumptions might lead to suboptimal answers. The function prompts the user to provide clarification or supplementary details.",
      "input_schema": {
          "type": "object",
          "properties": {
              "query_clarification": {
                  "type": "string",
                  "description": "A clear, concise question or prompt to ask the user to elicit the needed context. Tailor the prompt to the specific ambiguity or gap in the original query."
              },
              "context_needed": {
                  "type": "string",
                  "enum": [
                      "clarify_intent",
                      "missing_details",
                      "specific_example",
                      "user_preferences",
                      "other"
                  ],
                  "description": "The type of context required. Use 'clarify_intent' for unclear goals, 'missing_details' for absent specifics, 'specific_example' for illustrative cases, 'user_preferences' for personalized needs, or 'other' for miscellaneous gaps."
              }
          },
          "required": ["query_clarification","context_needed"]
      }
  }
]

gemini_tools_definition = [
    {
        "name": "google_search",
        "description": "This function executes a Google search and delivers results by identifying and summarizing the most relevant documents from the returned search results. Use this function only if user specficly requests to use Google search.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "A full query string to search for, including all required details."
                }
            },
            "required": ["search_query"]
        }
    },
    {
        "name": "get_auxiliary_dataset",
        "description": "Retrieves path to and the preview (head) of a auxiliary dataset containing data that adds additional context to the main dataset.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_format": {
                    "type": "string",
                    "description": "Desired format for the dataset file",
                    "enum": ["csv"]
                }
            },
            "required": ["file_format"]
        }
    },
    {
        "name": "request_user_context",
        "description": "Call this function whenever the user's query is ambiguous, incomplete, lacks specific details, or could benefit from additional context to provide a more accurate or tailored response. This includes cases where user intent is unclear, key information is missing, or assumptions might lead to suboptimal answers. The function prompts the user to provide clarification or supplementary details.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_clarification": {
                    "type": "string",
                    "description": "A clear, concise question or prompt to ask the user to elicit the needed context. Tailor the prompt to the specific ambiguity or gap in the original query."
                },
                "context_needed": {
                    "type": "string",
                    "enum": [
                        "clarify_intent",
                        "missing_details",
                        "specific_example",
                        "user_preferences",
                        "other"
                    ],
                    "description": "The type of context required. Use 'clarify_intent' for unclear goals, 'missing_details' for absent specifics, 'specific_example' for illustrative cases, 'user_preferences' for personalized needs, or 'other' for miscellaneous gaps."
                }
            },
            "required": ["query_clarification","context_needed"]
        }
    }
]