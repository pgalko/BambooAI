from termcolor import cprint
from IPython.display import display, HTML, Markdown
import sys
import time
import pandas as pd

class OutputManager:
    def __init__(self):
        # Summary colors
        self.color_result_header_cli = 'green'
        # Error colors
        self.color_error_ntb = '#d86c00'
        self.color_error_cli = {'color': '\033[31m', 'reset': '\033[0m'}
        # Info colors
        self.color_info = 'green'
        # Token summary colors
        self.color_token_summary_cli = 'yellow'
        # Check if the code is running in a Jupyter notebook
        self.is_notebook = 'ipykernel' in sys.modules

    # Display the complete results.
    def display_results(self, df=None, code=None, answer=None, generated_datasets=None, **for_the_page):
        """What a run shows outside the page: the data's structure, the script, the answer, the files it made. The
        host hands over what the page shows as well - its tabs, the figures, the report's head: taken, and left out
        (0345: this took no `code_exec_results`, and outside the page a run ended in a TypeError at its report)."""
        self.display_formated_df(df)
        self.display_formated_code(code)
        self.display_formated_answer(answer)
        self.display_generated_datasets(generated_datasets)

    # Markdown formated summaries
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

    def display_generated_datasets(self, generated_datasets):
        if generated_datasets:
            if self.is_notebook:
                display(Markdown(f"## Generated Files:\n\n"))
                for dataset in generated_datasets:
                    display(Markdown(f"- File: {dataset}\n"))

    # Display the error message
    def display_error(self, error, chain_id=None):
        if self.is_notebook:
            display(HTML(f'<br><b><span style="color:{self.color_error_ntb};">I ran into an issue:</span></b><br><pre style="color:{self.color_error_ntb};">{error}</pre><br>'))
        else:
            sys.stderr.write(f"{self.color_error_cli['color']}\n>> I ran into an issue: {error}{self.color_error_cli['reset']}\n")
            sys.stderr.flush()

    def display_tool_info(self,action, action_input, chain_id=None):
        if self.is_notebook:
            display(HTML(f'<span style="color:{self.color_info};">-- Performing Action {action}: \"{action_input}\"</span>'))
            time.sleep(1)
        else:
            cprint(f"\n--Performing Action {action}: \"{action_input}\"", self.color_info)

    def display_system_messages(self, message, chain_id=None):
        if self.is_notebook:
            display(HTML(f'<span style="color:{self.color_info};">-- info: \"{message}\"</span>'))
            time.sleep(1)
        else:
            cprint(f"\n--info: \"{message}\"", self.color_info)

    def display_call_summary(self, summary_text):
        if self.is_notebook:
            # Split the summary text into lines
            summary_lines = summary_text.split('\n')
            # Start the Markdown table with headers
            markdown_table = '**Chain Summary:**\n\n'
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
            cprint("\n>> Chain Summary:", self.color_token_summary_cli, attrs=['bold'])
            self.print_wrapper(summary_text)

    # A wrapper for the print function. This can be used to add additional behaviors or formatting to the print function
    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        print(str(message), end=end, flush=flush)
