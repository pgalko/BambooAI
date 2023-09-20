
import os
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

try:
    # Attempt package-relative import
    from . import models, prompts, func_calls, qa_retrieval, google_search, reg_ex
except ImportError:
    # Fall back to script-style import
    import models, prompts, func_calls, qa_retrieval, google_search, reg_ex

class BambooAI:
    def __init__(self, df: pd.DataFrame = None,
                 max_conversations: int = 4,
                 llm: str = 'gpt-3.5-turbo-0613', # Base Model
                 debug: bool = False, 
                 vector_db: bool = False, 
                 search_tool: bool = False,
                 llm_switch_plan: bool = False,
                 llm_switch_code: bool = False, 
                 exploratory: bool = True,
                 local_code_model: str = None 
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
        
        # Dataframe
        self.df = df if df is not None else None

        # LLMs
        # OpenAI models model dict
        self.model_dict = {"llm": llm,
                           "llm_gpt4": "gpt-4-0613",
                           "llm_16k": "gpt-3.5-turbo-16k",
                           "llm_func": "gpt-3.5-turbo-0613",}
        # Local models
        self.local_code_model = local_code_model

        # Set the debug mode. This mode is True when you want the model to debug the code and correct it.
        self.debug = debug
        # Set the llm_switch_plan mode. This mode is True when you want the model to switch to gpt-4 for planning tasks (task_eval, select_expert, select_analyst).
        self.llm_switch_plan = llm_switch_plan
        # Set the llm_switch_code mode. This mode is True when you want the model to switch to gpt-4 for coding tasks (debugg, error correction, ranking).
        self.llm_switch_code = llm_switch_code
        # Set the vector_db mode. This mode is True when you want the model to rank the generated code, and store the results above threshold in a vector database.
        self.vector_db = vector_db

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original user prompt and break it down in algorithm.
        self.exploratory = exploratory
        
        # Prompts
        self.default_example_output_df = prompts.example_output_df
        self.default_example_output_gen = prompts.example_output_gen
        self.system_task_classification = prompts.system_task_classification
        self.user_task_classification = prompts.user_task_classification
        self.system_analyst_selection = prompts.system_analyst_selection
        self.user_analyst_selection = prompts.user_analyst_selection
        self.system_task_evaluation = prompts.system_task_evaluation
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

        # Regular expresions
        self._extract_code = reg_ex._extract_code
        self._extract_rank = reg_ex._extract_rank
        self._extract_expert = reg_ex._extract_expert
        self._extract_analyst = reg_ex._extract_analyst
        self._remove_examples = reg_ex._remove_examples

        # Functions
        self.task_eval_function = func_calls.task_eval_function
        self.insights_function = func_calls.solution_insights_function

        # LLM calls
        self.llm_call = models.llm_call
        self.llm_func_call = models.llm_func_call
        self.llm_stream = models.llm_stream

        # Logging
        self.token_cost_dict = {
                                'gpt-3.5-turbo-0613': {'prompt_tokens': 0.0015, 'completion_tokens': 0.0020},
                                'gpt-3.5-turbo-16k': {'prompt_tokens': 0.0030, 'completion_tokens': 0.0040},
                                'gpt-4-0613': {'prompt_tokens': 0.03, 'completion_tokens': 0.06}  
                                }
        self.log_and_call_manager = models.LogAndCallManager(self.token_cost_dict)
        self.chain_id = None

        # Messages lists
        self.pre_eval_messages = [{"role": "system", "content": self.system_task_classification}]
        self.select_analyst_messages = [{"role": "system", "content": self.system_analyst_selection}]
        self.eval_messages = [{"role": "system", "content": self.system_task_evaluation}]
        self.code_messages = [{"role": "system", "content": self.system_task_df}]

        # QA Retrieval
        self.add_question_answer_pair = qa_retrieval.add_question_answer_pair
        self.retrieve_answer = qa_retrieval.retrieve_answer
        self.similarity_threshold = 0.8

        # Google Search
        self.search_tool = search_tool
        self.google_search = google_search.GoogleSearch()

    
    ######################
    ### Eval Functions ###
    ######################
    
    def task_eval(self, eval_messages, llm_cascade_plan=False):
        tool = 'Planner'
        using_model = self.model_dict['llm']
        if llm_cascade_plan:
            using_model = self.model_dict['llm_gpt4']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {using_model}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Trying to determine the best method to answer your question, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {using_model}", "magenta"))
            cprint(f"\n>> Trying to determine the best method to answer your question, please wait...\n", 'magenta', attrs=['bold'])

        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,self.model_dict, eval_messages, llm_cascade=llm_cascade_plan,tool=tool, chain_id=self.chain_id)

        return llm_response
    
    def select_expert(self, pre_eval_messages, llm_cascade_plan=False):
        tool = 'Expert Selector'
        using_model = self.model_dict['llm']
        if llm_cascade_plan:
            using_model = self.model_dict['llm_gpt4']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {using_model}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Selecting the expert to best answer your query, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {using_model}", "magenta"))
            cprint(f"\n>> Selecting the expert to best answer your query, please wait..\n", 'magenta', attrs=['bold'])

        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,self.model_dict, pre_eval_messages, llm_cascade=llm_cascade_plan, tool=tool,chain_id=self.chain_id)
        expert = self._extract_expert(llm_response)

        return expert
    
    def select_analyst(self, select_analyst_messages, llm_cascade_plan=False):
        tool = 'Analyst Selector'
        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,self.model_dict, select_analyst_messages, llm_cascade=llm_cascade_plan, tool=tool, chain_id=self.chain_id)
        analyst = self._extract_analyst(llm_response)

        return analyst
    
    def taskmaster(self, question):
        task = None
        analyst = None

        # Switch to gpt-4 if llm_switch_plan parameter is set to True. This will increase the processing time and cost
        if self.llm_switch_plan:
            llm_cascade_plan = True
        else:
            llm_cascade_plan = False

        def display_eval(answer=None):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                if answer is not None:
                    print(answer)
            else:
                # Other environment (like terminal)
                if answer is not None:
                    print(answer)

        ######## Select Expert ###########
        self.pre_eval_messages.append({"role": "user", "content": self.user_task_classification.format(question)})
        expert = self.select_expert(self.pre_eval_messages,llm_cascade_plan=llm_cascade_plan) 
        self.pre_eval_messages.append({"role": "assistant", "content": expert})

        ######## Refine Expert Selection, and Formulate a task for the expert ###########
        if expert == 'Data Analyst':
            self.select_analyst_messages.append({"role": "user", "content": self.user_analyst_selection.format(question, None if self.df is None else self.df.columns.tolist())})
            analyst = self.select_analyst(self.select_analyst_messages, llm_cascade_plan=llm_cascade_plan)
            if analyst == 'Data Analyst DF':
                self.eval_messages.append({"role": "user", "content": self.analyst_task_evaluation_df.format(question, None if self.df is None else self.df.head(1))})
                # Replace first dict in messages with a new system task
                self.code_messages[0] = {"role": "system", "content": self.system_task_df}
            elif analyst == 'Data Analyst Generic':
                self.eval_messages.append({"role": "user", "content": self.analyst_task_evaluation_gen.format(question)})
                # Replace first dict in messages with a new system task
                self.code_messages[0] = {"role": "system", "content": self.system_task_gen}

        elif expert == 'Data Analysis Theorist':
            self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})
        elif expert == 'Internet Research Specialist':
            if self.search_tool:
                self.eval_messages.append({"role": "user", "content": self.researcher_task_evaluation.format(question)})
            else:
                self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})
        else:
            self.eval_messages.append({"role": "user", "content": self.theorist_task_evaluation.format(question)})

        task_eval = self.task_eval(self.eval_messages, llm_cascade_plan=llm_cascade_plan)
        self.eval_messages.append({"role": "assistant", "content": task_eval})

        # Remove the oldest conversation from the messages list
        if len(self.eval_messages) > self.MAX_CONVERSATIONS:
            self.eval_messages.pop(1)
            self.eval_messages.pop(1)

        if expert == 'Data Analysis Theorist':
            self.log_and_call_manager.print_summary_to_terminal()

        elif expert == 'Internet Research Specialist':
            if self.search_tool:
                print('I either do not have an answer to your query or I am not confident that the information that I have is satisfactory.\nI am going to search the Internet. Please wait...\n')
                answer,links_dict = self.google_search(self.token_cost_dict,self.model_dict,self.chain_id,task_eval)
                for link in links_dict:
                    print(f"Title: {link['title']}\nLink: {link['link']}\n")
                # Replace the last element in eval_messages with the answer from the Google search
                self.eval_messages[-1] = {"role": "assistant", "content": answer}
                display_eval(answer)
                self.log_and_call_manager.print_summary_to_terminal()
            else:
                self.log_and_call_manager.print_summary_to_terminal()

        elif expert == 'Data Analyst':
            task = task_eval
        else:
            self.log_and_call_manager.print_summary_to_terminal()

        return analyst,task
    
    #####################
    ### Main Function ###
    #####################

    def pd_agent_converse(self, question=None):
        # Functions to display results nicely
        def display_results(answer, code, rank):
            if 'ipykernel' in sys.modules: 
                if self.df is not None:
                    display(HTML(f'<p><b style="color:blue;">Here is the head of your dataframe:</b><br><pre style="color:#555555;">{self.df.head(5)}</pre></p><br>'))    
                if answer is not None:
                    display(HTML(f'<p><b style="color:blue;">I now have the final answer:</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{answer}</pre></p><br>'))
                if code is not None:
                    display(HTML(f'<p><b style="color:blue;">Here is the final code that accomplishes the task:</b><br><pre style="color:#555555;">{code}</pre></p><br>'))
                if self.vector_db and rank is not None:
                    display(HTML(f'<p><b style="color:blue;">Solution Rank:</b><br><span style="color:black;">{rank}</span></p><br>'))
            else:
                if self.df is not None:
                    cprint(f"\n>> Here is the head of your dataframe:", 'green', attrs=['bold'])
                    display(self.df.head(5))
                if answer is not None:
                    cprint(f"\n>> I now have the final answer:\n{answer}\n", 'green', attrs=['bold'])
                if code is not None:
                    cprint(">> Here is the final code that accomplishes the task:", 'green', attrs=['bold'])
                    print(code)
                if self.vector_db and rank is not None:
                    cprint("\n>> Solution Rank:", 'green', attrs=['bold'])
                    print(rank)
      
        # Initialize the loop variable. If user provided question as an argument, the loop will finish after one iteration
        if question is not None:
            loop = False
        else:
            loop = True

        # Set the chain id
        chain_id = int(time.time())
        self.chain_id = chain_id

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
                    self.log_and_call_manager.write_summary_to_log()
                    break
                
            if self.exploratory is True:
                # Call the taskmaister method with the user's question if the exploratory mode is True
                analyst,task = self.taskmaster(question)
                if not loop:
                    if not analyst:
                        return
                else:
                    if not analyst:
                        continue
            else:
                analyst = 'Data Analyst DF'
                task = question
            
            if self.vector_db:
                # Call the retrieve_answer method to check if the question has already been asked and answered
                if analyst == 'Data Analyst DF':
                    df_columns = '' if self.df is None else self.df.columns.tolist()
                elif analyst == 'Data Analyst Generic':
                    df_columns = ''

                example_output = self.retrieve_answer(task, df_columns, similarity_threshold=self.similarity_threshold)
                if example_output is not None:
                    example_output = example_output
                else:     
                    if analyst == 'Data Analyst DF':
                        example_output = self.default_example_output_df
                    else:
                        example_output = self.default_example_output_gen
            else:
                if analyst == 'Data Analyst DF':
                    example_output = self.default_example_output_df
                else:
                    example_output = self.default_example_output_gen

            # Call the generate_code() method to genarate and debug the code
            code = self.generate_code(analyst, task, self.code_messages, example_output)
            # Call the execute_code() method to execute the code and summarise the results
            answer, results, code = self.execute_code(analyst,code, task, self.code_messages)

            # Rank the LLM response
            if self.vector_db:
                # Switch to gpt-4 if llm_switch_code parameter is set to True. This will increase the processing time and cost
                if self.llm_switch_code:
                    llm_cascade_code = True
                else:
                    llm_cascade_code = False
                rank = self.rank_code(results, code,task,llm_cascade_code=llm_cascade_code)
            else:
                rank = ""

            display_results(answer, code, rank)

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

            self.log_and_call_manager.print_summary_to_terminal()
            
            if not loop:
                self.log_and_call_manager.write_summary_to_log()
                return 
            
    ######################
    ### Code Functions ###
    ######################
            
    def generate_code(self, analyst, task, code_messages, example_output):
        tool = 'Code Generator'
        # Add a user message with the updated task prompt to the messages list
        if analyst == 'Data Analyst DF':
            code_messages.append({"role": "user", "content": self.user_task_df.format(None if self.df is None else self.df.head(1), task, example_output)})
        elif analyst == 'Data Analyst Generic':
            code_messages.append({"role": "user", "content": self.user_task_gen.format(task,example_output)})

        if self.local_code_model:
            using_model = self.local_code_model
        else:
            using_model = self.model_dict['llm']

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {using_model}</p>'))
            display(HTML(f'<p><b style="color:magenta;">I am generating the first version of the code, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n>> Calling Model: {using_model}", "magenta"))
            cprint(f"\n>> I am generating the first version of the code, please wait\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API or a local code model
        llm_response = self.llm_stream(self.log_and_call_manager,self.model_dict, code_messages, local_model=self.local_code_model, tool=tool, chain_id=self.chain_id)
        code_messages.append({"role": "assistant", "content": llm_response})

        # Extract the code from the API response
        code = self._extract_code(llm_response,analyst,local_model=self.local_code_model)

        # Debug code if debug parameter is set to True
        if self.debug:
            # Switch to gpt-4 if llm_switch_code parameter is set to True. This will increase the processing time and cost
            if self.llm_switch_code:
                llm_cascade_code = True
                if 'ipykernel' in sys.modules:
                    # Jupyter notebook
                    display(HTML('<span style="color: magenta;">Switching model to gpt-4 to debug the code.</span>'))
                else:
                    # CLI
                    print(colored("\n>> Switching model to GPT-4 to debug the code.", "magenta"))
            else:
                llm_cascade_code = False
            code = self.debug_code(analyst, code, task, llm_cascade_code=llm_cascade_code)

        return code
    
    def debug_code(self,analyst,code,question, llm_cascade_code=False):
        tool = 'Code Debugger'
        # Initialize the messages list with a system message containing the task prompt
        debug_messages = [{"role": "user", "content": self.debug_code_task.format(code,question)}]
        
        if self.local_code_model:
            using_model = self.local_code_model
        else:
            using_model = self.model_dict['llm']
        if llm_cascade_code:
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
        llm_response = self.llm_stream(self.log_and_call_manager,self.model_dict, debug_messages,temperature=0, llm_cascade=llm_cascade_code, local_model=self.local_code_model, tool=tool, chain_id=self.chain_id)
        
        # Extract the code from the API response
        debugged_code = self._extract_code(llm_response,analyst)       
        display_task()

        return debugged_code

    def execute_code(self, analyst, code, task, code_messages):
        # Initialize error correction counter
        error_corrections = 0

        # Create a copy of the original self.df
        if self.df is not None:
            original_df = self.df.copy()

        # Redirect standard output to a StringIO buffer
        with redirect_stdout(io.StringIO()) as output:
            # Try to execute the code and handle errors
            while error_corrections < self.MAX_ERROR_CORRECTIONS:
                try:
                    # Remove the oldest conversation from the messages list
                    if len(code_messages) > self.MAX_CONVERSATIONS:
                        code_messages.pop(1)
                        code_messages.pop(1)

                    # Execute the code
                    if code is not None:
                        exec(code, {'df': self.df})
                        # Remove examples from the messages list to minimize the number of tokens used
                        self.code_messages = self._remove_examples(self.code_messages)
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
                    #If error correction is greater than 2 remove the first error correction
                    if error_corrections > 2:
                        del code_messages[-4] 
                        del code_messages[-3]

                    code_messages.append({"role": "user", "content": self.error_correct_task.format(e)})

                    # Switch to gpt-4 if llm_switch_code parameter is set to True. This will increase the processing time and cost.
                    if self.llm_switch_code:
                        llm_cascade_code = True
                        if 'ipykernel' in sys.modules:
                            # Jupyter notebook
                            display(HTML('<span style="color: #d86c00;">Switching model to gpt-4 to try to improve the outcome.</span>'))
                        else:
                            # CLI
                            sys.stderr.write('\033[31m' + f'>> Switching model to gpt-4 to try to improve the outcome.' + '\033[0m' + '\n')
                            sys.stderr.flush()
                    else:
                        llm_cascade_code = False

                    # Reset df to the original state before trying again
                    if self.df is not None:
                        self.df = original_df.copy()

                    # Call OpenAI API to get an updated code
                    tool = 'Error Corrector'
                    llm_response = self.llm_call(self.log_and_call_manager,self.model_dict,code_messages,llm_cascade=llm_cascade_code, tool=tool, chain_id=self.chain_id)
                    code_messages.append({"role": "assistant", "content": llm_response})
                    code = self._extract_code(llm_response,analyst)
                    
        # Get the output from the executed code
        results = output.getvalue()

        # I now need to add the answer to the messages list apending the answer to the content of the assistamt message.
        code_messages[-1]['content'] = code_messages[-1]['content'] + '\nThe execution of this code resulted in the following:\n' + results

        # Call OpenAI API to summarize the results
        tool = 'Solution Summarizer'
        # Initialize the messages list with a system message containing the task prompt
        insights_messages = [{"role": "user", "content": self.solution_insights.format(task, results)}]
        summary = self.llm_call(self.log_and_call_manager,self.model_dict,insights_messages,tool=tool, chain_id=self.chain_id)

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return summary, results, code
    
    def rank_code(self,results, code,question,llm_cascade_code=False):
        tool = 'Code Ranker'
        # Initialize the messages list with a system message containing the task prompt
        rank_messages = [{"role": "system", "content": self.rank_answer.format(code,results,question)}]

        using_model = self.model_dict['llm']
        if llm_cascade_code:
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
        llm_response = self.llm_call(self.log_and_call_manager,self.model_dict, rank_messages,llm_cascade=llm_cascade_code,tool=tool, chain_id=self.chain_id)

        # Extract the rank from the API response
        rank = self._extract_rank(llm_response)       

        return rank