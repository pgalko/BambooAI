
from termcolor import cprint
from IPython.display import display, HTML, Markdown
import sys
import time
import pandas as pd

class OutputManager:
    def __init__(self):
        # Summary colors
        self.color_result_header_ntb = 'blue'
        self.color_result_header_cli = 'green'
        self.color_result_body_code = '#555555'
        self.color_result_body_text = '#555555'
        # agent colors
        self.color_tool_header = 'magenta'
        # Error colors
        self.color_error_ntb = '#d86c00'
        self.color_error_cli = {'color': '\033[31m', 'reset': '\033[0m'}
        # User input colors
        self.color_usr_input_prompt = 'blue'
        self.color_usr_input_rank = 'green'
        # Token summary colors
        self.color_token_summary_header_ntb = 'blue'
        self.color_token_summary_text_ntb = '#555555'
        self.color_token_summary_cli = 'yellow'
        # Check if the code is running in a Jupyter notebook
        self.is_notebook = 'ipykernel' in sys.modules
    
    # Display the complete results.
    def display_results(self, chain_id=None, execution_mode=None, df_id=None, api_client=None, df=None, query=None, data_model=None, research=None, plan=None, code=None, answer=None, plot_jsons=None, review=None, vector_db=False, generated_datasets=None, semantic_search=None):
        self.display_formated_df(df)
        self.display_formatted_data_model(data_model)
        self.display_formatted_search(research)
        self.display_formated_plan(plan)
        self.display_formated_code(code)
        self.display_formated_answer(answer)
        self.display_formated_review(vector_db, review)
        self.display_generated_datasets(generated_datasets)

    def send_html_content(self, html_content, chain_id=None):
        """Display HTML content directly in the notebook"""
        if self.is_notebook:
            display(HTML(html_content))
        else:
            pass

    # Markdown formated Agent summaries
    def display_formated_plan(self, plan):
        if plan is not None:
            if self.is_notebook:
                display(Markdown(f"## Reasoning and Planning:\n\n```yaml\n{plan['yaml']}\n```"))
            else:
                cprint(f"\n>> Reasoning and Planning:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(plan)

    def display_formated_df(self, df):
        if df is not None:
            if self.is_notebook:
                display(Markdown(f'## Dataframe Preview:'))
                pd.set_option('display.max_columns', None)
                pd.set_option('display.expand_frame_repr', False)
                pd.set_option('display.max_colwidth', None)
                display(df.head(25))
            else:
                cprint(f"\n>> Here is the structure of your dataframe:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(df.dtypes)

    def display_formatted_data_model(self, data_model):
        if data_model is not None:
            if self.is_notebook:
                display(Markdown(f"## Data Model:\n\n```yaml\n{data_model['yaml']}\n```"))
            else:
                cprint(f"\n>> Data Model:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(data_model['yaml'])

    def display_formated_code(self, code):
        if code is not None:
            if self.is_notebook:
                display(Markdown(f'## Applied Code:\n\n```python\n{code}\n```'))
            else:
                cprint(f"\n>> Here is the final code that accomplishes the task:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(code)

    def display_formated_answer(self, answer):
        if answer is not None:
            if self.is_notebook:
                display(Markdown(f'## Solution Summary:\n\n{answer}'))
            else:
                cprint(f"\n>> I now have the final answer:\n{answer}", self.color_result_header_cli, attrs=['bold'])

    def display_formated_review(self, vector_db, review):
        if vector_db and review is not None:
            if self.is_notebook:
                display(Markdown(f'## Solution review:\n\n{review}'))
            else:
                cprint(f"\n>> Solution Review:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(review)

    def display_formatted_search(self, triplets):
        if triplets:
            research_content = f"## Research Findings:\n\n"
            for triplet in triplets:
                research_content += f"### Query: {triplet['query']}\n\n{triplet['result']}\n\n### Sources:\n"
                for link in triplet['links']:
                    research_content += f"\nTitle: {link['title']}  \nLink: {link['link']}  \n\n"

            if self.is_notebook:
                display(Markdown(research_content))

    def display_generated_datasets(self, generated_datasets):
        if generated_datasets:
            if self.is_notebook:
                display(Markdown(f"## Generated Files:\n\n"))
                for dataset in generated_datasets:
                    display(Markdown(f"- File: {dataset}\n"))

    # Display the header for the agent
    def display_tool_start(self, agent, model, chain_id=None):
        color = self.color_tool_header
        if agent == 'Planner':
            msg = 'Drafting a plan to provide a comprehensive answer, please wait...'
        elif agent == 'Dataframe Inspector':
            msg = 'Inspecting the dataframe schema, please wait...'
        elif agent == 'Theorist':
            msg = 'Working on an answer to your question, please wait...'
        elif agent == 'Google Search Query Generator':
            msg = 'I am going to generate the queries and search the internet for the answer, please wait...'
        elif agent == 'Expert Selector':
            msg = 'Selecting the expert to best answer your query, please wait...'
        elif agent == 'Code Generator':
            msg = 'I am generating the code, please wait...'
        elif agent == 'Reviewer':
            msg = 'I am going to assess and rank the answer, please wait...'
        elif agent == 'Solution Summarizer':
            msg = 'Summarizing the solution, please wait...'
        

        if self.is_notebook:
            display(HTML(f'<p style="color:{color};">\nCalling Model: {model}</p>'))
            display(HTML(f'<p><b style="color:{color};">{msg}</b></p><br>'))
        else:
            cprint(f"\n>> Calling Model: {model}", color)
            cprint(f"\n>> {msg}\n", color, attrs=['bold'])
    
    # Display the error message
    def display_error(self, error, chain_id=None):
        if self.is_notebook:
            display(HTML(f'<br><b><span style="color:{self.color_error_ntb};">I ran into an issue:</span></b><br><pre style="color:{self.color_error_ntb};">{error}</pre><br><b><span style="color:{self.color_error_ntb};">I will examine it, and try again with an adjusted code.</span></b><br>'))
        else:
            sys.stderr.write(f"{self.color_error_cli['color']}\n>> I ran into an issue:{error}. \n>> I will examine it, and try again with an adjusted code.{self.color_error_cli['reset']}\n")
            sys.stderr.flush()
    
    # Display the input to enter the prompt
    def display_user_input_prompt(self):
        if self.is_notebook:
            display(HTML(f'<b style="color:{self.color_usr_input_prompt};">Enter your question or type \'exit\' to quit:</b>'))
            time.sleep(1)
            question = input()
        else:
            cprint("\nEnter your question or type 'exit' to quit:", self.color_usr_input_prompt, attrs=['bold'])
            question = input()

        return question
    
    # Display the input to enter the rank
    def display_user_input_rank(self):
        if self.is_notebook:
            display(HTML(f'<b style="color:{self.color_usr_input_rank};">Are you happy with the ranking ? If YES type \'yes\'. If NO type in the new rank on a scale from 1-10:</b>'))
            time.sleep(1)
            rank = input()
        else:
            cprint("\nAre you happy with the ranking ?\nIf YES type 'yes'. If NO type in the new rank on a scale from 1-10:", self.color_usr_input_rank, attrs=['bold'])
            rank = input()

        return rank
    
    # Request user feedback
    def request_user_feedback(self, chain_id=None, query_clarification=None, context_needed=None):
        if self.is_notebook:
            display(HTML(f'<b style="color:{self.color_usr_input_rank};">Requesting user feedback: \"{query_clarification}\"</b>'))
            time.sleep(1)
            feedback = input()
        else:
            cprint(f"\nRequesting user feedback: \"{query_clarification}\"", self.color_usr_input_rank)
            feedback = input()
        
        return feedback
 
    def display_tool_info(self,action, action_input, chain_id=None):
        if self.is_notebook:
            display(HTML(f'<span style="color:{self.color_usr_input_rank};">-- Performing Action {action}: \"{action_input}\"</span>'))
            time.sleep(1)
        else:
            cprint(f"\n--Performing Action {action}: \"{action_input}\"", self.color_usr_input_rank)

    def display_system_messages(self, message):
        if self.is_notebook:
            display(HTML(f'<span style="color:{self.color_usr_input_rank};">-- info: \"{message}\"</span>'))
            time.sleep(1)
        else:
            cprint(f"\n--info: \"{message}\"", self.color_usr_input_rank)

    def display_call_summary(self, summary_text):
        if self.is_notebook:
            # Split the summary text into lines
            summary_lines = summary_text.split('\n')
            # Start the Markdown table with headers
            markdown_table = '**Chain Summary (Detailed info in bambooai_consolidated_log.json file):**\n\n'
            markdown_table += '| Metric                      | Value          |\n'
            markdown_table += '|-----------------------------|----------------|\n'
            # Populate the table with data
            for line in summary_lines:
                if line.strip():  # Ensure the line contains data
                    key, value = line.split(':')
                    key = key.strip()
                    value = value.strip()
                    markdown_table += f'| {key} | {value} |\n'

            display(Markdown(markdown_table))
        else:
            cprint("\n>> Chain Summary (Detailed info in bambooai_consolidated_log.json file):", self.color_token_summary_cli, attrs=['bold'])
            self.print_wrapper(summary_text)

    # A wrapper for the print function. This can be used to add additional behaviors or formatting to the print function
    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        # Add any additional behaviors or formatting here
        formatted_message = message
        
        print(formatted_message, end=end, flush=flush)



