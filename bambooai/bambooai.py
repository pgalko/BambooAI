
import os
import time
import uuid
import pandas as pd
import warnings
import json
warnings.filterwarnings('ignore')

try:
    # Attempt package-relative import
    from . import code_executor, models, prompts, template_formatting, func_calls, qa_retrieval, reg_ex, log_manager, output_manager, web_output_manager, storage_manager, utils, executor_client
except ImportError:
    # Fall back to script-style import
    import code_executor, models, prompts, template_formatting, func_calls, qa_retrieval, reg_ex, log_manager, output_manager, web_output_manager, storage_manager, utils, executor_client

class BambooAI:
    def __init__(self, df: pd.DataFrame = None,
                 max_conversations: int = 4,
                 vector_db: bool = False, 
                 search_tool: bool = False,
                 exploratory: bool = True,
                 df_ontology: str = None,
                 planning: bool = False,
                 webui: bool = False,
                 df_id: str = None
                 ):
        
        # Thread and chain identifiers
        self.thread_id = None
        self.chain_id = None
        
        # Output
        self.output_manager = web_output_manager.WebOutputManager() if webui else output_manager.OutputManager()
        self.webui = webui

        # Code execution and API client
        self.execution_mode = os.getenv('EXECUTION_MODE', 'local')
        self.executor_api_url = os.getenv('EXECUTOR_API_BASE_URL', None)
        self.api_client = executor_client.ExecutorAPIClient(base_url=self.executor_api_url)
        self.executor = code_executor.CodeExecutor(webui=self.webui, 
                                                   mode=self.execution_mode,
                                                   api_client=self.api_client)

        # Web search mode
        self.search_mode = os.getenv('WEB_SEARCH_MODE', 'google_ai')

        # Storage
        try:
            self.interaction_store = storage_manager.SimpleInteractionStore()
        except storage_manager.StorageError as e:
            self.output_manager.print_wrapper(f"Warning: Failed to initialize interaction store: {e}")
            self.interaction_store = None

        # Check if the OPENAI_API_KEY environment variable is set
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
        
        # Check if search tool requirements are met
        def validate_search_tool(self, search_tool, search_mode):
            if not search_tool:
                return False
                
            if search_mode == 'google_ai':
                if not os.getenv('GEMINI_API_KEY'):
                    self.output_manager.print_wrapper(
                        "Warning: GEMINI_API_KEY environment variable not found. Disabling google_search.", 
                        chain_id=self.chain_id
                    )
                    return False
                    
            elif search_mode == 'selenium':
                if not os.getenv('SERPER_API_KEY'):
                    self.output_manager.print_wrapper(
                        "Warning: SERPER_API_KEY environment variable not found. Disabling google_search.", 
                        chain_id=self.chain_id
                    )
                    return False
                    
            return True
        
        # Validate search tool
        search_tool = validate_search_tool(self, search_tool, self.search_mode)
        
        # Check if the PINECONE_API_KEY and PINECONE_ENV environment variables are set if vector_db is True
        if vector_db:
            PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
            
            if PINECONE_API_KEY is None:
                self.output_manager.print_wrapper("Warning: PINECONE_API_KEY or PINECONE_ENV environment variable not found. Disabling vector_db.", chain_id=self.chain_id)
                vector_db = False

        self.MAX_ERROR_CORRECTIONS = 5
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1
        
        # Dataframe

        # Check if the dataframe is provided and generate a unique ID if not provided
        if df is not None and not df_id:
            df_id = str(uuid.uuid4())

        self.df = df if df is not None else None
        self.original_df_columns = utils.get_dataframe_columns(df, self.execution_mode, df_id, self.api_client) if df_id is not None else None
        self.df_ontology = df_ontology # Set the df_ontology mode. The argument takes the path to the ontology file.
        self.data_model = None # Stores details retrieved from the ontology
        self.df_id = df_id

        # User intent
        self.user_intent = None
        
        # Results of the code execution
        self.code_exec_results = None

        # QA Pairs (a list of dictionaries containing "question/results of the code execution" pairs)
        self.qa_pairs = []
        
        # Tasks (a list of task)
        self.tasks = []

        # Last generated code
        self.last_code = None

        # Last generated plan
        self.last_plan = None

        # Set the vector_db mode. This mode is True when you want the model to rank the generated code, and store the results above threshold in a vector database.
        self.vector_db = vector_db

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original user prompt and break it down in algorithm.
        self.exploratory = exploratory

        # Set the planning mode. This mode is True when you want the model to generate a plan for the solution.
        self.planning = planning

        # Set the pandas, python and plotly versions
        versions = utils.get_package_versions()
        self.pandas_version = versions['pandas_version']
        self.python_version = versions['python_version']
        self.plotly_version = versions['plotly_version']
        
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
            "planner_user_gen_reasoning",
            "planner_user_df_reasoning",
            "theorist_system",
            "dataframe_inspector_system",
            "dataframe_inspector_user",
            "google_search_query_generator_system",
            "google_search_react_system",
            "code_generator_system_df",
            "code_generator_system_gen",
            "code_generator_user_df_plan",
            "code_generator_user_df_no_plan",
            "code_generator_user_gen_plan",
            "code_generator_user_gen_no_plan",
            "error_corector_system",
            "error_corector_system_reasoning",
            "error_corector_edited_system",
            "error_corector_edited_system_reasoning",
            "reviewer_system",
            "solution_summarizer_system",
            "solution_summarizer_custom_code_system",
            "plot_query",
            "plot_query_routing"
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
        self._extract_data_model = reg_ex._extract_data_model
        self._remove_examples = reg_ex._remove_examples
        self._remove_all_except_task_text = reg_ex._remove_all_except_task_text
        self._remove_all_except_task_xml = reg_ex._remove_all_except_task_xml
        self._remove_all_except_task_ontology_text = reg_ex._remove_all_except_task_ontology_text

        # Functions
        self.openai_tools_definition = func_calls.openai_tools_definition
        self.anthropic_tools_definition = func_calls.anthropic_tools_definition
        self.gemini_tools_definition = func_calls.gemini_tools_definition

        # LLM calls
        self.llm_call = models.llm_call
        self.llm_stream = models.llm_stream

        # Model dictionary containing model capabilities, template formatting and tokens cost
        self.model_dict = models.get_model_properties()
        
        self.log_and_call_manager = log_manager.LogAndCallManager(self.model_dict)

        # Model capabilities
        self.reasoning_models = [
            model_name 
            for model_name, model_info in self.model_dict.items() 
            if model_info['capability'] == 'reasoning'
        ]

        self.multimodal_models = [
            model_name
            for model_name, model_info in self.model_dict.items()
            if model_info['multimodal'] == 'true'
        ]


        # Messages lists
        self.pre_eval_messages = [{"role": "system", "content": self.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.planner_system}]
        self.code_messages = [{"role": "system", "content": self.code_generator_system_df}]
        self.df_inspector_messages = [{"role": "system", "content": self.dataframe_inspector_system}]
        self.plan_review_messages = None
        self.insight_messages = None

        # QA Retrieval
        self.pinecone_wrapper = qa_retrieval.PineconeWrapper(output_manager=self.output_manager)
        self.similarity_threshold = 0.80
        self.retrieved_data_model = None
        self.retrieved_plan = None
        self.retrieved_code = None

        # Google Search
        self.search_tool = search_tool

        # Auxiliary datasets. This flag is set to True when the user wants to use an auxiliary dataset to provide additional context to the main dataset.
        self.auxiliary_dataset = False

        # Request user feedback during the conversation
        self.user_feedback = True

        # Templates formatting
        code_gen_templates = [
            'code_generator_user_df_plan',
            'code_generator_user_df_no_plan', 
            'code_generator_user_gen_plan',
            'code_generator_user_gen_no_plan'
        ]
        code_gen_template_dict = {name: getattr(self, name) for name in code_gen_templates}
        self.code_gen_prompt_generator = template_formatting.CodeGenPromptGenerator(code_gen_template_dict, self.model_dict)


    ######################
    ### Util Functions ###
    ######################

    def reset_messages_and_logs(self):
        self.pre_eval_messages = [{"role": "system", "content": self.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.planner_system}]
        self.code_messages = [{"role": "system", "content": self.code_generator_system_df}]
        self.df_inspector_messages = [{"role": "system", "content": self.dataframe_inspector_system}]
        self.code_exec_results = None

        self.log_and_call_manager.clear_run_logs()

    def reset_non_cumul_messages(self):
        self.plan_review_messages = None
        self.insight_messages = None

    def reset_retrieved_data(self):
        self.retrieved_data_model = None
        self.retrieved_plan = None
        self.retrieved_code = None

    def messages_maintenace(self, messages):
        # Remove tool_calls messages from the messages list
        for i in range(len(messages) - 1, -1, -1):  # Start from the last item to index 0
            msg = messages[i]
            if "tool_calls" in msg or msg.get("role") == "tool":
                messages.pop(i)
        # Remove the oldest conversation from the messages list
        if len(messages) > self.MAX_CONVERSATIONS:
            messages.pop(1)
            messages.pop(1)
            self.output_manager.display_system_messages("Truncating messages")

    def filter_tools(self, tools_list, search_enabled=False, auxiliary_enabled=False, feedback_enabled=False):
        filtered_tools = tools_list.copy()  # Create a copy to avoid modifying original list
        
        def get_tool_name(tool):
            # Handle direct name (anthropic/gemini style)
            if "name" in tool:
                return tool["name"]
            # Handle nested name (openai style)
            if "function" in tool and "name" in tool["function"]:
                return tool["function"]["name"]
            return None
        
        # Remove tools based on flags
        if not search_enabled:
            filtered_tools = [tool for tool in filtered_tools if get_tool_name(tool) != "google_search"]
        
        if not auxiliary_enabled:
            filtered_tools = [tool for tool in filtered_tools if get_tool_name(tool) != "get_auxiliary_dataset"]
            
        if not feedback_enabled:
            filtered_tools = [tool for tool in filtered_tools if get_tool_name(tool) != "request_user_context"]
        
        return filtered_tools
    
    def append_qa_pair(self, question, results):
        # Define the custom operation identifier strings
        custom_identifiers = [
            "User requested to run the code to do a custom analysis of the activity with ID:",
            "User manually edited your code, and requested to run it, and return the result."
        ]
        
        # Remove all existing custom operation entries
        self.qa_pairs = [
            pair for pair in self.qa_pairs 
            if not any(identifier in pair["task"] for identifier in custom_identifiers)
        ]
        
        # Append the new QA pair
        self.qa_pairs.append({"task": question, "result": results})

    def format_qa_pairs(self, qa_pairs, max_qa_pairs=8):
        # Format QA pairs for prompts
        if not qa_pairs:
            return "No previous analyses."
        
        # Trim qa_pairs first if it exceeds max_qa_pairs
        if len(qa_pairs) > max_qa_pairs:
            qa_pairs = qa_pairs[-max_qa_pairs:]  # Keep only the most recent pairs
        
        formatted_str = ["Previous Analyses:"]
        
        for i, pair in enumerate(qa_pairs, 1):
            # Add question with minimal formatting
            formatted_str.append(f"\n{i}. Task: {pair['task']}")
            
            # Format answer with minimal separators and line preservation
            answer_lines = [line for line in pair['result'].split('\n') if line.strip()]
            formatted_str.append('Result:\n' + '\n'.join(answer_lines))
            
            # Add minimal separator if not the last pair
            if i < len(qa_pairs):
                formatted_str.append("-" * 5)
         
        return '\n'.join(formatted_str)
    
    def format_tasks(self, tasks):
        # Format tasks for prompts
        if not tasks:
            return "No previous tasks."
        
        formatted_str = ["Tasks:"]
        
        for i, task in enumerate(tasks, 1):
            # Add task with minimal formatting
            formatted_str.append(f"\n{i}. {task}")
            
            # Add minimal separator if not the last task
            if i < len(tasks):
                formatted_str.append("-" * 5)
        
        return '\n'.join(formatted_str)

    def messages_content_maintenance(self, agent, messages):
        if agent == 'Dataframe Inspector':
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    # Check if content is a list (image message format)
                    if isinstance(content, list):
                        # Extract only the text content from the message
                        text_content = next((item.get('text', '') for item in content if item.get('type') == 'text'), '')
                        # Replace the content with just the text and process it
                        msg['content'] = self._remove_all_except_task_ontology_text(text_content)
                    else:
                        # Process regular text message
                        msg['content'] = self._remove_all_except_task_ontology_text(content)
        # Planner messages content maintenance
        if agent == 'Planner' or agent == 'Theorist':
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    # Check if content is a list (image message format)
                    if isinstance(content, list):
                        # Extract only the text content from the message
                        text_content = next((item.get('text', '') for item in content if item.get('type') == 'text'), '')
                        # Replace the content with just the text and process it
                        msg['content'] = self._remove_all_except_task_xml(text_content)
                    else:
                        # Process regular text message
                        msg['content'] = self._remove_all_except_task_xml(content)

        if agent == 'Code Executor':
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    # Check if content is a list (image message format)
                    if isinstance(content, list):
                        # Extract only the text content from the message
                        text_content = next((item.get('text', '') for item in content if item.get('type') == 'text'), '')
                        # Replace the content with just the text and process it
                        if self.model_dict[models.get_model_name('Code Generator')[0]]['templ_formating'] == 'xml':
                            msg['content'] = self._remove_all_except_task_xml(text_content)
                        else:  # templ_formating is 'text'
                            msg['content'] = self._remove_all_except_task_text(text_content)
                    else:
                        # Process regular text message
                        if self.model_dict[models.get_model_name('Code Generator')[0]]['templ_formating'] == 'xml':
                            msg['content'] = self._remove_all_except_task_xml(content)
                        else:  # templ_formating is 'text'
                            msg['content'] = self._remove_all_except_task_text(content)

    def format_image_message(self, agent, message_content, image, provider, model):
        # Format the message content with an image. 
        # This replaces the last message content with the image and message content.
        
        if agent == 'Code Generator' or agent == 'Planner':
            message_content = message_content
        else:
            message_content = self.plot_query.format(message_content)
        
        if model in self.multimodal_models:
            if provider == 'anthropic':
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image,
                            },
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
            elif provider == 'openai':
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
            elif provider == 'gemini':
                # For Gemini, we'll return a format that can be converted to types.ContentDict later
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_base64",
                            "data": image,
                            "mime_type": "image/png"
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
        else:
            return {
                "role": "user",
                "content": message_content
            }

    def store_interaction(self, google_search_results=None, executed_code=None, code_exec_results=None, plot_jsons=None, qa_pairs=None, tasks=None):
        # Store the interaction if store is available
        if hasattr(self, 'interaction_store') and self.interaction_store is not None:
            try:
                messages = {
                    'pre_eval_messages': self.pre_eval_messages,
                    'select_analyst_messages': self.select_analyst_messages,
                    'eval_messages': self.eval_messages,
                    'df_inspector_messages': self.df_inspector_messages,
                    'code_messages': self.code_messages,
                    'plan_review_messages': self.plan_review_messages,
                    'insight_messages': self.insight_messages
                }
                
                # Collect all search triplets maintaining query-links relationship
                search_results = {
                    'search': {
                        'searches': [] # List of search triplets
                    }
                }
                
                # Add search triplets if they exist
                if google_search_results:
                    for triplet in google_search_results:
                        search_results['search']['searches'].append({
                            'query': triplet['query'],
                            'result': triplet['result'],
                            'links': triplet['links']
                        })
                
                # Combine search results with code execution results
                tool_results = {
                    'search': search_results['search'] if search_results['search']['searches'] else None,
                    'code_exec': {
                        'executed_code': executed_code,
                        'code_exec_results': code_exec_results,
                        'plot_jsons': plot_jsons if plot_jsons else [],
                        'qa_pairs': qa_pairs if qa_pairs else [],
                        'tasks': tasks if tasks else []
                    }
                }
                
                self.interaction_store.store_interaction(
                    thread_id=str(self.thread_id),
                    chain_id=str(self.chain_id),
                    messages=messages,
                    tool_results=tool_results
                )
            except storage_manager.StorageError as e:
                self.output_manager.print_wrapper(f"Warning: Failed to store interaction: {e}")

    ######################
    ### Eval Functions ###
    ######################
    
    def select_expert(self, pre_eval_messages):
        '''Call the Expert Selector'''
        agent = 'Expert Selector'
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        reasoning_effort = "medium"

        # Call OpenAI API to evaluate the task
        llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, pre_eval_messages, agent=agent,chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        expert, requires_dataset, confidence = self._extract_expert(llm_response)

        return llm_response, expert, requires_dataset, confidence
    
    def select_analyst(self, select_analyst_messages):
        '''Call the Analyst Selector'''
        agent = 'Analyst Selector'
        using_model,provider = models.get_model_name(agent)

        reasoning_effort = "medium"

        if provider == 'openai':
            tools=self.filter_tools(self.openai_tools_definition, search_enabled=False, auxiliary_enabled=False, feedback_enabled=self.user_feedback)
        elif provider == 'anthropic':
            tools=self.filter_tools(self.anthropic_tools_definition, search_enabled=False, auxiliary_enabled=False, feedback_enabled=self.user_feedback)
        elif provider == 'gemini':
            tools=self.filter_tools(self.gemini_tools_definition, search_enabled=False, auxiliary_enabled=False, feedback_enabled=self.user_feedback)
        else:
            tools=None

        # Call LLM API to evaluate the task
        if tools:
            llm_response, tool_response = self.llm_stream(self.log_and_call_manager, self.output_manager, select_analyst_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, select_analyst_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
            tool_response = []
            
        analyst, query_unknown, query_condition, intent_breakdown = self._extract_analyst(llm_response)

        return llm_response, analyst, query_unknown, query_condition, intent_breakdown
    
    def task_eval(self, eval_messages, agent, image=None):
        '''Call the Task Evaluator'''
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        reasoning_effort = "medium"

        # Format messages if image is provided
        if image is not None:
            last_message = eval_messages[-1]
            formatted_message = self.format_image_message(
                agent=agent,
                message_content=last_message["content"],
                image=image,
                provider=provider,
                model=using_model
            )
            eval_messages[-1] = formatted_message

        if provider == 'openai':
            tools=self.filter_tools(self.openai_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        elif provider == 'anthropic':
            tools=self.filter_tools(self.anthropic_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        elif provider == 'gemini':
            tools=self.filter_tools(self.gemini_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        else:
            tools=None

        if tools:
            llm_response, tool_response = self.llm_stream(self.log_and_call_manager, self.output_manager, eval_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, eval_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
            tool_response = []

        #self.output_manager.display_formated_plan(llm_response)

        if agent == 'Planner':
            response = self._extract_plan(llm_response)
        else:
            response = llm_response
            
        return response, tool_response, llm_response
    
    def taskmaster(self, question, df_columns, image=None):
        '''Taskmaster function to select the expert, refine the expert selection, and formulate a task for the expert'''
        plan = None
        analyst = None
        query_unknown = None
        query_condition = None
        requires_dataset = None
        confidence = None
        intent_breakdown = None

        ######## Select Expert ###########
        if image:
            template = self.plot_query_routing.format(question)
        else:
            template = self.expert_selector_user.format(question)
        self.pre_eval_messages.append({"role": "user", "content": template})
        select_expert_llm_response, expert,requires_dataset,confidence  = self.select_expert(self.pre_eval_messages) 
        self.pre_eval_messages.append({"role": "assistant", "content": select_expert_llm_response})

        ######## Refine Expert Selection, and Formulate the task for the expert ###########
        if expert == 'Data Analyst':
            self.select_analyst_messages.append({"role": "user", "content": self.analyst_selector_user.format(self.format_tasks(self.tasks),
                                                                                                              None if self.df_id is None else df_columns, 
                                                                                                              question)
                                                                                                              })
            
            select_analyst_llm_response, analyst, query_unknown, query_condition, intent_breakdown = self.select_analyst(self.select_analyst_messages)
            self.user_intent = intent_breakdown
            self.select_analyst_messages.append({"role": "assistant", "content": select_analyst_llm_response})

            self.output_manager.display_results(chain_id=self.chain_id, query={"expert":analyst, "original_question": question, "unknown": query_unknown, "condition": query_condition, "requires_dataset": requires_dataset, "confidence": confidence, "intent_breakdown": intent_breakdown})

            if analyst == 'Data Analyst DF':
                example_plan = self.default_example_plan_df
            elif analyst == 'Data Analyst Generic':
                example_plan = self.default_example_plan_gen

            # Retrieve the matching data_model, code and plan from the vector database if exists
            if self.vector_db:
                vector_data = self.pinecone_wrapper.retrieve_matching_record(query_unknown, query_condition, self.original_df_columns, similarity_threshold=self.similarity_threshold)
                if vector_data:
                    self.retrieved_plan = vector_data['metadata']['plan']
                    self.retrieved_data_model = vector_data['metadata']['data_model']
                    self.retrieved_code = vector_data['metadata']['code']
                    if self.retrieved_plan == '':
                        self.retrieved_plan = None
                    if self.retrieved_data_model == '':
                        self.retrieved_data_model = None
                    if self.retrieved_code == '':
                        self.retrieved_code = None

                if self.retrieved_plan is not None:
                    example_plan = f"USE THE FOLLOWING PLAN AS A BLUEPRINT FOR YOUR SOLUTION. FOLLOW ITS GENERAL STRUCTURE, BUT IF NECESSARY MODIFY OR EXPAND STEPS AS APPROPRIATE FOR THE CURRENT TASK:\n```yaml\n{self.retrieved_plan}\n```"

            if analyst == 'Data Analyst DF':
                if self.df_ontology and self.retrieved_data_model is None: # Only inspect the dataframe using ontology if the data_model is not retrieved from the vector database
                    query = intent_breakdown
                    data_model, df_inspector_messages = utils.inspect_dataframe(df=self.df, log_and_call_manager=self.log_and_call_manager, output_manager=self.output_manager, 
                                                                                     chain_id=self.chain_id, query=query, execution_mode=self.execution_mode, df_ontology=self.df_ontology, 
                                                                                     df_id=self.df_id, executor_client=self.api_client, messages=self.df_inspector_messages)
                    if df_inspector_messages:
                        self.df_inspector_messages = df_inspector_messages
                    self.data_model = self._extract_data_model(data_model)
                    dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
                    data_model_vis = utils.generate_model_graph(self.data_model)
                    self.messages_maintenace(self.df_inspector_messages)
                    self.messages_content_maintenance("Dataframe Inspector", self.df_inspector_messages)
                    # Create a dictionary containing both the visualization and the YAML data
                    data_model_web = {
                        'visualization': data_model_vis,
                        'yaml': self.data_model
                    }
                    self.output_manager.display_results(chain_id=self.chain_id, data_model=data_model_web)
                elif self.df_ontology and self.retrieved_data_model is not None: # Use the data_model retrieved from the vector database
                    self.data_model = self.retrieved_data_model
                    dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
                else:
                    dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
                    self.data_model = None

                if models.get_model_name("Planner")[0] not in self.reasoning_models:
                    self.eval_messages.append({"role": "user", "content": self.planner_user_df.format(utils.get_readable_date(), 
                                                                                                      self.format_qa_pairs(self.qa_pairs), 
                                                                                                      intent_breakdown, None if self.df_id is None else dataframe_head, 
                                                                                                      f"```yaml\n{self.data_model}\n```", example_plan)
                                                                                                      })
                else:
                    self.eval_messages.append({"role": "user", "content": self.planner_user_df_reasoning.format(utils.get_readable_date(), 
                                                                                                                self.format_qa_pairs(self.qa_pairs), 
                                                                                                                intent_breakdown, None if self.df_id is None else dataframe_head, 
                                                                                                                f"```yaml\n{self.data_model}\n```")
                                                                                                                })

                if not self.planning: 
                    self.eval_messages.append({"role": "assistant", "content": "No content, as planning was disabled for this task"}) # We just add a dummy assistant message if planning is disabled, to maintain the conversation messages structure

                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.code_messages[0] = {"role": "system", "content": self.code_generator_system_df}
                
            elif analyst == 'Data Analyst Generic':
                if models.get_model_name("Planner")[0] not in self.reasoning_models:
                    self.eval_messages.append({"role": "user", "content": self.planner_user_gen.format(utils.get_readable_date(), 
                                                                                                       self.format_qa_pairs(self.qa_pairs), 
                                                                                                       intent_breakdown, example_plan)
                                                                                                       })
                else:
                    self.eval_messages.append({"role": "user", "content": self.planner_user_gen_reasoning.format(utils.get_readable_date(), 
                                                                                                                 self.format_qa_pairs(self.qa_pairs), 
                                                                                                                 intent_breakdown)
                                                                                                                 })

                if not self.planning:
                    self.eval_messages.append({"role": "assistant", "content": "No content, as planning was disabled for this task"}) # We just add a dummy assistant message if planning is disabled, to maintain the conversation messages structure

                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.code_messages[0] = {"role": "system", "content": self.code_generator_system_gen}
            agent = 'Planner'

        elif expert == 'Research Specialist':
            self.eval_messages.append({"role": "user", "content": self.theorist_system.format(utils.get_readable_date(),
                                                                                              None if self.df_id is None else df_columns, 
                                                                                              self.last_code, self.format_qa_pairs(self.qa_pairs), 
                                                                                              question)
                                                                                              })
            agent = 'Theorist'
            self.output_manager.display_results(chain_id=self.chain_id, query={"expert":expert, "original_question": question, "unknown": query_unknown, "condition": query_condition, "requires_dataset": requires_dataset, "confidence": confidence, "intent_breakdown": intent_breakdown})
        else:
            self.eval_messages.append({"role": "user", "content": self.theorist_system.format(utils.get_readable_date(), 
                                                                                              None if self.df_id is None else df_columns, 
                                                                                              self.last_code, self.format_qa_pairs(self.qa_pairs), 
                                                                                              question)
                                                                                              })
            agent = 'Theorist'
        
        if not analyst or (self.planning and  models.get_model_name("Code Generator")[0] not in self.reasoning_models): # If the analyst is not selected or the code generator model is not a reasoning model
            task_eval,tool_response, full_response = self.task_eval(self.eval_messages, agent, image)
            self.eval_messages.append({"role": "assistant", "content": full_response})
            self.last_plan = task_eval
        else:
            task_eval = self.last_plan # If exists it will be included in the messages under header CONTEXT:. This is to pass Theorist output to coder if planning is disabled, or model is a reasoning model
            tool_response = []
            self.last_plan = None

        # Remove the oldest conversation and all tool calls, and dataset, plan, and code from the messages list
        self.messages_maintenace(self.eval_messages)
        self.messages_content_maintenance(agent, self.eval_messages)

        plan = task_eval

        return analyst, plan, tool_response, query_unknown, query_condition, intent_breakdown
    
    #####################
    ### Main Function ###
    #####################

    def pd_agent_converse(self, question=None, action=None, thread_id=None, chain_id=None, image=None, user_code=None):
        # Determine the mode of operation
        is_web = self.webui
        is_single_query = question is not None and not is_web

        # Handle the action parameter
        if action == 'reset':
            self.log_and_call_manager.consolidate_logs()
            self.reset_messages_and_logs()
            self.thread_id = None
            return

        # Set the thread_id for the new conversation
        if thread_id is None:
            self.thread_id = int(time.time())
        else:
            self.thread_id = thread_id

        # If chain_id is provided and different from current, restore the content of that chain to serve as the starting point
        if chain_id is not None and str(chain_id) != str(self.chain_id):
            try:
                if hasattr(self, 'interaction_store') and self.interaction_store is not None:
                    restored_data = self.interaction_store.restore_interaction(
                        thread_id=str(self.thread_id),
                        chain_id=str(chain_id)
                    )
                    
                    # Set the messages from restored data
                    self.pre_eval_messages = restored_data['pre_eval_messages']
                    self.select_analyst_messages = restored_data['select_analyst_messages']
                    self.eval_messages = restored_data['eval_messages']
                    self.df_inspector_messages = restored_data['df_inspector_messages']
                    self.code_messages = restored_data['code_messages']
                    self.plan_review_messages = restored_data['plan_review_messages']
                    self.insight_messages = restored_data['insight_messages']

                    # Restore code execution results
                    self.code_exec_results = restored_data['code_exec_results']

                    # Restore the last executed code
                    self.last_code = restored_data['executed_code']

                    # Restore the QA pairs
                    self.qa_pairs = restored_data['qa_pairs']
                    
                    # Restore the tasks
                    self.tasks = restored_data['tasks']
                    
            except storage_manager.StorageError as e:
                self.output_manager.print_wrapper(f"Warning: Failed to restore chain {chain_id}: {e}")
        
        # Set the chain_id for the new chain that will either build on the restored chain, current chain, or start afresh
        self.chain_id = int(time.time())

        # Start the conversation loop
        while True:
            if is_web or is_single_query:
                # For web UI or single query, process once and return
                if is_web:
                    question = self.output_manager.get_user_input()
                
                # Process the question
                self._process_question(question, image, user_code)

                # Reset non-cumulative messages
                self.reset_non_cumul_messages()
                
                if not is_web:
                    self.log_and_call_manager.consolidate_logs()
                    self.reset_messages_and_logs()
                return
            else:
                # For CLI/Jupyter interactive mode
                question = self.output_manager.display_user_input_prompt()
                if question.strip().lower() == 'exit':
                    self.log_and_call_manager.consolidate_logs()
                    self.reset_messages_and_logs()
                    break
                # Process the question
                self._process_question(question, image, user_code)

    def _process_question(self, question, image, user_code):
        if self.webui:
            self.output_manager.send_chain_id(self.thread_id, self.chain_id, self.df_id) # Send the thread_id and chain_id for the new chain to the web interface

        if user_code is None:
            if self.exploratory is True:
                self.output_manager.display_results(chain_id=self.chain_id, execution_mode=self.execution_mode, df_id=self.df_id, df=self.df,api_client=self.api_client)
                # Call the taskmaster method with the user's question if the exploratory mode is True
                analyst, plan, tool_response, query_unknown, query_condition, intent_breakdown = self.taskmaster(question, 
                                                                                                                             '' if self.df_id is None else utils.get_dataframe_columns(self.df, self.execution_mode, self.df_id, self.api_client), 
                                                                                                                             image
                                                                                                                             )
                if not analyst:
                    self.output_manager.display_results(chain_id=self.chain_id, research=tool_response, answer=plan)
                    self.log_and_call_manager.print_summary_to_terminal(self.output_manager)
                    self.store_interaction(google_search_results=tool_response, code_exec_results=self.code_exec_results, executed_code=self.last_code, qa_pairs=self.qa_pairs, tasks=self.tasks)
                    self.tasks.append(question)
                    return
                else:
                    if self.planning and models.get_model_name("Code Generator")[0] not in self.reasoning_models:
                        plan_vis = utils.generate_plan_graph(plan)
                        # Create a dictionary containing both the visualization and the YAML data
                        plan_web = {
                            'visualization': plan_vis,
                            'yaml': plan
                        }
                        self.output_manager.display_results(chain_id=self.chain_id, research=tool_response, plan=plan_web)
            else:
                self.output_manager.display_results(chain_id=self.chain_id, execution_mode=self.execution_mode, df_id=self.df_id, df=self.df, api_client=self.api_client)
                analyst = 'Data Analyst DF'
                plan = None
                tool_response = []
                intent_breakdown = question

            if analyst == 'Data Analyst DF':
                example_code = self.default_example_output_df
            else:
                example_code = self.default_example_output_gen
            
            if self.vector_db:
                if self.retrieved_code is not None:
                    example_code = f"USE THIS CODE AS A BLUEPRINT FOR YOUR SOLUTION. FOLLOW ITS GENERAL STRUCTURE AND ALGORITHMS, BUT IF NECESSARY MODIFY AS APPROPRIATE FOR THE CURRENT TASK.\n```python\n{self.retrieved_code}\n```"

            # Call the generate_code() method to generate the code
            code, llm_response = self.generate_code(analyst, intent_breakdown, plan, self.code_messages, example_code, image)
            code_type = 'llm'
            
            # We are returning the response from the LLM model to the user, as the code is not present, or can not be extracted
            if code is None or code == "":
                self.output_manager.display_results(chain_id=self.chain_id, answer=llm_response)
                self.log_and_call_manager.print_summary_to_terminal(self.output_manager)
                self.store_interaction(google_search_results=tool_response, code_exec_results=self.code_exec_results, executed_code=self.last_code, qa_pairs=self.qa_pairs, tasks=self.tasks)
                self.tasks.append(intent_breakdown)
                return
        else:
            analyst = 'User'
            #self.output_manager.display_results(chain_id=self.chain_id, df=self.df)
            code = user_code
            plan = None
            tool_response = None
            intent_breakdown = question
            code_type = 'user'

        # Call the execute_code() method to execute the code and summarise the results
        answer, results, code, plot_jsons, error_corrections = self.execute_code(analyst, code, plan, intent_breakdown, self.code_messages, self.execution_mode, code_type)

        # Review and correct the plan for storage if there were code corrections or use the original plan
        reviewed_plan = None

        if plan:
            if self.planning and models.get_model_name("Code Generator")[0] not in self.reasoning_models:
                reviewed_plan = self.review_plan(code, plan) if (self.vector_db and error_corrections > 0) else plan

        # Display the results
        self.output_manager.display_results(chain_id=self.chain_id, review=reviewed_plan, vector_db=self.vector_db)

        if user_code is None:
            if self.webui:
                # For web interface, always add the rank data to the output queue. This gives the user the option to rank the response even if the vector database is not enabled
                rank_data = {
                    "query_unknown": query_unknown,
                    "query_condition": query_condition,
                    "plan": '' if reviewed_plan is None else reviewed_plan,
                    "original_df_columns": '' if self.df_id is None else self.original_df_columns,
                    "data_model": '' if self.data_model is None else self.data_model,
                    "code": code,
                    "current_rank": 0
                }
                self.output_manager.output_queue.put(json.dumps({"rank_data": rank_data}))
            else:
                if self.vector_db:
                    rank_feedback = self.output_manager.display_user_input_rank()

                    if rank_feedback in map(str, range(0, 11)):
                        rank = rank_feedback
                    else:
                        rank = 0

                    # Add the question and answer pair to the QA retrieval index
                    self.pinecone_wrapper.add_record(
                        query_unknown, 
                        query_condition, 
                        '' if reviewed_plan is None else reviewed_plan,
                        '' if self.df_id is None else self.original_df_columns,
                        '' if self.data_model is None else self.data_model,
                        code,
                        rank,
                        self.similarity_threshold
                        )

        self.log_and_call_manager.print_summary_to_terminal(self.output_manager)

        # Append the QA pair to the list of QA pairs
        self.append_qa_pair(intent_breakdown, results)

        # Append Task to the list of tasks
        self.tasks.append(intent_breakdown)

        # Reset the retrieved data
        self.reset_retrieved_data()

        # Store the interaction
        self.store_interaction(google_search_results=tool_response, plot_jsons=plot_jsons, code_exec_results=results, executed_code=code, qa_pairs=self.qa_pairs, tasks=self.tasks)
            
    ######################
    ### Code Functions ###
    ######################
            
    def generate_code(self, analyst, intent_breakdown, plan, code_messages, example_code, image=None):
        agent = 'Code Generator'

        reasoning_effort = "high" if self.planning else "medium"
        
        # Get dataframe info and data model
        if analyst == 'Data Analyst DF':
            dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
            data_model = f"{self.data_model}" if self.df_ontology and self.data_model is not None else None
        else:
            dataframe_head = None
            data_model = None

        # Generate formatted prompt
        formatted_prompt = self.code_gen_prompt_generator.generate_prompt(
            analyst=analyst,
            planning=self.planning,
            model=models.get_model_name(agent)[0],
            reasoning_models=self.reasoning_models,
            plan_or_context=plan,
            dataframe_head=dataframe_head,
            data_model=data_model,
            task=intent_breakdown,
            python_version=self.python_version,
            pandas_version=self.pandas_version,
            plotly_version=self.plotly_version,
            previous_results=self.format_qa_pairs(self.qa_pairs),
            example_code=example_code
        )

        # Add formatted prompt to messages
        code_messages.append({"role": "user", "content": formatted_prompt})

        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        # Format messages if image is provided
        if image is not None:
            last_message = code_messages[-1]
            formatted_message = self.format_image_message(
                agent=agent,
                message_content=last_message["content"],
                image=image,
                provider=provider,
                model=using_model
            )
            code_messages[-1] = formatted_message

        if provider == 'openai':
            tools=self.filter_tools(self.openai_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        elif provider == 'anthropic':
            tools=self.filter_tools(self.anthropic_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        elif provider == 'gemini':
            tools=self.filter_tools(self.gemini_tools_definition, search_enabled=self.search_tool, auxiliary_enabled=self.auxiliary_dataset, feedback_enabled=self.user_feedback)
        else:
            tools=None

        # Call the LLM API or local model to generate the code
        if tools:
            llm_response, tool_response = self.llm_stream(self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)

        code_messages.append({"role": "assistant", "content": llm_response})

        # Extract the code from the API response
        code = self._extract_code(llm_response,analyst,provider)

        return code, llm_response

    def execute_code(self, analyst, code, plan, intent_breakdown, code_messages, execution_mode, code_type):
        agent = 'Code Executor'
        error_corrections = 0
        executor = self.executor
        results = None
        plot_images = []

        while error_corrections < self.MAX_ERROR_CORRECTIONS:
            # Remove the oldest conversation from the messages list
            self.messages_maintenace(code_messages)

            # Execute the code
            if code is not None:
                self.output_manager.display_tool_info('code_execution', f"exec(code,'df': pd.DataFrame) in {execution_mode} mode", chain_id=self.chain_id)
                
                new_df, new_results, error, new_plot_images = executor.execute(code, self.df, self.df_id)
                
                if error:
                    error_corrections += 1
                    code, code_messages = self.correct_code_errors(error, error_corrections, code_messages, analyst, code_type, code if code_type == 'user' else None)
                    # Ensure plot_images is cleared after each unsuccessful attempt
                    plot_images = []
                else:
                    self.df = new_df
                    results = new_results
                    plot_images = new_plot_images  # Only keep plots from successful execution
                    break

            # Remove examples from the messages list to minimize the number of tokens used
            code_messages = self._remove_examples(code_messages)

        # Remove dataset, plan, and code from the messages list
        self.messages_content_maintenance(agent, code_messages)

        # Store the results in a class variable so it can be appended to the subsequent messages list
        self.code_exec_results = results
        # Store the last generated code in a class variable so it can be appended to the subsequent messages list
        self.last_code = code

        plot_jsons = []
        for i, plot_data in enumerate(plot_images):
            plot_jsons.append(json.dumps({
                'type': 'plot',
                'data': plot_data['data'],
                'format': plot_data['format'],
                'id': f'plot_{i+1}',
                'chain_id': self.chain_id
            }))

        self.output_manager.display_results(chain_id=self.chain_id,code=code, plot_jsons=plot_jsons if self.webui else None)
        summary = self.summarise_solution(intent_breakdown, plan, results, code if code_type == 'user' else None)

        return summary, results, code, plot_jsons if self.webui else None, error_corrections
    
    def correct_code_errors(self, error, error_corrections, code_messages, analyst, code_type, code=None):
        agent = 'Error Corrector'

        model,provider = models.get_model_name(agent)

        #If error correction is greater than 2 remove the first error correction
        if error_corrections > 2:
            del code_messages[-4] 
            del code_messages[-3]
        
        # Append the error message to the messages list
        if code_type == 'user' and error_corrections == 1:
            if self.model_dict[model]['templ_formating'] == 'xml':
                code_messages.append({"role": "user", "content": self.error_corector_edited_system.format(code, error, self.python_version, self.pandas_version, self.plotly_version)})
            else: # templ_formating is 'text'
                code_messages.append({"role": "user", "content": self.error_corector_edited_system_reasoning.format(code, error, self.python_version, self.pandas_version, self.plotly_version)})
        else:
            if self.model_dict[model]['templ_formating'] == 'xml':
                code_messages.append({"role": "user", "content": self.error_corector_system.format(error, self.python_version, self.pandas_version, self.plotly_version)})
            else: # templ_formating is 'text'
                code_messages.append({"role": "user", "content": self.error_corector_system_reasoning.format(error, self.python_version, self.pandas_version, self.plotly_version)})

        # Display the error message
        self.output_manager.display_error(error,chain_id=self.chain_id)

        #llm_response = self.llm_call(self.log_and_call_manager,code_messages,agent=agent, chain_id=self.chain_id)
        llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models)
        code_messages.append({"role": "assistant", "content": llm_response})
        code = self._extract_code(llm_response,analyst,provider)

        return code, code_messages

    def review_plan(self,code, plan):
        agent = 'Reviewer'
        # Initialize the messages list with a user message containing the task prompt
        self.plan_review_messages = [{"role": "user", "content": self.reviewer_system.format(code, plan)}]

        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        llm_response = self.llm_stream(self.log_and_call_manager, self.output_manager, self.plan_review_messages, agent=agent, chain_id=self.chain_id)

        self.plan_review_messages.append({"role": "assistant", "content": llm_response})

        reviewed_plan = self._extract_plan(llm_response)
        plan_vis = utils.generate_plan_graph(plan)
        # Create a dictionary containing both the visualization and the YAML data
        plan_web = {
            'visualization': plan_vis,
            'yaml': reviewed_plan
        }
        self.output_manager.display_results(chain_id=self.chain_id, plan=plan_web)     
        
        return reviewed_plan
    
    
    ############################
    ## Summarise the solution ##
    ############################

    def summarise_solution(self, intent_breakdown, plan, results, code=None):
        agent = 'Solution Summarizer'

        reasoning_effort = "low"

        # Initialize the messages list with a user message containing the task prompt
        if code is not None:
            self.insight_messages = [{"role": "user", "content": self.solution_summarizer_custom_code_system.format(code, results)}]
        else:
            self.insight_messages = [{"role": "user", "content": self.solution_summarizer_system.format(intent_breakdown, plan, results)}]
        
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        summary = self.llm_stream(self.log_and_call_manager, self.output_manager, self.insight_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)

        self.insight_messages.append({"role": "assistant", "content": summary})

        self.output_manager.display_results(chain_id=self.chain_id, answer=summary)

        return summary