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