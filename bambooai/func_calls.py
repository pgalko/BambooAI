# func_calls.py

task_eval_function = [
    {
        "name": "QA_Response",
        "description": "The answer classification function",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Answer as a narrative, or as an algorithm",
                },
                "answer_type": {
                    "type": "string",
                    "enum": ["narrative", "algorithm"],
                    "description": "Task classification",
                },
            },
            "required": ["answer", "answer_type"],
            },
    },
    ]

solution_insights_function = [
    {
        "name": "Solution_Insights",
        "description": "The solution summary and insights function",
        "parameters": {
            "type": "object",
            "properties": {
                "insight": {
                    "type": "string",
                    "description": "Delivers a comprehensive summary of the outcomes obtained from the execution of the python code",
                },
            },
            "required": ["insight"],
            },
    },
    ]

openai_search_function = [
  {
    "type": "function",
    "function": {
      "name": "google_search",
      "description": "This function executes a Google search and delivers results by identifying and summarizing the most relevant documents from the returned search results.",
      "parameters": {
        "type": "object",
        "properties": {
          "search_query": {
            "type": "string",
            "description": "A full query string to search for, including all required details.",
          }
        },
        "required": ["search_query"]
      }
    }
  }
]

anthropic_search_function = [
  {
    "name": "google_search",
    "description": "This function executes a Google search and delivers results by identifying and summarizing the most relevant documents from the returned search results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "search_query": {
                "type": "string",
                "description": "A full query string to search for, including all required details.",
            }
        },
        "required": ["search_query"]
    }
  }
]