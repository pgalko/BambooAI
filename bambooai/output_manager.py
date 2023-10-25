
from termcolor import cprint
from IPython.display import display, HTML
import sys
import time

class OutputManager:
    def __init__(self):
        # Summary colors
        self.color_result_header_ntb = 'blue'
        self.color_result_header_cli = 'green'
        self.color_result_body_code = '#555555'
        self.color_result_body_text = 'black'
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
        self.color_token_summary_text_ntb = 'black'
        self.color_token_summary_cli = 'yellow'
    
    # Display the results of the analysis
    def display_results(self, df=None, answer=None, code=None, rank=None, vector_db=False):
        if 'ipykernel' in sys.modules:
            if df is not None:
                display(HTML(f'<p><b style="color:{self.color_result_header_ntb};">Here is the head of your dataframe:</b><br><pre style="color:{self.color_result_body_code};">{df.head(5)}</pre></p><br>'))
            if answer is not None:
                display(HTML(f'<p><b style="color:{self.color_result_header_ntb};">I now have the final answer:</b><br><pre style="color:{self.color_result_body_text}; white-space: pre-wrap; font-weight: bold;">{answer}</pre></p><br>'))
            if code is not None:
                display(HTML(f'<p><b style="color:{self.color_result_header_ntb};">Here is the final code that accomplishes the task:</b><br><pre style="color:{self.color_result_body_code};">{code}</pre></p><br>'))
            if vector_db and rank is not None:
                display(HTML(f'<p><b style="color:{self.color_result_header_ntb};">Solution Rank:</b><br><span style="color:{self.color_result_body_text};">{rank}</span></p><br>'))
        else:
            if df is not None:
                cprint(f"\n>> Here is the head of your dataframe:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(df.head(5))
            if answer is not None:
                cprint(f"\n>> I now have the final answer:\n{answer}", self.color_result_header_cli, attrs=['bold'])
            if code is not None:
                cprint(f"\n>> Here is the final code that accomplishes the task:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(code)
            if vector_db and rank is not None:
                cprint(f"\n>> Solution Rank:", self.color_result_header_cli, attrs=['bold'])
                self.print_wrapper(rank)
    
    # Display the header for the agent
    def display_tool_start(self, agent, model):
        color = self.color_tool_header
        if agent == 'Planner':
            msg = 'Drafting a plan to provide a comprehensive answer, please wait...'
        elif agent == 'Theorist':
            msg = 'Working on an answer to your question, please wait...'
        elif agent == 'Google Search Query Generator':
            msg = 'Generating a query to search for the answer, please wait...'
        elif agent == 'Expert Selector':
            msg = 'Selecting the expert to best answer your query, please wait...'
        elif agent == 'Code Generator':
            msg = 'I am generating the first version of the code, please wait...'
        elif agent == 'Code Debugger':
            msg = 'I am reviewing and debugging the first version of the code to check for any errors, bugs, or inconsistencies and will make corrections if necessary. Please wait...'
        elif agent == 'Code Ranker':
            msg = 'I am going to assess, summarize and rank the answer, please wait...'

        if 'ipykernel' in sys.modules:
            display(HTML(f'<p style="color:{color};">\nCalling Model: {model}</p>'))
            display(HTML(f'<p><b style="color:{color};">{msg}</b></p><br>'))
        else:
            cprint(f"\n>> Calling Model: {model}", color)
            cprint(f"\n>> {msg}\n", color, attrs=['bold'])
    
    # Display the footer for the agent
    def display_tool_end(self, agent):
        color = self.color_tool_header
        if agent == 'Code Debugger':
            msg = 'I have finished debugging the code, and will now proceed to the execution...'
        elif agent == 'Code Generator':
            msg = 'I have finished generating the code, and will now proceed to the execution...'

        if 'ipykernel' in sys.modules:
            display(HTML(f'<p><b style="color:{color};">{msg}</b></p><br>'))
        else:
            cprint(f"\n>> {msg}\n", color, attrs=['bold'])
    
    # Display the error message
    def display_error(self, error):
        if 'ipykernel' in sys.modules:
            display(HTML(f'<br><b><span style="color:{self.color_error_ntb};">I ran into an issue:</span></b><br><pre style="color:{self.color_error_ntb};">{error}</pre><br><b><span style="color:{self.color_error_ntb};">I will examine it, and try again with an adjusted code.</span></b><br>'))
        else:
            sys.stderr.write(f"{self.color_error_cli['color']}\n>> I ran into an issue:{error}. \n>> I will examine it, and try again with an adjusted code.{self.color_error_cli['reset']}\n")
            sys.stderr.flush()
    
    # Display the input to enter the prompt
    def display_user_input_prompt(self):
        if 'ipykernel' in sys.modules:
            display(HTML(f'<b style="color:{self.color_usr_input_prompt};">Enter your question or type \'exit\' to quit:</b>'))
            time.sleep(1)
            question = input()
        else:
            cprint("\nEnter your question or type 'exit' to quit:", self.color_usr_input_prompt, attrs=['bold'])
            question = input()

        return question
    
    # Display the input to enter the rank
    def display_user_input_rank(self):
        if 'ipykernel' in sys.modules:
            display(HTML(f'<b style="color:{self.color_usr_input_rank};">Are you happy with the ranking ? If YES type \'yes\'. If NO type in the new rank on a scale from 1-10:</b>'))
            time.sleep(1)
            rank_feedback = input()
        else:
            cprint("\nAre you happy with the ranking ?\nIf YES type 'yes'. If NO type in the new rank on a scale from 1-10:", self.color_usr_input_rank, attrs=['bold'])
            rank_feedback = input()

        return rank_feedback

    # Display the llm calls summary
    def display_call_summary(self, summary_text):
        if 'ipykernel' in sys.modules:
            display(HTML(f'''
            <br>
            <p><b style="color:{self.color_token_summary_header_ntb};">Chain Summary (Detailed info in bambooai_consolidated_log.json file):</b></p>
            <pre style="color:{self.color_token_summary_text_ntb}; white-space: pre-line;">{summary_text}</pre>
            '''))
        else:
            cprint("\n>> Chain Summary (Detailed info in bambooai_consolidated_log.json file):", self.color_token_summary_cli, attrs=['bold'])
            self.print_wrapper(summary_text)

    # A wrapper for the print function. This can be used to add additional behaviors or formatting to the print function
    def print_wrapper(self, message, end="\n", flush=False):
        # Add any additional behaviors or formatting here
        formatted_message = message
        
        print(formatted_message, end=end, flush=flush)



