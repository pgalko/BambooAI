
import os
from contextlib import redirect_stdout
import io
import time
import pandas as pd
import warnings
import traceback
import sys
import json
warnings.filterwarnings('ignore')

try:
    # Attempt package-relative import
    from . import models, prompts, func_calls, qa_retrieval, google_search, reg_ex, log_manager, output_manager, utils
except ImportError:
    # Fall back to script-style import
    import models, prompts, func_calls, qa_retrieval, google_search, reg_ex, log_manager, output_manager, utils

class BambooAI:
    def __init__(self, df: pd.DataFrame = None,
                 max_conversations: int = 4,
                 debug: bool = False, 
                 vector_db: bool = False, 
                 search_tool: bool = False,
                 exploratory: bool = True,
                 ):
        
        # Output
        self.output_manager = output_manager.OutputManager()

        # Check if the OPENAI_API_KEY environment variable is set
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
        
        # Check if the SERPER_API_KEY environment variable is set
        if not os.getenv('SERPER_API_KEY'):
            self.output_manager.print_wrapper("Warning: SERPER_API_KEY environment variable not found. Disabling google_search.")
            search_tool = False
        
        # Check if the PINECONE_API_KEY and PINECONE_ENV environment variables are set if vector_db is True
        if vector_db:
            PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
            PINECONE_ENV = os.getenv('PINECONE_ENV')
            
            if PINECONE_API_KEY is None or PINECONE_ENV is None:
                self.output_manager.print_wrapper("Warning: PINECONE_API_KEY or PINECONE_ENV environment variable not found. Disabling vector_db.")
                vector_db = False

        self.MAX_ERROR_CORRECTIONS = 5
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1
        
        # Dataframe
        self.df = df if df is not None else None
        
        # Results of the code execution
        self.code_exec_results = None

        # Set the debug mode. This mode is True when you want the model to debug the code and correct it.
        self.debug = debug
        # Set the vector_db mode. This mode is True when you want the model to rank the generated code, and store the results above threshold in a vector database.
        self.vector_db = vector_db

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original user prompt and break it down in algorithm.
        self.exploratory = exploratory
        
        # Prompts
        # Define list of templates
        templates = [
            "default_example_output_df",
            "default_example_output_gen",
            "default_example_plan_df",
            "default_example_plan_gen",
            "expert_selector_system",
            "expert_selector_user",
            "analyst_selector_system",
            "analyst_selector_user",
            "planner_system",
            "planner_user_gen",
            "planner_user_df",
            "theorist_system",
            "google_search_query_generator_system",
            "google_search_react_system",
            "code_generator_system_df",
            "code_generator_system_gen",
            "code_generator_user_df",
            "code_generator_user_gen",
            "error_corector_system",
            "code_debugger_system",
            "code_ranker_system",
            "solution_summarizer_system"
        ]

        prompt_data = {}

        # Check if the JSON file exists
        if os.path.exists("PROMPT_TEMPLATES.json"):
            # Load from JSON file
            with open("PROMPT_TEMPLATES.json", "r") as f:
                prompt_data = json.load(f)

        # Set templates to the values from the JSON file or the default values. This dynamicaly sets the object attributes.
        # These attributes are part of the object's state and will exist as long as the object itself exists.
        # The attributes can be called using self.<attribute_name> throughout the class.
        for template in templates:
            value = prompt_data.get(template, getattr(prompts, template, ""))
            setattr(self, template, value)

        # Regular expresions
        self._extract_code = reg_ex._extract_code
        self._extract_rank = reg_ex._extract_rank
        self._extract_expert = reg_ex._extract_expert
        self._extract_analyst = reg_ex._extract_analyst
        self._extract_plan = reg_ex._extract_plan
        self._remove_examples = reg_ex._remove_examples

        # Functions
        self.task_eval_function = func_calls.task_eval_function
        self.insights_function = func_calls.solution_insights_function
        self.search_function = func_calls.search_function

        # LLM calls
        self.llm_call = models.llm_call
        self.llm_stream = models.llm_stream

        # Logging
        self.token_cost_dict = {
                                'gpt-3.5-turbo-0613': {'prompt_tokens': 0.0015, 'completion_tokens': 0.0020},
                                'gpt-3.5-turbo-1106': {'prompt_tokens': 0.0010, 'completion_tokens': 0.0020},
                                'gpt-3.5-turbo-instruct': {'prompt_tokens': 0.0015, 'completion_tokens': 0.0020},
                                'gpt-3.5-turbo-16k': {'prompt_tokens': 0.0030, 'completion_tokens': 0.0040},
                                'gpt-4': {'prompt_tokens': 0.03, 'completion_tokens': 0.06},
                                'gpt-4-1106-preview': {'prompt_tokens': 0.01, 'completion_tokens': 0.03},
                                'gpt-4-0613': {'prompt_tokens': 0.03, 'completion_tokens': 0.06}, 
                                'gpt-4-0125-preview': {'prompt_tokens': 0.01, 'completion_tokens': 0.03},
                                'gpt-4-turbo': {'prompt_tokens': 0.01, 'completion_tokens': 0.03},
                                'llama3-70b-8192': {'prompt_tokens': 0.00059, 'completion_tokens': 0.00079}, #Groq Llama3
                                'gemini-1.5-pro-latest': {'prompt_tokens': 0.0025, 'completion_tokens': 0.0025}, 
                                'claude-3-haiku-20240307': {'prompt_tokens': 0.00025, 'completion_tokens': 0.00079}, 
                                'claude-3-sonnet-20240229': {'prompt_tokens': 0.003, 'completion_tokens': 0.015},
                                'claude-3-opus-20240307': {'prompt_tokens': 0.015, 'completion_tokens': 0.075},
                                'mistral-small': {'prompt_tokens': 0.002, 'completion_tokens': 0.006},
                                'open-mixtral-8x22b': {'prompt_tokens': 0.002, 'completion_tokens': 0.006},
                                'mistral-large': {'prompt_tokens': 0.008, 'completion_tokens': 0.024},
                                }
        self.log_and_call_manager = log_manager.LogAndCallManager(self.token_cost_dict)
        self.chain_id = None

        # Messages lists
        self.pre_eval_messages = [{"role": "system", "content": self.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.planner_system.format(utils.get_readable_date())}]
        self.code_messages = [{"role": "system", "content": self.code_generator_system_df}]

        # QA Retrieval
        self.add_question_answer_pair = qa_retrieval.add_question_answer_pair
        self.retrieve_answer = qa_retrieval.retrieve_answer
        self.similarity_threshold = 0.8

        # Google Search
        self.search_tool = search_tool
        self.google_search = google_search.SmartSearchOrchestrator()

    ######################
    ### Util Functions ###
    ######################

    def reset_messages_and_logs(self):
        self.pre_eval_messages = [{"role": "system", "content": self.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.planner_system.format(utils.get_readable_date())}]
        self.code_messages = [{"role": "system", "content": self.code_generator_system_df}]
        self.code_exec_results = None

        self.log_and_call_manager.clear_run_logs()
    
    ######################
    ### Eval Functions ###
    ######################
    
    def select_expert(self, pre_eval_messages):
        '''Call the Expert Selector'''
        agent = 'Expert Selector'
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model)

        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,pre_eval_messages, agent=agent,chain_id=self.chain_id)
        expert, requires_dataset, confidence = self._extract_expert(llm_response)

        return expert, requires_dataset, confidence
    
    def select_analyst(self, select_analyst_messages):
        '''Call the Analyst Selector'''
        agent = 'Analyst Selector'
        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,select_analyst_messages, agent=agent, chain_id=self.chain_id)
        analyst, rephrased_query = self._extract_analyst(llm_response)

        return analyst, rephrased_query
    
    def task_eval(self, eval_messages, agent):
        '''Call the Task Evaluator'''
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model)

        if self.search_tool:
            tools=self.search_function
        else:
            tools=None

        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager,eval_messages, agent=agent, chain_id=self.chain_id, tools=tools)
        if agent == 'Planner':
            response = self._extract_plan(llm_response)
        else:
            response = llm_response
            
        return response
    
    def taskmaster(self, question, df_columns):
        '''Taskmaster function to select the expert, refine the expert selection, and formulate a task for the expert'''
        task = None
        analyst = None
        rephrased_query = None
        requires_dataset = None
        confidence = None

        ######## Select Expert ###########
        self.pre_eval_messages.append({"role": "user", "content": self.expert_selector_user.format(question)})
        expert,requires_dataset,confidence  = self.select_expert(self.pre_eval_messages) 
        self.pre_eval_messages.append({"role": "assistant", "content": f"expert:{expert},requires_dataset:{requires_dataset},confidence:{confidence}"})

        ######## Refine Expert Selection, and Formulate the task for the expert ###########
        if expert == 'Data Analyst':
            self.select_analyst_messages.append({"role": "user", "content": self.analyst_selector_user.format(question, None if self.df is None else df_columns)})
            analyst, rephrased_query = self.select_analyst(self.select_analyst_messages)
            self.select_analyst_messages.append({"role": "assistant", f"content": f"analyst:{analyst},rephrased_query:{rephrased_query}"})

            if analyst == 'Data Analyst DF':
                example_plan = self.default_example_plan_df
            elif analyst == 'Data Analyst Generic':
                example_plan = self.default_example_plan_gen

            # Retrieve the matching code and plan from the vector database if exists
            if self.vector_db:
                retrieved_code, retrieved_plan = self.retrieve_answer(rephrased_query, df_columns, similarity_threshold=self.similarity_threshold)

                if retrieved_plan is not None:
                    example_plan = f"Use the below plan as base for your answer:\n\n```yaml\n{retrieved_plan}\n```"

            if analyst == 'Data Analyst DF':
                self.eval_messages.append({"role": "user", "content": self.planner_user_df.format(None if self.df is None else self.df.dtypes.to_string(max_rows=None), example_plan, question)}) 
                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.code_messages[0] = {"role": "system", "content": self.code_generator_system_df}
            elif analyst == 'Data Analyst Generic':
                self.eval_messages.append({"role": "user", "content": self.planner_user_gen.format(example_plan, question)})
                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.code_messages[0] = {"role": "system", "content": self.code_generator_system_gen}
            agent = 'Planner'

        elif expert == 'Data Analysis Theorist':
            self.eval_messages.append({"role": "user", "content": self.theorist_system.format(question)})
            agent = 'Theorist'
        else:
            self.eval_messages.append({"role": "user", "content": self.theorist_system.format(question)})

        task_eval = self.task_eval(self.eval_messages, agent)
        self.eval_messages.append({"role": "assistant", "content": task_eval})

        # Remove the oldest conversation from the eval_messages list
        if len(self.eval_messages) > self.MAX_CONVERSATIONS:
            self.eval_messages.pop(1)
            self.eval_messages.pop(1)

        if expert == 'Data Analysis Theorist':
            self.log_and_call_manager.print_summary_to_terminal()
        elif expert == 'Data Analyst':
            task = task_eval
        else:
            self.log_and_call_manager.print_summary_to_terminal()

        return analyst, task, rephrased_query, requires_dataset, confidence
    
    #####################
    ### Main Function ###
    #####################

    def pd_agent_converse(self, question=None):
      
        # Initialize the loop variable. If user provided question as an argument, the loop will finish after one iteration
        if question is not None:
            loop = False
        else:
            loop = True

        # Set the chain id
        chain_id = int(time.time())
        self.chain_id = chain_id

        # Reset messages and logs
        self.reset_messages_and_logs()

        # Start the conversation loop
        while True:
            if loop:
                question = self.output_manager.display_user_input_prompt()
                # If the user types 'exit', break out of the loop
                if question.strip().lower() == 'exit':
                    self.log_and_call_manager.consolidate_logs()    
                    break
                
            if self.exploratory is True:
                # Call the taskmaister method with the user's question if the exploratory mode is True
                analyst, task, rephrased_query, requires_dataset, confidence = self.taskmaster(question,'' if self.df is None else self.df.columns.tolist())
                if not loop:
                    if not analyst:
                        self.log_and_call_manager.consolidate_logs()
                        return
                else:
                    if not analyst:
                        continue
            else:
                analyst = 'Data Analyst DF'
                task = question

            if analyst == 'Data Analyst DF':
                    example_code = self.default_example_output_df
            else:
                example_code = self.default_example_output_gen
            
            if self.vector_db:
                # Call the retrieve_answer method to check if the question has already been asked and answered
                retrieved_code, retrieved_plan = self.retrieve_answer(rephrased_query, '' if self.df is None else self.df.columns.tolist(), similarity_threshold=self.similarity_threshold)
                if retrieved_code is not None:
                    example_code = f"Review the the below code, and use as base for your answer:\n\n```python\n{retrieved_code}\n```"

            # Call the generate_code() method to genarate and debug the code
            code = self.generate_code(analyst, task, self.code_messages, example_code)
            # Call the execute_code() method to execute the code and summarise the results
            answer, results, code = self.execute_code(analyst,code, task, question, self.code_messages)

            # Rank the LLM response
            if self.vector_db:
                rank = self.rank_code(results, code,task)
            else:
                rank = ""

            # Display the results
            self.output_manager.display_results(df=self.df, answer=answer, code=code, rank=rank, vector_db=self.vector_db)

            if self.vector_db:
                rank_feedback = self.output_manager.display_user_input_rank()

                # If the user types "yes", use the rank as is. If not, use the user's rank.
                if rank_feedback.strip().lower() == 'yes':
                    rank = rank
                elif rank_feedback in map(str, range(0, 11)):
                    rank = rank_feedback
                else:
                    rank = rank

                # Add the question and answer pair to the QA retrieval index
                self.add_question_answer_pair(rephrased_query, task, '' if self.df is None else self.df.columns.tolist(), code, rank)

            self.log_and_call_manager.print_summary_to_terminal()
            
            if not loop:
                self.log_and_call_manager.consolidate_logs()
                return 
            
    ######################
    ### Code Functions ###
    ######################
            
    def generate_code(self, analyst, task, code_messages, example_code):
        agent = 'Code Generator'
        # Add a user message with the updated task prompt to the messages list
        if analyst == 'Data Analyst DF':
            code_messages.append({"role": "user", "content": self.code_generator_user_df.format(None if self.df is None else self.df.dtypes.to_string(max_rows=None), task, self.code_exec_results, example_code)})
        elif analyst == 'Data Analyst Generic':
            code_messages.append({"role": "user", "content": self.code_generator_user_gen.format(task, self.code_exec_results, example_code)})

        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model)

        # Call the OpenAI API or a local code model
        llm_response = self.llm_stream(self.log_and_call_manager,code_messages, agent=agent, chain_id=self.chain_id)
        code_messages.append({"role": "assistant", "content": llm_response})

        # Extract the code from the API response
        code = self._extract_code(llm_response,analyst,provider)

        # Debug code if debug parameter is set to True
        if self.debug:
            code = self.debug_code(analyst, code, task)
        else:
            self.output_manager.display_tool_end(agent)

        return code
    
    def debug_code(self,analyst,code,question):
        agent = 'Code Debugger'
        # Initialize the messages list with a system message containing the task prompt
        debug_messages = [{"role": "user", "content": self.code_debugger_system.format(code,question)}]
        
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model)

        # Call the OpenAI API
        llm_response = self.llm_stream(self.log_and_call_manager, debug_messages, agent=agent, chain_id=self.chain_id)
        
        # Extract the code from the API response
        debugged_code = self._extract_code(llm_response,analyst,provider)       
        self.output_manager.display_tool_end(agent)

        return debugged_code

    def execute_code(self, analyst, code, task, original_question, code_messages):
        agent = 'Code Executor'
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
                except Exception as error:
                    # Capture the full traceback
                    exc_type, exc_value, tb = sys.exc_info()
                    full_traceback = traceback.format_exc()
                    # Filter the traceback
                    exec_traceback = self.filter_exec_traceback(full_traceback, exc_type.__name__, str(exc_value)) 

                    # Increment the error corrections counter
                    error_corrections += 1

                    # Reset df to the original state before trying again
                    if self.df is not None:
                        self.df = original_df.copy()

                    code, code_messages = self.correct_code_errors(exec_traceback, error_corrections, code_messages, analyst)
              
        # Get the output from the executed code
        results = output.getvalue()
        
        # Store the results in a class variable so it can be appended to the subsequent messages list
        self.code_exec_results = results

        summary = self.summarise_solution(task, original_question, results)

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return summary, results, code
    
    def filter_exec_traceback(self, full_traceback, exception_type, exception_value):
        # Split the full traceback into lines and filter those that originate from "<string>"
        filtered_tb_lines = [line for line in full_traceback.split('\n') if '<string>' in line]

        # Combine the filtered lines and append the exception type and message
        filtered_traceback = '\n'.join(filtered_tb_lines)
        if filtered_traceback:  # Add a newline only if there's a traceback to show
            filtered_traceback += '\n'
        filtered_traceback += f"{exception_type}: {exception_value}"

        return filtered_traceback
    
    def correct_code_errors(self, error, error_corrections, code_messages, analyst):
        agent = 'Error Corrector'

        model,provider = models.get_model_name(agent)

        #If error correction is greater than 2 remove the first error correction
        if error_corrections > 2:
            del code_messages[-4] 
            del code_messages[-3]
        
        # Append the error message to the messages list
        code_messages.append({"role": "user", "content": self.error_corector_system.format(error)})

        # Display the error message
        self.output_manager.display_error(error)

        llm_response = self.llm_call(self.log_and_call_manager,code_messages,agent=agent, chain_id=self.chain_id)
        code_messages.append({"role": "assistant", "content": llm_response})
        code = self._extract_code(llm_response,analyst,provider)

        return code, code_messages

    def rank_code(self,results, code,question):
        agent = 'Code Ranker'
        # Initialize the messages list with a user message containing the task prompt
        rank_messages = [{"role": "user", "content": self.code_ranker_system.format(code,results,question)}]

        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model)

        # Call the OpenAI API 
        llm_response = self.llm_call(self.log_and_call_manager,rank_messages,agent=agent, chain_id=self.chain_id)

        # Extract the rank from the API response
        rank = self._extract_rank(llm_response)       

        return rank
    
    ############################
    ## Summarise the solution ##
    ############################

    def summarise_solution(self, task, original_question, results):
        agent = 'Solution Summarizer'

        # Initialize the messages list with a user message containing the task prompt
        insights_messages = [{"role": "user", "content": self.solution_summarizer_system.format(original_question, task, results)}]
        # Call the OpenAI API
        summary = self.llm_call(self.log_and_call_manager,insights_messages,agent=agent, chain_id=self.chain_id)

        return summary