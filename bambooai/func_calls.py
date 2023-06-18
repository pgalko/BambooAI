# func_calls.py

task_eval_function = [
    {
        "name": "QA_Response",
        "description": "The task classification function",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "Output the answer in  either natural language or as a heuristic algorithm depending on the task classification.",
                },
                "answer_type": {
                    "type": "string",
                    "description": "The class of the response depending on the task. It is either natural_language or heuristic_algorithm",
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
