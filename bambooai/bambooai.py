import os
import time
import uuid
import pandas as pd
import warnings
import json
warnings.filterwarnings('ignore')

from bambooai import code_executor, models, template_formatting, qa_retrieval, log_manager, output_manager, web_output_manager, storage_manager, utils, executor_client
from bambooai.messages import reg_ex, tools_definition
from bambooai.messages.message_manager import MessageManager
from bambooai.messages.prompts import PromptManager

class BambooAI:
    def __init__(self, df: pd.DataFrame = None,
                 auxiliary_datasets: list = None,
                 max_conversations: int = 4,
                 vector_db: bool = False, 
                 search_tool: bool = False,
                 exploratory: bool = True,
                 df_ontology: str = None,
                 planning: bool = False,
                 webui: bool = False,
                 df_id: str = None,
                 custom_prompt_file: str = None
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

        # Check if the OPENAI_API_KEY environment variable is set
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
        
        # Check if search tool requirements are met
        def validate_search_tool(self, search_tool, search_mode):
            if not search_tool:
                return False
                
            if search_mode == 'google_ai':
                if not os.getenv('GEMINI_API_KEY'):
                    self.output_manager.display_system_messages(
                        "Warning: GEMINI_API_KEY environment variable not found. Disabling google_search."
                    )
                    return False
                    
            elif search_mode == 'selenium':
                if not os.getenv('SERPER_API_KEY'):
                    self.output_manager.display_system_messages(
                        "Warning: SERPER_API_KEY environment variable not found. Disabling google_search."
                    )
                    return False
                    
            return True
        
        # Validate search tool
        search_tool = validate_search_tool(self, search_tool, self.search_mode)
        
        # Check if the PINECONE_API_KEY and PINECONE_ENV environment variables are set if vector_db is True
        if vector_db:
            PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')

            if PINECONE_API_KEY is not None:
                try:
                    self.pinecone_wrapper = qa_retrieval.PineconeWrapper(output_manager=self.output_manager)
                except Exception as e:
                    self.output_manager.display_system_messages(f"Error initializing Pinecone")
                    vector_db = False

            else:
                self.output_manager.display_system_messages("Warning: PINECONE_API_KEY environment variable not found. Disabling vector_db.")
                vector_db = False

        self.MAX_ERROR_CORRECTIONS = 5
        
        # Dataframe
        # Check if the dataframe is provided and generate a unique ID if not provided
        if df is not None and not df_id:
            df_id = str(uuid.uuid4())

        self.df = df if df is not None else None
        self.original_df_columns = utils.get_dataframe_columns(df, self.execution_mode, df_id, self.api_client) if df_id is not None else None
        self.df_ontology = df_ontology # Set the df_ontology mode. The argument takes the path to the ontology file.
        self.data_model = None # Stores details retrieved from the ontology
        self.df_id = df_id

        # Auxiliary datasets
        self.auxiliary_datasets = auxiliary_datasets if auxiliary_datasets is not None else []

        # User intent
        self.user_intent = None

        # Set the vector_db mode. This mode is True when you want the model to rank the generated code, and store the results above threshold in a vector database.
        self.vector_db = vector_db
        self.retrieved_similarity_score = None  # Stores the similarity score of the retrieved data from the vector database
        self.retrieved_rank = None

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original user prompt and break it down in algorithm.
        self.exploratory = exploratory

        # Set the planning mode. This mode is True when you want the model to generate a plan for the solution.
        self.planning = planning

        # Set the pandas, python and plotly versions
        versions = utils.get_package_versions()
        self.pandas_version = versions['pandas_version']
        self.python_version = versions['python_version']
        self.plotly_version = versions['plotly_version']

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

        # Prompt manager
        self.prompts = PromptManager(custom_prompt_file_path=custom_prompt_file)

        self.message_manager = MessageManager(output_manager=self.output_manager,
                                               prompts=self.prompts,
                                               multimodal_models=self.multimodal_models,
                                               max_conversations=max_conversations,
                                               )

        # QA Retrieval
        self.similarity_threshold = 0.80
        self.retrieved_data_model = None
        self.retrieved_plan = None
        self.retrieved_code = None

        # Google Search
        self.search_tool = search_tool

        # Request user feedback during the conversation
        self.user_feedback = True

        # Templates formatting
        code_gen_templates = [
            'code_generator_user_df_plan',
            'code_generator_user_df_no_plan', 
            'code_generator_user_gen_plan',
            'code_generator_user_gen_no_plan'
        ]
        code_gen_template_dict = {
            name: getattr(self.prompts, name) for name in code_gen_templates
        }
        self.code_gen_prompt_generator = template_formatting.CodeGenPromptGenerator(code_gen_template_dict, self.model_dict)


    ######################
    ### Util Functions ###
    ######################

    def reset_messages_and_logs(self):
        self.message_manager.reset_messages(self.prompts)
        self.log_and_call_manager.clear_run_logs()

    def reset_retrieved_data(self):
        self.retrieved_data_model = None
        self.retrieved_plan = None
        self.retrieved_code = None
        self.retrieved_similarity_score = None
        self.retrieved_rank = None

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
        llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, pre_eval_messages, agent=agent,chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        expert, requires_dataset, confidence = reg_ex._extract_expert(llm_response)

        return llm_response, expert, requires_dataset, confidence
    
    def select_analyst(self, select_analyst_messages):
        '''Call the Analyst Selector'''
        agent = 'Analyst Selector'
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        reasoning_effort = "medium"

        if provider in ['openai', 'anthropic', 'gemini']:
            tools = tools_definition.filter_tools(provider, search_enabled=False, feedback_enabled=self.user_feedback)
        else:
            tools = None

        # Call LLM API to evaluate the task
        if tools:
            llm_response, tool_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, select_analyst_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, select_analyst_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
            tool_response = []
            
        analyst, query_unknown, query_condition, data_descr, intent_breakdown = reg_ex._extract_analyst(llm_response)

        # Retrieve the matching data_model, code and plan from the vector database if exists
        if self.vector_db:
            self.output_manager.print_wrapper(f"I am now going to search the episodic memory for similar tasks to the current one. if I find a match, I will use the plan, data model and code from the previous task to help me with the current task.", chain_id=self.chain_id)
            self.output_manager.display_tool_info('Semantic Search', f"Searching episodic memory for similar tasks", chain_id=self.chain_id)
            vector_data = self.pinecone_wrapper.retrieve_matching_record(intent_breakdown, data_descr, similarity_threshold=self.similarity_threshold)
            if vector_data:
                self.retrieved_similarity_score = str(round(vector_data['score'] * 100, 1))
                self.retrieved_rank = str(int(vector_data['metadata']['rank']))
                self.retrieved_plan = vector_data['metadata']['plan']
                self.retrieved_data_model = vector_data['metadata']['data_model']
                self.retrieved_code = vector_data['metadata']['code']
                if self.retrieved_plan == '':
                    self.retrieved_plan = None
                if self.retrieved_data_model == '':
                    self.retrieved_data_model = None
                if self.retrieved_code == '':
                    self.retrieved_code = None

                self.output_manager.display_results(chain_id=self.chain_id, 
                                                    semantic_search={'id': vector_data['id'],
                                                                     'similarity_score': self.retrieved_similarity_score,
                                                                     'rank': self.retrieved_rank, 
                                                                     'data': vector_data['metadata']['data_descr'], 
                                                                     'matching_task': vector_data['metadata']['intent']})
            else:
                self.output_manager.display_results(chain_id=self.chain_id, semantic_search=None)
        else: 
                self.output_manager.print_wrapper(f"I have not found a match in the episodic memory for the current task. I will continue with the current task without using any previous data.", chain_id=self.chain_id)

        return llm_response, analyst, query_unknown, query_condition, data_descr, intent_breakdown
    
    def task_eval(self, eval_messages, agent, image=None):
        '''Call the Task Evaluator'''
        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        reasoning_effort = "medium"

        # Format messages if image is provided
        if image is not None:
            last_message = eval_messages[-1]
            formatted_message = self.message_manager.format_image_message(
                agent=agent,
                message_content=last_message["content"],
                image=image,
                provider=provider,
                model=using_model
            )
            eval_messages[-1] = formatted_message

        if provider in ['openai', 'anthropic', 'gemini']:
            tools = tools_definition.filter_tools(provider, search_enabled=self.search_tool, feedback_enabled=self.user_feedback)
        else:
            tools = None

        if tools:
            llm_response, tool_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, eval_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, eval_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
            tool_response = []

        #self.output_manager.display_formated_plan(llm_response)

        if agent == 'Planner':
            response = reg_ex._extract_plan(llm_response)
        else:
            response = llm_response
            
        return response, tool_response, llm_response
    
    def taskmaster(self, question, df_columns, aux_datasets_columns, image=None):
        '''Taskmaster function to select the expert, refine the expert selection, and formulate a task for the expert'''
        plan = None
        analyst = None
        query_unknown = None
        query_condition = None
        requires_dataset = None
        data_descr = None
        confidence = None
        intent_breakdown = None

        ######## Select Expert ###########
        if image:
            template = self.prompts.plot_query_routing.format(question)
        else:
            template = self.prompts.expert_selector_user.format(question)
        self.message_manager.pre_eval_messages.append({"role": "user", "content": template})
        select_expert_llm_response, expert,requires_dataset,confidence  = self.select_expert(self.message_manager.pre_eval_messages) 
        self.message_manager.pre_eval_messages.append({"role": "assistant", "content": select_expert_llm_response})

        ######## Refine Expert Selection, and Formulate the task for the expert ###########
        if expert == 'Data Analyst':
            self.message_manager.select_analyst_messages.append({"role": "user", "content": self.prompts.analyst_selector_user.format(self.message_manager.format_tasks(),
                                                                                                              None if self.df_id is None else df_columns,
                                                                                                              aux_datasets_columns, 
                                                                                                              question)
                                                                                                              })
            
            select_analyst_llm_response, analyst, query_unknown, query_condition, data_descr, intent_breakdown = self.select_analyst(self.message_manager.select_analyst_messages)
            self.user_intent = intent_breakdown
            self.message_manager.select_analyst_messages.append({"role": "assistant", "content": select_analyst_llm_response})

            self.output_manager.display_results(chain_id=self.chain_id, query={"expert":analyst, 
                                                                               "original_question": question, 
                                                                               "unknown": query_unknown, 
                                                                               "condition": query_condition, 
                                                                               "requires_dataset": requires_dataset, 
                                                                               "confidence": confidence, 
                                                                               "intent_breakdown": intent_breakdown
                                                                               })
            
            if self.retrieved_plan is not None:
                example_plan = self.prompts.semantic_memory_plan_example.format(self.retrieved_similarity_score, self.retrieved_rank, self.retrieved_plan)
            else:
                if analyst == 'Data Analyst DF':
                    example_plan = self.prompts.default_example_plan_df
                elif analyst == 'Data Analyst Generic':
                    example_plan = self.prompts.default_example_plan_gen

            if analyst == 'Data Analyst DF':
                if self.df_ontology and self.retrieved_data_model is None: # Only inspect the dataframe using ontology if the data_model is not retrieved from the vector database
                    query = intent_breakdown
                    data_model, df_inspector_messages = utils.inspect_dataframe(df=self.df, prompt_manager=self.prompts, log_and_call_manager=self.log_and_call_manager, output_manager=self.output_manager, 
                                                                                     chain_id=self.chain_id, query=query, execution_mode=self.execution_mode, df_ontology=self.df_ontology, 
                                                                                     df_id=self.df_id, aux_file_paths=self.auxiliary_datasets, executor_client=self.api_client, messages=self.message_manager.df_inspector_messages)
                    if df_inspector_messages:
                        self.message_manager.df_inspector_messages = df_inspector_messages
                    self.data_model = reg_ex._extract_data_model(data_model)
                    dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
                    data_model_vis = utils.generate_model_graph(self.data_model)
                    self.message_manager.messages_maintenace(self.message_manager.df_inspector_messages)
                    self.message_manager.messages_content_maintenance("Dataframe Inspector", self.message_manager.df_inspector_messages, self.model_dict[models.get_model_name('Code Generator')[0]]['templ_formating'])
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
                    self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.planner_user_df.format(utils.get_readable_date(), 
                                                                                                      self.message_manager.format_qa_pairs(), 
                                                                                                      intent_breakdown, 
                                                                                                      None if self.df_id is None else dataframe_head, 
                                                                                                      utils.aux_datasets_to_string(file_paths=self.auxiliary_datasets,execution_mode=self.execution_mode,executor_client=self.api_client),
                                                                                                      f"```yaml\n{self.data_model}\n```", example_plan)
                                                                                                      })
                else:
                    self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.planner_user_df_reasoning.format(utils.get_readable_date(), 
                                                                                                                self.message_manager.format_qa_pairs(), 
                                                                                                                intent_breakdown, 
                                                                                                                None if self.df_id is None else dataframe_head,
                                                                                                                utils.aux_datasets_to_string(file_paths=self.auxiliary_datasets,execution_mode=self.execution_mode,executor_client=self.api_client),
                                                                                                                f"```yaml\n{self.data_model}\n```")
                                                                                                                })

                if not self.planning: 
                    self.message_manager.eval_messages.append({"role": "assistant", "content": "No content, as planning was disabled for this task"}) # We just add a dummy assistant message if planning is disabled, to maintain the conversation messages structure

                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.message_manager.code_messages[0] = {"role": "system", "content": self.prompts.code_generator_system_df}
                
            elif analyst == 'Data Analyst Generic':
                if models.get_model_name("Planner")[0] not in self.reasoning_models:
                    self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.planner_user_gen.format(utils.get_readable_date(), 
                                                                                                       self.message_manager.format_qa_pairs(), 
                                                                                                       intent_breakdown, example_plan)
                                                                                                       })
                else:
                    self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.planner_user_gen_reasoning.format(utils.get_readable_date(), 
                                                                                                                 self.message_manager.format_qa_pairs(), 
                                                                                                                 intent_breakdown)
                                                                                                                 })

                if not self.planning:
                    self.message_manager.eval_messages.append({"role": "assistant", "content": "No content, as planning was disabled for this task"}) # We just add a dummy assistant message if planning is disabled, to maintain the conversation messages structure

                # Replace first dict in messages with a new system task. This is to distinguish between the two types of analysts
                self.message_manager.code_messages[0] = {"role": "system", "content": self.prompts.code_generator_system_gen}
            agent = 'Planner'

        elif expert == 'Research Specialist':
            self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.theorist_system.format(utils.get_readable_date(),
                                                                                              None if self.df_id is None else df_columns,
                                                                                              aux_datasets_columns, 
                                                                                              self.message_manager.last_code, self.message_manager.format_qa_pairs(), 
                                                                                              question)
                                                                                              })
            agent = 'Theorist'
            self.output_manager.display_results(chain_id=self.chain_id, query={"expert":expert, "original_question": question, "unknown": query_unknown, "condition": query_condition, "requires_dataset": requires_dataset, "confidence": confidence, "intent_breakdown": intent_breakdown})
        else:
            self.message_manager.eval_messages.append({"role": "user", "content": self.prompts.theorist_system.format(utils.get_readable_date(), 
                                                                                              None if self.df_id is None else df_columns,
                                                                                              aux_datasets_columns,   
                                                                                              self.message_manager.last_code, self.message_manager.format_qa_pairs(), 
                                                                                              question)
                                                                                              })
            agent = 'Theorist'
        
        if not analyst or (self.planning and  models.get_model_name("Code Generator")[0] not in self.reasoning_models): # If the analyst is not selected or the code generator model is not a reasoning model
            task_eval, tool_response, full_response = self.task_eval(self.message_manager.eval_messages, agent, image)
            self.message_manager.eval_messages.append({"role": "assistant", "content": full_response})
            self.message_manager.last_plan = task_eval
        else:
            task_eval = self.message_manager.last_plan # If exists it will be included in the messages under header CONTEXT:. This is to pass Theorist output to coder if planning is disabled, or model is a reasoning model
            tool_response = []
            self.message_manager.last_plan = None

        # Remove the oldest conversation and all tool calls, and dataset, plan, and code from the messages list
        self.message_manager.messages_maintenace(self.message_manager.eval_messages)
        self.message_manager.messages_content_maintenance(agent, self.message_manager.eval_messages, self.model_dict[models.get_model_name('Code Generator')[0]]['templ_formating'])

        plan = task_eval

        return analyst, plan, tool_response, query_unknown, query_condition, data_descr, intent_breakdown
    
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
                self.message_manager.restore_interaction(self.thread_id, chain_id)
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
                self.message_manager.reset_non_cumul_messages()
                
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

        # Path to where the generated datasets will be stored.
        generated_datasets_path =  os.path.join('datasets', 'generated', str(self.thread_id), str(self.chain_id))

        if user_code is None:
            if self.exploratory is True:
                self.output_manager.display_results(chain_id=self.chain_id, execution_mode=self.execution_mode, df_id=self.df_id, df=self.df,api_client=self.api_client)
                # Call the taskmaster method with the user's question if the exploratory mode is True
                analyst, plan, tool_response, query_unknown, query_condition, data_descr, intent_breakdown = self.taskmaster(question, 
                                                                                                                 '' if self.df_id is None else utils.get_dataframe_columns(self.df, self.execution_mode, self.df_id, self.api_client),
                                                                                                                 utils.get_aux_datasets_columns(file_paths=self.auxiliary_datasets,execution_mode=self.execution_mode,executor_client=self.api_client),
                                                                                                                 image
                                                                                                                )
                if not analyst:
                    self.output_manager.display_results(chain_id=self.chain_id, research=tool_response, answer=plan)
                    self.log_and_call_manager.print_summary_to_terminal(self.output_manager)
                    self.message_manager.tasks.append(question)
                    self.message_manager.store_interaction(self.thread_id, self.chain_id, google_search_results=tool_response, code_exec_results=self.message_manager.code_exec_results, executed_code=self.message_manager.last_code, qa_pairs=self.message_manager.qa_pairs, tasks=self.message_manager.tasks)
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
                example_code = self.prompts.default_example_output_df
            else:
                example_code = self.prompts.default_example_output_gen
            
            if self.vector_db:
                if self.retrieved_code is not None:
                    example_code = self.prompts.semantic_memory_code_example.format(self.retrieved_similarity_score, self.retrieved_rank, self.retrieved_code)

            # Call the generate_code() method to generate the code
            code, llm_response = self.generate_code(
                analyst, 
                intent_breakdown, 
                plan, 
                self.message_manager.code_messages, 
                example_code, 
                image=image, 
                generated_datasets_path=generated_datasets_path
            )
            code_type = 'llm'
            
            # We are returning the response from the LLM model to the user, as the code is not present, or can not be extracted
            if code is None or code == "":
                self.output_manager.display_results(chain_id=self.chain_id, answer=llm_response)
                self.log_and_call_manager.print_summary_to_terminal(self.output_manager)
                self.message_manager.tasks.append(intent_breakdown)
                self.message_manager.store_interaction(self.thread_id, self.chain_id, google_search_results=tool_response, code_exec_results=self.message_manager.code_exec_results, executed_code=self.message_manager.last_code, qa_pairs=self.message_manager.qa_pairs, tasks=self.message_manager.tasks)
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
        answer, results, code, plot_jsons, error_corrections = self.execute_code(analyst, code, plan, intent_breakdown, self.message_manager.code_messages, self.execution_mode, code_type, generated_datasets_path)

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
                    "chain_id": self.chain_id,
                    "intent_breakdown": intent_breakdown,
                    "plan": '' if reviewed_plan is None else reviewed_plan,
                    "data_descr": '' if data_descr is None else data_descr,
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
                        self.chain_id,
                        intent_breakdown,
                        '' if reviewed_plan is None else reviewed_plan,
                        '' if data_descr is None else data_descr,
                        '' if self.data_model is None else self.data_model,
                        code,
                        rank,
                        self.similarity_threshold
                        )

        self.log_and_call_manager.print_summary_to_terminal(self.output_manager)

        # Append the QA pair to the list of QA pairs
        self.message_manager.append_qa_pair(intent_breakdown, results)

        # Append Task to the list of tasks
        self.message_manager.tasks.append(intent_breakdown)

        # Reset the retrieved data
        self.reset_retrieved_data()

        # Store the interaction
        self.message_manager.store_interaction(self.thread_id, self.chain_id, google_search_results=tool_response, plot_jsons=plot_jsons, code_exec_results=results, executed_code=code, qa_pairs=self.message_manager.qa_pairs, tasks=self.message_manager.tasks)
            
    ######################
    ### Code Functions ###
    ######################
            
    def generate_code(self, analyst, intent_breakdown, plan, code_messages, example_code, image=None, generated_datasets_path=None):
        agent = 'Code Generator'

        reasoning_effort = "high" if self.planning else "low"
        
        # Get dataframe info and data model
        if analyst == 'Data Analyst DF':
            dataframe_head = utils.inspect_dataframe(df=self.df, execution_mode=self.execution_mode, df_id=self.df_id, executor_client=self.api_client)
            data_model = f"{self.data_model}" if self.df_ontology and self.data_model is not None else None
        else:
            dataframe_head = None
            data_model = None

        # Generate formatted prompt
        formatted_prompt = self.code_gen_prompt_generator.generate_prompt(
            generated_datasets_path=generated_datasets_path,
            analyst=analyst,
            planning=self.planning,
            model=models.get_model_name(agent)[0],
            reasoning_models=self.reasoning_models,
            plan_or_context=plan,
            dataframe_head=dataframe_head,
            auxiliary_datasets=utils.aux_datasets_to_string(file_paths=self.auxiliary_datasets,execution_mode=self.execution_mode,executor_client=self.api_client),
            data_model=data_model,
            task=intent_breakdown,
            python_version=self.python_version,
            pandas_version=self.pandas_version,
            plotly_version=self.plotly_version,
            previous_results=self.message_manager.format_qa_pairs(),
            example_code=example_code
        )

        # Add formatted prompt to messages
        code_messages.append({"role": "user", "content": formatted_prompt})

        using_model,provider = models.get_model_name(agent)

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        # Format messages if image is provided
        if image is not None:
            last_message = code_messages[-1]
            formatted_message = self.message_manager.format_image_message(
                agent=agent,
                message_content=last_message["content"],
                image=image,
                provider=provider,
                model=using_model
            )
            code_messages[-1] = formatted_message

        if provider in ['openai', 'anthropic', 'gemini']:
            # Filter tools based on the selected provider and user feedback
            tools = tools_definition.filter_tools(provider, search_enabled=self.search_tool, feedback_enabled=self.user_feedback)
        else:
            tools = None

        # Call the LLM API or local model to generate the code
        if tools:
            llm_response, tool_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, tools=tools, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)
        else:
            llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)

        code_messages.append({"role": "assistant", "content": llm_response})

        # Extract the code from the API response
        code = reg_ex._extract_code(llm_response,analyst,provider)

        return code, llm_response

    def execute_code(self, analyst, code, plan, intent_breakdown, code_messages, execution_mode, code_type, generated_datasets_path):
        agent = 'Code Executor'
        error_corrections = 0
        executor = self.executor
        results = None
        plot_images = []

        while error_corrections < self.MAX_ERROR_CORRECTIONS:
            # Remove the oldest conversation from the messages list
            self.message_manager.messages_maintenace(code_messages)

            # Execute the code
            if code is not None:
                self.output_manager.display_tool_info('Code Execution', f"exec(code,'df': pd.DataFrame) in {execution_mode} mode", chain_id=self.chain_id)
                
                new_df, new_results, error, new_plot_images, generated_datasets = executor.execute(code, self.df, self.df_id, generated_datasets_path)
                
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
            code_messages = reg_ex._remove_examples(code_messages)

        if self.webui:
            # If webui is enabled, we display the results of code execution using the output manager
            self.output_manager.display_results(chain_id=self.chain_id, code_exec_results=results)

        # Remove dataset, plan, and code from the messages list
        self.message_manager.messages_content_maintenance(agent, code_messages, self.model_dict[models.get_model_name('Code Generator')[0]]['templ_formating'])

        # Store the results in a class variable so it can be appended to the subsequent messages list
        self.message_manager.code_exec_results = results
        # Store the last generated code in a class variable so it can be appended to the subsequent messages list
        self.message_manager.last_code = code

        plot_jsons = []
        for i, plot_data in enumerate(plot_images):
            plot_jsons.append(json.dumps({
                'type': 'plot',
                'data': plot_data['data'],
                'format': plot_data['format'],
                'id': f'plot_{i+1}',
                'chain_id': self.chain_id
            }))

        self.output_manager.display_results(chain_id=self.chain_id,code=code, plot_jsons=plot_jsons if self.webui else None, generated_datasets=generated_datasets if generated_datasets else None)
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
                code_messages.append({"role": "user", "content": self.prompts.error_corector_edited_system.format(code, error, self.python_version, self.pandas_version, self.plotly_version)})
            else: # templ_formating is 'text'
                code_messages.append({"role": "user", "content": self.prompts.error_corector_edited_system_reasoning.format(code, error, self.python_version, self.pandas_version, self.plotly_version)})
        else:
            if self.model_dict[model]['templ_formating'] == 'xml':
                code_messages.append({"role": "user", "content": self.prompts.error_corector_system.format(error, self.python_version, self.pandas_version, self.plotly_version)})
            else: # templ_formating is 'text'
                code_messages.append({"role": "user", "content": self.prompts.error_corector_system_reasoning.format(error, self.python_version, self.pandas_version, self.plotly_version)})

        # Display the error message
        self.output_manager.display_error(error,chain_id=self.chain_id)

        #llm_response = self.llm_call(self.log_and_call_manager,code_messages,agent=agent, chain_id=self.chain_id)
        llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, code_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models)
        code_messages.append({"role": "assistant", "content": llm_response})
        code = reg_ex._extract_code(llm_response,analyst,provider)

        return code, code_messages

    def review_plan(self,code, plan):
        agent = 'Reviewer'

        # Initialize the messages list with a user message containing the task prompt
        self.message_manager.plan_review_messages = [{"role": "user", "content": self.prompts.reviewer_system.format(code, plan)}]

        using_model,provider = models.get_model_name(agent)

        if provider == 'gemini':
            reasoning_effort = "minimal" # Flash tends to think for ever with higher budgets, so we use minimal reasoning effort to ground it.
        else:
            reasoning_effort = "low" # Minimal is not supported by OpenAI and Anthropic

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        llm_response = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, self.message_manager.plan_review_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)

        self.message_manager.plan_review_messages.append({"role": "assistant", "content": llm_response})

        reviewed_plan = reg_ex._extract_plan(llm_response)
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

        # Initialize the messages list with a user message containing the task prompt
        if code is not None:
            self.message_manager.insight_messages = [{"role": "user", "content": self.prompts.solution_summarizer_custom_code_system.format(code, results)}]
        else:
            self.message_manager.insight_messages = [{"role": "user", "content": self.prompts.solution_summarizer_system.format(intent_breakdown, plan, results)}]
        
        using_model,provider = models.get_model_name(agent)

        if provider == 'gemini':
            reasoning_effort = "minimal" # Flash tends to think for ever with higher budgets, so we use minimal reasoning effort to ground it.
        else:
            reasoning_effort = "low" # Minimal is not supported by OpenAI and Anthropic

        self.output_manager.display_tool_start(agent,using_model, chain_id=self.chain_id)

        summary = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, self.message_manager.insight_messages, agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models, reasoning_effort=reasoning_effort)

        self.message_manager.insight_messages.append({"role": "assistant", "content": summary})

        self.output_manager.display_results(chain_id=self.chain_id, answer=summary)

        return summary