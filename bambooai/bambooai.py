
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
#import google_search 

#Running as a package
from . import models
from . import prompts
from . import func_calls
from . import qa_retrieval
from . import google_search

class BambooAI:
    def __init__(self, df: pd.DataFrame,
                 max_conversations: int = 4,
                 llm: str = 'gpt-3.5-turbo-0613', # Base Model
                 debug: bool = False, 
                 vector_db: bool = False, 
                 search_tool: bool = False,
                 llm_switch: bool = False, 
                 exploratory: bool = True, 
                 ):

        # Check if the OPENAI_API_KEY environment variable is set
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
        
        # Check if the SERPER_API_KEY environment variable is set
        if not os.getenv('SERPER_API_KEY'):
            print("Warning: SERPER_API_KEY environment variable not found. Disabling google_search.")
            search_tool = False
        
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
        self.default_example_output_df = prompts.example_output_df
        self.default_example_output_gen = prompts.example_output_gen
        self.task_classification = prompts.task_classification
        self.analyst_selection = prompts.analyst_selection
        self.analyst_task_evaluation_gen = prompts.analyst_task_evaluation_gen
        self.analyst_task_evaluation_df = prompts.analyst_task_evaluation_df
        self.theorist_task_evaluation = prompts.theorist_task_evaluation
        self.researcher_task_evaluation = prompts.researcher_task_evaluation
        self.system_task_df = prompts.system_task_df
        self.system_task_gen = prompts.system_task_gen
        self.user_task_df = prompts.user_task_df
        self.user_task_gen = prompts.user_task_gen
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

        # Messages lists
        self.pre_eval_messages = []
        self.select_analyst_messages = []
        self.eval_messages = []
        self.code_messages = [{"role": "system", "content": self.system_task_df}]

        # QA Retrieval
        self.add_question_answer_pair = qa_retrieval.add_question_answer_pair
        self.retrieve_answer = qa_retrieval.retrieve_answer
        self.similarity_threshold = 0.8

        # Initialize the total tokens used list. This list will be used to keep track of the total tokens used by the models
        self.total_tokens_used = []

        # Google Search
        self.search_tool = search_tool
        self.google_search = google_search.GoogleSearch()

    #########################
    ### Output Sanitizing ###
    #########################

    # Function to sanitize the LLM response, and exctract the code.
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
    
    def _extract_expert(self,response: str) -> str:
        # Create a pattern to match any of the substrings
        pattern = r'Data Analyst|Data Analysis Theorist|Internet Research Specialist'
        
        # Use re.search to find the first match in the input string
        match = re.search(pattern, response)
        
        if match:
            # If a match is found, return it
            return match.group()
        else:
            # If no match is found, return None
            return None
        
    def _extract_analyst(self,response: str) -> str:
        # Create a pattern to match any of the substrings
        pattern = r'Data Analyst DF|Data Analyst Generic'
        
        # Use re.search to find the first match in the input string
        match = re.search(pattern, response)
        
        if match:
            # If a match is found, return it
            return match.group()
        else:
            # If no match is found, return None
            return None
    
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
    
    ######################
    ### Eval Functions ###
    ######################
    
    def task_eval(self, eval_messages):
        
        llm = self.model_dict['llm']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Trying to determine the best method to answer your question, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {llm}", "magenta"))
            cprint(f"\n>> Trying to determine the best method to answer your question, please wait...\n", 'magenta', attrs=['bold'])

        # Call OpenAI API to evaluate the task
        llm_response, tokens_used = self.llm_stream(self.model_dict, eval_messages)

        self.total_tokens_used.append(tokens_used)

        return llm_response
    
    def select_expert(self, pre_eval_messages):
        
        llm = self.model_dict['llm']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Selecting the expert to best answer your query, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {llm}", "magenta"))
            cprint(f"\n>> Selecting the expert to best answer your query, please wait..\n", 'magenta', attrs=['bold'])

        # Call OpenAI API to evaluate the task
        llm_response, tokens_used = self.llm_stream(self.model_dict, pre_eval_messages)
        selected_expert = self._extract_expert(llm_response)

        self.total_tokens_used.append(tokens_used)

        return selected_expert
    
    def select_analyst(self, select_analyst_messages):
        
        llm = self.model_dict['llm']

        # Call OpenAI API to evaluate the task
        llm_response, tokens_used = self.llm_stream(self.model_dict, select_analyst_messages)
        selected_analyst = self._extract_analyst(llm_response)

        self.total_tokens_used.append(tokens_used)

        return selected_analyst
    
    #####################
    ### Main Function ###
    #####################

    def pd_agent_converse(self, question=None):
        # Functions to display results nicely
        def display_results(answer, code, rank, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:     
                if answer is not None:
                    display(HTML(f'<p><b style="color:blue;">I now have the final answer:</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{answer}</pre></p><br>'))
                if code is not None:
                    display(HTML(f'<p><b style="color:blue;">Here is the final code that accomplishes the task:</b><br><pre style="color:#555555;">{code}</pre></p><br>'))
                if self.vector_db and rank is not None:
                    display(HTML(f'<p><b style="color:blue;">Solution Rank:</b><br><span style="color:black;">{rank}</span></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                if answer is not None:
                    cprint(f"\n>> I now have the final answer:\n{answer}\n", 'green', attrs=['bold'])
                if code is not None:
                    cprint(">> Here is the final code that accomplishes the task:", 'green', attrs=['bold'])
                    print(code)
                if self.vector_db and rank is not None:
                    cprint("\n>> Solution Rank:", 'green', attrs=['bold'])
                    print(rank)
                cprint(f"\n>> Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])

        def display_eval(total_tokens_used_sum,answer=None):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                if answer is not None:
                    print(answer)
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                # Other environment (like terminal)
                if answer is not None:
                    print(answer)
                cprint(f"\n>> Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])

        
        # Initialize the loop variable. If user provided question as an argument, the loop will finish after one iteration
        if question is not None:
            loop = False
        else:
            loop = True

        # Start the conversation loop
        while True:
            if loop:
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
                
            # Call the task_eval method with the user's question if the exploratory mode is True
            if self.exploratory is True:
                ######## Select Expert ###########
                self.pre_eval_messages.append({"role": "user", "content": self.task_classification.format(question)})
                selected_expert = self.select_expert(self.pre_eval_messages) 
                self.pre_eval_messages.append({"role": "assistant", "content": selected_expert})

                ######## Refine Expert Selection, and Formulate a task for the expert ###########
                if selected_expert == 'Data Analyst':
                    self.select_analyst_messages.append({"role": "user", "content": self.analyst_selection.format(question, self.df_columns)})
                    selected_analyst = self.select_analyst(self.select_analyst_messages)
                    if selected_analyst == 'Data Analyst DF':
                        self.eval_messages.append({"role": "user", "content": self.analyst_task_evaluation_df.format(question, self.df_head)})
                        # Replace first dict in messages with a new system task
                        self.code_messages[0] = {"role": "system", "content": self.system_task_df}
                    elif selected_analyst == 'Data Analyst Generic':
                        self.eval_messages.append({"role": "user", "content": self.analyst_task_evaluation_gen.format(question)})
                        # Replace first dict in messages with a new system task
                        self.code_messages[0] = {"role": "system", "content": self.system_task_gen}

                elif selected_expert == 'Data Analysis Theorist':
                    self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})
                elif selected_expert == 'Internet Research Specialist':
                    if self.search_tool:
                        self.eval_messages.append({"role": "user", "content": self.researcher_task_evaluation.format(question)})
                    else:
                        self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})
                else:
                    self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})

                task_eval = self.task_eval(self.eval_messages)
                self.eval_messages.append({"role": "assistant", "content": task_eval})

                # Remove the oldest conversation from the messages list
                if len(self.eval_messages) > self.MAX_CONVERSATIONS:
                    self.eval_messages.pop(0)
                    self.eval_messages.pop(0)

                total_tokens_used_sum = sum(self.total_tokens_used)

                if selected_expert == 'Data Analysis Theorist':                  
                    display_eval(total_tokens_used_sum)
                    if not loop:
                        return
                    continue
                elif selected_expert == 'Internet Research Specialist':
                    if self.search_tool:
                        print('I either do not have an answer to your query or I am not confident that the information that I have is satisfactory.\nI am going to search the Internet. Please wait...\n')
                        answer,links_dict,search_tokens = self.google_search(task_eval)
                        for link in links_dict:
                            print(f"Title: {link['title']}\nLink: {link['link']}\n")
                        # Replace the last element in eval_messages with the answer from the Google search
                        self.eval_messages[-1] = {"role": "assistant", "content": answer}
                        self.total_tokens_used.append(search_tokens)
                        total_tokens_used_sum = sum(self.total_tokens_used)
                        display_eval(total_tokens_used_sum,answer)
                    else:
                        display_eval(total_tokens_used_sum)
                    if not loop:
                        return
                    continue
                elif selected_expert == 'Data Analyst':
                    task = task_eval
                    display_eval(total_tokens_used_sum)
                else:
                    display_eval(total_tokens_used_sum)
                    if not loop:
                        return
                    continue
            else:
                task = question
            
            if self.vector_db:
                # Call the retrieve_answer method to check if the question has already been asked and answered
                if selected_analyst == 'Data Analyst DF':
                    df_columns = self.df_columns
                elif selected_analyst == 'Data Analyst Generic':
                    df_columns = ''

                example_output = self.retrieve_answer(task, df_columns, similarity_threshold=self.similarity_threshold)
                if example_output is not None:
                    example_output = example_output
                else:     
                    if selected_analyst == 'Data Analyst DF':
                        example_output = self.default_example_output_df
                    else:
                        example_output = self.default_example_output_gen
            else:
                if selected_analyst == 'Data Analyst DF':
                    example_output = self.default_example_output_df
                else:
                    example_output = self.default_example_output_gen

            # Call the generate_code() method to genarate and debug the code
            code = self.generate_code(selected_analyst, task, self.code_messages, example_output)
            # Call the execute_code() method to execute the code and summarise the results
            answer, results, code, total_tokens_used_sum = self.execute_code(code, task, self.code_messages)  
            
            # Remove the examples from the messages list to minimize the number of tokens used
            self.code_messages = self._remove_examples(self.code_messages)

            # Rank the LLM response
            if self.vector_db:
                # Switch to gpt-4 if llm_switch parameter is set to True. This will increase the processing time and cost
                if self.llm_switch:
                    llm_cascade = True
                else:
                    llm_cascade = False
                rank = self.rank_code(results, code,task,llm_cascade=llm_cascade)
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
                self.add_question_answer_pair(task, df_columns, code, rank)
            
            if not loop:
                return 
            
    ######################
    ### Code Functions ###
    ######################
            
    def generate_code(self, selected_analyst, task, code_messages, example_output):
        # Add a user message with the updated task prompt to the messages list
        if selected_analyst == 'Data Analyst DF':
            code_messages.append({"role": "user", "content": self.user_task_df.format(self.df_head, task, example_output)})
        elif selected_analyst == 'Data Analyst Generic':
            code_messages.append({"role": "user", "content": self.user_task_gen.format(task,example_output)})

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
        llm_response, tokens_used = self.llm_stream(self.model_dict, code_messages)
        code_messages.append({"role": "assistant", "content": llm_response})

        # Extract the code from the API response
        code = self._extract_code(llm_response)

        # Update the total tokens used
        self.total_tokens_used.append(tokens_used)

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

        return code
    
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

    def execute_code(self, code, task, code_messages):
        # Initialize error correction counter
        error_corrections = 0
        # Redirect standard output to a StringIO buffer
        with redirect_stdout(io.StringIO()) as output:
            # Try to execute the code and handle errors
            while error_corrections < self.MAX_ERROR_CORRECTIONS:
                try:
                    # Remove the oldest conversation from the messages list
                    if len(code_messages) > self.MAX_CONVERSATIONS:
                        code_messages.pop(1)
                        code_messages.pop(1)
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
                    code_messages.append({"role": "user", "content": self.error_correct_task.format(e)})

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
                    llm_response, tokens_used = self.llm_call(self.model_dict,code_messages,llm_cascade=llm_cascade)
                    code_messages.append({"role": "assistant", "content": llm_response})
                    code = self._extract_code(llm_response)
                    self.total_tokens_used.append(tokens_used)
                    
        # Get the output from the executed code
        results = output.getvalue()

        # I now need to add the answer to the messages list apending the answer to the content of the assistamt message.
        code_messages[-1]['content'] = code_messages[-1]['content'] + '\nResults:\n' + results

        # Call OpenAI API to summarize the results
        # Initialize the messages list with a system message containing the task prompt
        insights_messages = [{"role": "user", "content": self.solution_insights.format(task, results)}]
        summary, tokens_used = self.llm_call(self.model_dict,insights_messages)

        self.total_tokens_used.append(tokens_used)
        total_tokens_used_sum = sum(self.total_tokens_used)

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return summary, results, code, total_tokens_used_sum
    
    def rank_code(self,results, code,question,llm_cascade=False):
        # Initialize the messages list with a system message containing the task prompt
        rank_messages = [{"role": "system", "content": self.rank_answer.format(code,results,question)}]

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
