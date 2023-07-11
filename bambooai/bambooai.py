
import os
import re
import sys
import json
from contextlib import redirect_stdout
import io
import time
import pandas as pd
from termcolor import colored, cprint
from IPython.display import display,HTML
import warnings
warnings.filterwarnings('ignore')

#Running as a script
#import models
#import prompts
#import func_calls
#import qa_retrieval
#import_google_search # Included in the package, but not ready yet. Will need some more work.

#Running as a package
from . import models
from . import prompts
from . import func_calls
from . import qa_retrieval
#from . import google_search # Included in the package, but not ready yet. Will need some more work.

class BambooAI:
    def __init__(self, df: pd.DataFrame,
                 max_conversations: int = 4,
                 llm: str = 'gpt-3.5-turbo-0613', # Base Model
                 debug: bool = False, 
                 vector_db: bool = False, 
                 llm_switch: bool = False, 
                 exploratory: bool = True, 
                 ):

        # Check if the OPENAI_API_KEY environment variable is set
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
        
        # Check if the PINECONE_API_KEY and PINECONE_ENV environment variables are set if vector_db is True
        if vector_db:
            PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
            PINECONE_ENV = os.getenv('PINECONE_ENV')
            
            if PINECONE_API_KEY is None or PINECONE_ENV is None:
                print("Warning: PINECONE_API_KEY or PINECONE_ENV environment variable not found. Disabling vector_db.")
                vector_db = False

        self.MAX_ERROR_CORRECTIONS = 5
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1
        
        # Store the original dataframe. This will be used to reset the dataframe before executing the code
        self.original_df = df
        self.df = df.copy()  # make a copy of the dataframe
        self.df_head = self.original_df.head(1)
        self.df_columns = self.df.columns.tolist()

        # LLMs
        # model dict
        self.model_dict = {"llm": llm,
                           "llm_gpt4": "gpt-4-0613",
                           "llm_16k": "gpt-3.5-turbo-16k",
                           "llm_func": "gpt-3.5-turbo-0613",}

        # Set the debug mode. This mode is True when you want the model to debug the code and correct it.
        self.debug = debug
        # Set the llm_switch mode. This mode is True when you want the model to switch to gpt-4 for debugging, error correction and ranking.
        self.llm_switch = llm_switch
        # Set the rank mode. This mode is True when you want the model to rank the generated code.
        self.vector_db = vector_db

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original prompt and break it down in algorithm.
        self.exploratory = exploratory
        
        # Prompts
        self.default_example_output = prompts.example_output
        self.task_evaluation = prompts.task_evaluation
        self.system_task = prompts.system_task
        self.user_task = prompts.user_task
        self.error_correct_task = prompts.error_correct_task
        self.debug_code_task = prompts.debug_code_task  
        self.rank_answer = prompts.rank_answer
        self.solution_insights = prompts.solution_insights

        # Functions
        self.task_eval_function = func_calls.task_eval_function
        self.insights_function = func_calls.solution_insights_function

        # LLM calls
        self.llm_call = models.llm_call
        self.llm_func_call = models.llm_func_call
        self.llm_stream = models.llm_stream

        # QA Retrieval
        self.add_question_answer_pair = qa_retrieval.add_question_answer_pair
        self.retrieve_answer = qa_retrieval.retrieve_answer
        self.similarity_threshold = 0.8

        # Initialize the total tokens used list. This list will be used to keep track of the total tokens used by the model
        self.total_tokens_used = []


    # Functions to sanitize the output from the LLM
    def _extract_code(self,response: str, separator: str = "```") -> str:

        # Define a blacklist of Python keywords and functions that are not allowed
        blacklist = ['os','subprocess','sys','eval','exec','file','socket','urllib',
                    'shutil','pickle','ctypes','multiprocessing','tempfile','glob','code','pty','commands',
                    'requests','cgi','cgitb','xml.etree.ElementTree','builtins'
                    ]

        # Search for a pattern between <code> and </code> in the extracted code
        match = re.search(r"<code>(.*)</code>", response, re.DOTALL)
        if match:
            # If a match is found, extract the code between <code> and </code>
            code = match.group(1)
            # If the response contains the separator, extract the code block between the separators
            if len(code.split(separator)) > 1:
                code = code.split(separator)[1]

        # If the response contains the separator, extract the code block between the separators
        if len(response.split(separator)) > 1:
            code = response.split(separator)[1]
            
        # Remove the "python" or "py" prefix if present
        if re.match(r"^(python|py)", code):
            code = re.sub(r"^(python|py)", "", code)
        # If the code is between single backticks, extract the code between them
        if re.match(r"^`.*`$", code):
            code = re.sub(r"^`(.*)`$", r"\1", code)

        # Remove any instances of "df = pd.read_csv('filename.csv')" from the code
        code = re.sub(r"df\s*=\s*pd\.read_csv\('.*?'(,.*)?\)", "", code)

        # Define the regular expression pattern to match the blacklist items
        pattern = r"^(.*\b(" + "|".join(blacklist) + r")\b.*)$"

        # Replace the blacklist items with comments
        code = re.sub(pattern, r"# not allowed \1", code, flags=re.MULTILINE)

        # Return the cleaned and extracted code
        return code.strip()
    
    def _extract_rank(self,response: str) -> str:

        # Search for a pattern between <rank> and </rank> in the response
        match = re.search(r"<rank>(.*)</rank>", response)
        if match:
            # If a match is found, extract the rank between <rank> and </rank>
            rank = match.group(1)
        else:
            rank = ""

        # Return the cleaned and extracted code
        return rank.strip()
    
    # Function to remove examples from messages when no longer needed
    def _remove_examples(self,messages: str) -> str:
        # Define the regular expression pattern
        pattern = 'Example Output:\s*<code>.*?</code>\s*'

        # Iterate over the list of dictionaries
        for dict in messages:
            # Access and clean up 'content' field
            if dict.get('role') == 'user' and 'content' in dict:
                dict['content'] = re.sub(pattern, '', dict['content'], flags=re.DOTALL)

        return messages
    
    def task_eval(self, eval_messages):
        
        llm_func = self.model_dict['llm_func']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {llm_func}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Trying to determine the best method to answer your question, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {llm_func}", "magenta"))
            cprint(f"\n>> Trying to determine the best method to answer your question, please wait...\n", 'magenta', attrs=['bold'])

        # Call OpenAI API
        function_name = {"name": "QA_Response"}
        fn_name, arguments, tokens_used = self.llm_func_call(self.model_dict, eval_messages,self.task_eval_function, function_name)

        # Parse the JSON string to a Python dict
        arguments_dict = json.loads(arguments, strict=False)

        # Retrieve values
        eval_answer = arguments_dict["answer"]
        eval_answer_type = arguments_dict["answer_type"]

        self.total_tokens_used.append(tokens_used)

        return arguments, fn_name, eval_answer, eval_answer_type

    def debug_code(self,code,question, llm_cascade=False):
        # Initialize the messages list with a system message containing the task prompt
        debug_messages = [{"role": "system", "content": self.debug_code_task.format(code,question)}]

        using_model = self.model_dict['llm']
        if llm_cascade:
            using_model = self.model_dict['llm_gpt4']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {using_model}</p>'))
            display(HTML(f'<p><b style="color:magenta;"> I am reviewing and debugging the first version of the code to check for any errors, bugs, or inconsistencies and will make corrections if necessary. Please wait..</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {using_model}", "magenta"))
            cprint(f"\n>> I am reviewing and debugging the first version of the code to check for any errors, bugs, or inconsistencies and will make corrections if necessary. Please wait...\n", 'magenta', attrs=['bold'])

        # Function to display results nicely
        def display_task():
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:magenta;">I have finished debugging the code, and will now proceed to the execution...</b></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\n>> I have finished debugging the code, and will now proceed to the execution...\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API
        llm_response, tokens_used = self.llm_stream(self.model_dict, debug_messages,temperature=0,llm_cascade=llm_cascade) # higher temperature results in more "creative" answers (sometimes too creative :-))
        
        # Extract the code from the API response
        debugged_code = self._extract_code(llm_response)       
        display_task()

        self.total_tokens_used.append(tokens_used)

        return debugged_code

    def rank_code(self,code,question,llm_cascade=False):
        # Initialize the messages list with a system message containing the task prompt
        rank_messages = [{"role": "system", "content": self.rank_answer.format(code,question)}]

        using_model = self.model_dict['llm']
        if llm_cascade:
            using_model = self.model_dict['llm_gpt4']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {using_model}</p>'))
            display(HTML(f'<p><b style="color:magenta;">I am going to evaluate and rank the answer. Please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {using_model}", "magenta"))
            cprint(f"\n>> I am going to evaluate and rank the answer. Please wait..\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API 
        llm_response, tokens_used = self.llm_call(self.model_dict, rank_messages,llm_cascade=llm_cascade)

        # Extract the rank from the API response
        rank = self._extract_rank(llm_response)       

        self.total_tokens_used.append(tokens_used)

        return rank

    def pd_agent_converse(self, question=None):
        # Functions to display results nicely
        def display_results(answer, code, rank, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:     
                if answer is not None:
                    display(HTML(f'<p><b style="color:blue;">I now have the final answer:</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{answer}</pre></p><br>'))
                if code is not None:
                    display(HTML(f'<p><b style="color:blue;">Here is the final code that accomplishes the task:</b><br><pre style="color:#555555;">{code}</pre></p><br>'))
                if self.vector_db and rank is not None:
                    display(HTML(f'<p><b style="color:blue;">Rank:</b><br><span style="color:black;">{rank}</span></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                if answer is not None:
                    cprint(f"\n>> I now have the final answer:\n{answer}\n", 'green', attrs=['bold'])
                if code is not None:
                    cprint(">> Here is the final code that accomplishes the task:", 'green', attrs=['bold'])
                    print(code)
                if self.vector_db and rank is not None:
                    cprint("\n>> Rank:", 'green', attrs=['bold'])
                    print(rank)
                cprint(f"\n>> Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])

        def display_eval(task_eval, title, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:blue;">{title}</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{task_eval}</pre></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                # Other environment (like terminal)
                print(f"\n>> {title}\n{task_eval}\n")
                cprint(f">> Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])

        # Initialize the eval_messages list
        eval_messages = []
        
        # If a question is provided, skip the input prompt
        if question is not None:
            # Initialize the messages list with a system message containing the task prompt
            messages = [{"role": "system", "content": self.system_task}]
            # Initialize the messages list with a system message containing the task prompt
            eval_messages.append({"role": "user", "content": self.task_evaluation.format(question, self.df_head)})

            # Call the task_eval method with the user's question if the exploratory mode is True
            if self.exploratory is True:
                arguments, fn_name, task_eval, task_type = self.task_eval(eval_messages)
                total_tokens_used_sum = sum(self.total_tokens_used)
                if task_type == 'narrative':
                    title = 'Here is the answer to your question:'                   
                    display_eval(task_eval, title, total_tokens_used_sum)
                    return
                if task_type == 'follow_up':
                    title = 'To be able to answer your question, I am going to need some more info:'                   
                    display_eval(task_eval, title, total_tokens_used_sum)
                    return
                else:
                    title = 'Here is the sequence of steps required to complete the task:'
                    task = task_eval
                    display_eval(task_eval, title, total_tokens_used_sum)
            else:
                task = question

            if self.vector_db:
                # Call the retrieve_answer method to check if the question has already been asked and answered
                example_output = self.retrieve_answer(task, self.df_columns, similarity_threshold=self.similarity_threshold)
                if example_output is not None:
                    example_output = example_output
                else:
                    example_output = self.default_example_output
            else:
                example_output = self.default_example_output

            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, total_tokens_used_sum = self.pd_agent(task, messages, example_output, self.df)

            # Rank the LLM response
            if self.vector_db:
                # Switch to gpt-4 if llm_switch parameter is set to True. This will increase the processing time and cost
                if self.llm_switch:
                    llm_cascade = True
                else:
                    llm_cascade = False
                rank = self.rank_code(code,task,llm_cascade=llm_cascade)
            else:
                rank = ""

            display_results(answer, code, rank, total_tokens_used_sum)

            if self.vector_db:
                # Prompt the user to to give a feedback on the ranking
                if 'ipykernel' in sys.modules:
                    display(HTML('<b style="color:green;">Are you happy with the ranking ? If YES type \'yes\'. If NO type in the new rank on a scale from 1-10:</b>'))
                    time.sleep(1)
                    rank_feedback = input()
                else:
                    cprint("\nAre you happy with the ranking ?\nIf YES type 'yes'. If NO type in the new rank on a scale from 1-10:", 'green', attrs=['bold'])
                    rank_feedback = input()

                # If the user types "yes", use the rank as is. If not, use the user's rank.
                if rank_feedback.strip().lower() == 'yes':
                    rank = rank
                elif rank_feedback in map(str, range(0, 11)):
                    rank = rank_feedback
                else:
                    rank = rank

                # Add the question and answer pair to the QA retrieval index
                self.add_question_answer_pair(task, self.df_columns, code, rank)

            return
        
        # Start an infinite loop to keep asking the user for questions
        first_iteration = True  # Flag for the first iteration of the loop
        while True:
            # Prompt the user to enter a question or type 'exit' to quit
            if 'ipykernel' in sys.modules:
                display(HTML('<b style="color:blue;">Enter your question or type \'exit\' to quit:</b>'))
                time.sleep(1)
                question = input()
            else:
                cprint("\nEnter your question or type 'exit' to quit:", 'blue', attrs=['bold'])
                question = input()

            # If the user types 'exit', break out of the loop
            if question.strip().lower() == 'exit':
                break

            if first_iteration:
                # Initialize the messages list with a system message containing the task prompt
                messages = [{"role": "system", "content": self.system_task}]
                first_iteration = False  
                
            # Call the task_eval method with the user's question if the exploratory mode is True
            if self.exploratory is True:
                eval_messages.append({"role": "user", "content": self.task_evaluation.format(question, self.df_head)})
                arguments, fn_name, task_eval, task_type = self.task_eval(eval_messages)
                eval_messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": fn_name,
                            "arguments": arguments,
                        },
                    }
                )

                # Remove the oldest conversation from the messages list
                if len(eval_messages) > self.MAX_CONVERSATIONS:
                    eval_messages.pop(0)
                    eval_messages.pop(0)

                total_tokens_used_sum = sum(self.total_tokens_used)

                if task_type == 'narrative':
                    title = 'Here is an answer to your question:'                   
                    display_eval(task_eval, title, total_tokens_used_sum)
                    continue
                else:
                    title = 'Here is a sequence of steps required to complete the task:'
                    task = task_eval
                    display_eval(task_eval, title, total_tokens_used_sum)
            else:
                task = question
            
            if self.vector_db:
                # Call the retrieve_answer method to check if the question has already been asked and answered
                example_output = self.retrieve_answer(task, self.df_columns, similarity_threshold=self.similarity_threshold)
                if example_output is not None:
                    example_output = example_output
                else:
                    example_output = self.default_example_output
            else:
                example_output = self.default_example_output

            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, total_tokens_used_sum = self.pd_agent(task, messages, example_output, self.df)
            
            # Remove the examples from the messages list to minimize the number of tokens used
            messages = self._remove_examples(messages)

            # Rank the LLM response
            if self.vector_db:
                # Switch to gpt-4 if llm_switch parameter is set to True. This will increase the processing time and cost
                if self.llm_switch:
                    llm_cascade = True
                else:
                    llm_cascade = False
                rank = self.rank_code(code,task,llm_cascade=llm_cascade)
            else:
                rank = ""

            display_results(answer, code, rank, total_tokens_used_sum)

            if self.vector_db:
                # Prompt the user to to give a feedback on the ranking
                if 'ipykernel' in sys.modules:
                    display(HTML('<b style="color:green;">Are you happy with the ranking ? If YES type \'yes\'. If NO type in the new rank on a scale from 1-10:</b>'))
                    time.sleep(1)
                    rank_feedback = input()
                else:
                    cprint("\nAre you happy with the ranking ?\nIf YES type 'yes'. If NO type in the new rank on a scale from 1-10:", 'green', attrs=['bold'])
                    rank_feedback = input()

                # If the user types "yes", use the rank as is. If not, use the user's rank.
                if rank_feedback.strip().lower() == 'yes':
                    rank = rank
                elif rank_feedback in map(str, range(0, 11)):
                    rank = rank_feedback
                else:
                    rank = rank

                # Add the question and answer pair to the QA retrieval index
                self.add_question_answer_pair(task, self.df_columns, code, rank)

    def pd_agent(self, task, messages, example_output,df=None):
        # Add a user message with the updated task prompt to the messages list
        messages.append({"role": "user", "content": self.user_task.format(self.df_head, task,example_output)})

        llm = self.model_dict['llm']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">I am generating the first version of the code, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {llm}", "magenta"))
            cprint(f"\n>> I am generating the first version of the code, please wait\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API
        llm_response, tokens_used = self.llm_stream(self.model_dict, messages)

        # Extract the code from the API response
        code = self._extract_code(llm_response)

        # Update the total tokens used
        self.total_tokens_used.append(tokens_used)

        # Initialize error correction counter
        error_corrections = 0

        # Debug code if debug parameter is set to True
        if self.debug:
            # Switch to gpt-4 if llm_switch parameter is set to True. This will increase the processing time and cost
            if self.llm_switch:
                llm_cascade = True
                if 'ipykernel' in sys.modules:
                    # Jupyter notebook
                    display(HTML('<span style="color: magenta;">Switching model to gpt-4 to debug the code.</span>'))
                else:
                    # CLI
                    print(colored("\n>> Switching model to GPT-4 to debug the code.", "magenta"))
            else:
                llm_cascade = False
            code = self.debug_code(code, task, llm_cascade=llm_cascade)

        # Redirect standard output to a StringIO buffer
        with redirect_stdout(io.StringIO()) as output:
            # Try to execute the code and handle errors
            while error_corrections < self.MAX_ERROR_CORRECTIONS:
                try:
                    messages.append({"role": "assistant", "content": llm_response})
                    # Remove the oldest conversation from the messages list
                    if len(messages) > self.MAX_CONVERSATIONS:
                        messages.pop(1)
                        messages.pop(1)
                    # Reset df to the original state before executing the code
                    self.df = self.original_df.copy()
                    # Execute the code
                    if code is not None:
                        exec(code, {'df': self.df})
                    break
                except Exception as e:
                    # Print the error message
                    if 'ipykernel' in sys.modules:
                        # Jupyter notebook
                        display(HTML(f'<br><b><span style="color: #d86c00;">I ran into an issue:</span></b><br><pre style="color: #d86c00;">{e}</pre><br><b><span style="color: #d86c00;">I will examine it, and try again with an adjusted code.</span></b><br>'))
                    else:
                        # CLI
                        sys.stderr.write('\033[31m' + f'>> I ran into an issue: {e}. \n>> I will examine it, and try again with an adjusted code.' + '\033[0m' + '\n')
                        sys.stderr.flush()

                    # Increment the error correction counter and update the messages list with the error
                    error_corrections += 1
                    messages.append({"role": "user", "content": self.error_correct_task.format(e)})

                    # Switch to gpt-4 if llm_switch parameter is set to True. This will increase the processing time and cost.
                    if self.llm_switch:
                        llm_cascade = True
                        if 'ipykernel' in sys.modules:
                            # Jupyter notebook
                            display(HTML('<span style="color: #d86c00;">Switching model to gpt-4 to try to improve the outcome.</span>'))
                        else:
                            # CLI
                            sys.stderr.write('\033[31m' + f'>> Switching model to gpt-4 to try to improve the outcome.' + '\033[0m' + '\n')
                            sys.stderr.flush()
                    else:
                        llm_cascade = False

                    # Call OpenAI API to get an updated code
                    llm_response, tokens_used = self.llm_call(self.model_dict,messages,llm_cascade=llm_cascade)
                    code = self._extract_code(llm_response)
                    self.total_tokens_used.append(tokens_used)
                    

        # Get the output from the executed code
        answer = output.getvalue()

        # Call OpenAI API
        # Initialize the messages list with a system message containing the task prompt
        insights_messages = [{"role": "user", "content": self.solution_insights.format(task, answer)}]
        function_name = {"name": "Solution_Insights"}
        fn_name, arguments, tokens_used = self.llm_func_call(self.model_dict,insights_messages, self.insights_function, function_name)

        # Parse the JSON string to a Python dict
        arguments_dict = json.loads(arguments,strict=False)

        # Retrieve values
        answer = arguments_dict["insight"]

        self.total_tokens_used.append(tokens_used)
        total_tokens_used_sum = sum(self.total_tokens_used)

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return answer, code, total_tokens_used_sum
    
