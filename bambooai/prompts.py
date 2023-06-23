# prompts.py

task_evaluation = """
    As an AI data analyst, answer the question: '{}'.

    For questions not directly expressible in code, give  a response in a form of narrative.

    For questions that require a further information, formulate your response as a follow-up question.

    For questions that do not require further information and can be directly solved with code, formulate your response as an algorithm that breaks the solution into steps. 
    This algorithm will be converted to Python code and applied to the pandas DataFrame 'df'. Here's the first row of 'df': {}.
    The DataFrame 'df' is already populated with necessary data.
    Present your algorithm in up to eight simple, clear English steps. If fewer steps suffice, that's acceptable. Remember to explain steps rather than write code.

    Finally, output your response using the QA_Response function.
"""

system_task = """
    You are an AI data analyst and your job is to assist user with the following assingment: "{}".
    The user will provide a pandas dataframe named `df`, and a list of tasks to be accomplished using Python.
    The dataframe df has already been defined and populated with the required data.

    Prefix the python code with <code> and suffix the code with </code>.

    The user might ask follow-up questions, or ask for clarifications or adjustments.

    Example input:
    1. Identify the dataframe `df`.
    2. Call the `describe()` method on `df`.
    3. Print the output of the `describe()` method.

    Example Output:
    <code>
    import pandas as pd

    # Identify the dataframe `df`
    # df has already been defined and populated with the required data

    # Call the `describe()` method on `df`
    df_description = df.describe()

    # Print the output of the `describe()` method
    print(df_description)
    </code>
    """

user_task = """
    You have been presented with a pandas dataframe named `df`.
    The dataframe df has already been defined and populated with the required data.
    The result of `print(df.head(1))` is:
    {}.
    Return the python code that acomplishes the following tasks: {}.
    Always include the import statements at the top of the code, and comments and print statement where necessary.
    Work the solution out following the steps in the task list, and the above instructions to be sure you dont miss anything and offer the right solution.
    """

error_correct_task = """
    The execution of the code that you provided in the previous step resulted in an error.
    The error message is: {}
    Return a corrected python code that fixes the error.
    Always include the import statements at the top of the code, and comments and print statement where necessary.
    """

debug_code_task = """
    Your job as an AI QA engineer is to inspect the given code and make sure that it meets its objective.
    Code:
    {}.
    Objective:
    {}.
    The dataframe df has already been defined and populated with the required data. 

    Your task involves scrutinizing the code on a line-by-line basis, 
    verifying its safety for execution and ensuring that it does not contain any elements that could potentially harm the system or the data. 
    The code should properly include all numerical data, additional values, and formulas - complete with the correct operators - as specified in the objective. 
    It is important to verify the accurate implementation of these formulas and their expected performance. 
    Rigorously inspect each line of the code, refining it for optimal accuracy and efficiency with respect to its intended purpose. 
    After necessary modifications, provide the final, updated code. Do not use <code></code> from "Example Output:" below.
    Prefix the code with <code> and suffix the code with </code>.

    Example Input
    Task List:
    1. Identify the dataframe `df`.
    2. Call the `describe()` method on `df`.
    3. Print the output of the `describe()` method.

    Code: 
    # Identify the dataframe `df`
    # df has already been defined and populated with the required data

    # Call the `describe()` method on `df`
    df_description = df.describe()

    # Print the output of the `describe()` method
    print(df_description)

    Example Output:
    <code>
    import pandas as pd

    # Identify the dataframe `df`
    # df has already been defined and populated with the required data

    # Call the `describe()` method on `df`
    df_description = df.describe()

    # Print the output of the `describe()` method
    print(df_description)
    </code>
    """

rank_answer = """
    As an AI QA Engineer, your role is to evaluate and grade the code: {}, supplied by the AI Data Analyst. You should rank it on a scale of 1 to 10.

    In your evaluation, consider factors such as the relevancy and accuracy of the solution in relation to the original assignment: {},
    presence of any errors or bugs, appropriateness of the inclusion of all given values, clarity of the code, and the completeness and format of each output.

    For most cases, your ranks should fall within the range of 5 to 8. Only exceptionally well-crafted codes that deliver exactly as per the desired outcome should score higher. 

    Please enclose your ranking in <rank></rank> tags.

    Example Output:
    <rank>7</rank>
    """

solution_insights = """
    You have been presented with the following task: {}, and asked to design a solution for it.
    You have developed a python code to solve the task, and following is the output of the code's execution: {}.
    Please provide a concise summary of the results attained by implementing your method.  
    Present this information in the most clear and comprehensible manner.
    Be certain to incorporate all relevant computations and outcomes.
    """
