
import os
import re
import sys
import base64
from contextlib import redirect_stdout
import io
import time
import openai
import pandas as pd
from termcolor import colored, cprint
from IPython.display import display, Image, HTML
import warnings
warnings.filterwarnings('ignore')

class BambooAI:
    def __init__(self, df: pd.DataFrame,max_conversations: int = 2 ,llm: str = 'gpt-3.5-turbo',llm_switch: bool = False, exploratory: bool = True):

        self.API_KEY = os.environ.get('OPENAI_API_KEY')
        self.MAX_ERROR_CORRECTIONS = 5
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1

        self.original_df = df
        self.df = df.copy()  # make a copy of the dataframe
        self.df_head = self.original_df.head(1)
    
        self.llm = llm
        self.llm_switch = llm_switch

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original prompt and suggest a few possible approaches.
        self.exploratory = exploratory  

        self.task_evaluation = """
        You are an AI data analyst and you are presented with the following task "{}" to analyze the data in the pandas dataframe. 
        The name of the dataframe is `df`, and the result of `print(df.head(1))` is:
        {}.
        Describe by breaking the solution down as a numbered task list, including any supplied values or formulas from the above task.
        This list should be no longer than 6 tasks, but can be less if 6 is not necessary.
        Don’t generate code.   
        """

        self.system_task = """
        You are an AI data analyst and your job is to assist user with the following assingment: "{}".
        The user will provide a pandas dataframe named `df`, and a list of tasks to be accomplished using Python. 
        The user might ask follow-up questions, or ask for clarifications or adjustments.
        Your answers should always consist of the following segments: "code", "reflection" and "flow" enclosed within <segment></segment> tags.
        Example:<code>Your code goes here</code> <reflection>Reflection on your answer</reflection> <flow>Mermaid flow diagram</flow>
        """

        self.task = """
        You have been presented with a pandas dataframe named `df`.
        The result of `print(df.head(1))` is:
        {}.
        Return the python code that acomplishes the following tasks: {}.
        Always include the import statements at the top of the code, and comments and print statement where necessary.
        Prefix the python code with <code> and suffix the code with </code>. Skip if the answer can not be expressed in a code.
        Offer a  reflection on your answer, and posibble use case. Also offer some alternative approaches that could be beneficial.
        Prefix the reflection with <reflection> and suffix the reflection with </reflection>.
        Finally output a code for mermaid diagram. The code should start with "graph TD;"
        Prefix the mermaid code with <flow> and suffix the mermaid flow with </flow>.
        """

        self.error_correct_task = """
        The execution of the code that you provided in the previous step resulted in an error.
        The error message is: {}
        Return a corrected python code that fixes the error.
        Always include the import statements at the top of the code, and comments and print statement where necessary.
        Prefix the python code with <code> and suffix the code with </code>. Skip if the answer can not be expressed in a code.
        Offer a  reflection on your answer, and posibble use case. Also offer some alternative approaches that could be beneficial.
        Prefix the reflection with <reflection> and suffix the reflection with </reflection>.
        Finally output a code for mermaid diagram. The code should start with "graph TD;"
        Prefix the mermaid code with <flow> and suffix the mermaid flow with </flow>.
        """

        openai.api_key = self.API_KEY
        self.total_tokens_used = []

    def mm(self, graph):
        graphbytes = graph.encode("ascii")
        base64_bytes = base64.b64encode(graphbytes)
        base64_string = base64_bytes.decode("ascii")
        img_url = "https://mermaid.ink/img/" + base64_string
        return img_url

    def llm_call(self, messages: str, temperature: float = 0, max_tokens: int = 1000):
        response = openai.ChatCompletion.create(
            model=self.llm,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens

        return content, tokens_used
    
    # Functions to sanitize the output from the LLM
    def _extract_code(self,response: str, separator: str = "```") -> str:

        # Define a blacklist of Python keywords and functions that are not allowed
        blacklist = ['os','subprocess','sys','eval','exec','file','socket','urllib',
                    'shutil','pickle','ctypes','multiprocessing','tempfile','glob','code','pty','commands',
                    'requests','cgi','cgitb','xml.etree.ElementTree','builtins'
                    ]
        
        # Search for a pattern between <reflection> and </reflection> in the response
        match = re.search(r"<reflection>(.*)</reflection>", response, re.DOTALL)
        if match:
            # If a match is found, extract the reflection between <reflection> and </reflection>
            reflection = match.group(1)
        else:
            reflection = ""

        # Search for a pattern between <flow> and </flow> in the response
        match = re.search(r"<flow>(.*)</flow>", response, re.DOTALL)
        if match:
            # If a match is found, extract the reflection between <reflection> and </reflection>
            flow = match.group(1)
        else:
            flow = ""

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

        # Remove any occurrences of df = pd.DataFrame() with any number of characters inside the parentheses.
        code = re.sub(r"df\s*=\s*pd\.DataFrame\(.*?\)", "", code, flags=re.DOTALL)

        # Define the regular expression pattern to match the blacklist items
        pattern = r"^(.*\b(" + "|".join(blacklist) + r")\b.*)$"

        # Replace the blacklist items with comments
        code = re.sub(pattern, r"# not allowed \1", code, flags=re.MULTILINE)

        # Return the cleaned and extracted code
        return code.strip(), reflection.strip(), flow.strip()
    
    def task_eval(self, question=None):
        # Initialize the messages list with a system message containing the task prompt
        eval_messages = [{"role": "system", "content": self.task_evaluation.format(question, self.df_head,)}]

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nUsing Model: {self.llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Trying to determine the best method to analyse your data, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n> Using Model: {self.llm}", "magenta"))
            cprint(f"\n> Trying to determine the best method to analyse your data, please wait...\n", 'magenta', attrs=['bold'])

        # Function to display results nicely
        def display_task(task):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:blue;">I have created the following task list, and will now try to express it in code:</b><br><pre style="color:black;"><b>{task}</b></pre></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\nTask:\n{task}\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API and handle rate limit errors
        try:
            llm_response, tokens_used = self.llm_call(eval_messages,temperature=0) # higher temperature results in more "creative" answers (sometimes too creative :-))
        except openai.error.RateLimitError:
            print(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)
            llm_response, tokens_used = self.llm_call(eval_messages)

        task = llm_response
        
        display_task(task)

        self.total_tokens_used.append(tokens_used)

        return task

    def pd_agent_converse(self, question=None):
        # Function to display results nicely
        def display_results(answer, code, reflection, flow, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:blue;">Answer:</b><br><pre style="color:black;"><b>{answer}</b></pre></p><br>'))
                display(HTML(f'<p><b style="color:blue;">I have generated the following code:</b><br><pre style="color:#555555;">{code}</pre></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Final Thoughts:</b><br><b style="color:black;">{reflection}</b></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Below is my approch as a Flow chart:</b><br><img src="{self.mm(flow)}" alt="Analysis Flow"></img></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\n> Answer:\n{answer}\n", 'green', attrs=['bold'])
                cprint(f"> I have generated the following code:\n{code}\n", 'green', attrs=['bold'])
                cprint(f"> Final Thoughts:\n{reflection}\n", 'green', attrs=['bold'])
                cprint(f"> Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])
        
        # If a question is provided, skip the input prompt
        if question is not None:
            # Initialize the messages list with a system message containing the task prompt
            messages = [{"role": "system", "content": self.system_task.format(question)}]
            # Call the task_eval method with the user's question if the exploratory mode is True
            if self.exploratory is True:
                task = self.task_eval(question)
            else:
                task = question
            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, reflection, flow, total_tokens_used_sum = self.pd_agent(task, messages, self.df)
            display_results(answer, code, reflection, flow, total_tokens_used_sum)
            return

        # Start an infinite loop to keep asking the user for questions
        first_iteration = True  # Flag for the first iteration of the loop
        while True:
            # Prompt the user to enter a question or type 'exit' to quit
            if 'ipykernel' in sys.modules:
                display(HTML('<b style="color:blue;">Enter your question or type \'exit\' to quit:</b>'))
                question = input()
            else:
                cprint("\nEnter your question or type 'exit' to quit:", 'blue', attrs=['bold'])
                question = input()

            # If the user types 'exit', break out of the loop
            if question.strip().lower() == 'exit':
                break

            if first_iteration:
                # Initialize the messages list with a system message containing the task prompt
                messages = [{"role": "system", "content": self.system_task.format(question)}]
                # Call the task_eval method with the user's question if the exploratory mode is True
                if self.exploratory is True:
                    task = self.task_eval(question)
                else:
                    task = question
            else:
                task = question

            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, reflection, flow, total_tokens_used_sum = self.pd_agent(task, messages, self.df)
            display_results(answer, code, reflection,flow, total_tokens_used_sum)

            # After the first iteration, set the flag to False
            first_iteration = False

    def pd_agent(self, question, messages, df=None):
        # Add a user message with the updated task prompt to the messages list
        messages.append({"role": "user", "content": self.task.format(self.df_head, question)})

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nUsing Model: {self.llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Processing your request, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n> Using Model: {self.llm}", "magenta"))
            cprint(f"\n> Processing your request, please wait...\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API and handle rate limit errors
        try:
            llm_response, tokens_used = self.llm_call(messages)

        except openai.error.RateLimitError:
            print(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)
            llm_response, tokens_used = self.llm_call(messages)

        # Extract the code from the API response
        code,reflection,flow = self._extract_code(llm_response)

        # Update the total tokens used
        self.total_tokens_used.append(tokens_used)
        total_tokens_used_sum = sum(self.total_tokens_used)

        # Initialize error correction counter
        error_corrections = 0

        # Store the original llm value
        original_llm = self.llm

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
                        exec(code)
                    break
                except Exception as e:
                    # Print the error message
                    if 'ipykernel' in sys.modules:
                        # Jupyter notebook
                        display(HTML(f'<br><b><span style="color: #d86c00;">I ran into an issue:</span></b><br><pre style="color: #d86c00;">{e}</pre><br><b><span style="color: #d86c00;">I will examine it, and try again with an adjusted code.</span></b><br>'))
                    else:
                        # CLI
                        #print(colored(f'I ran into an issue: {e}. > I will examine it, and try again with an adjusted code.', 'red'))
                        sys.stderr.write('\033[31m' + f'> I ran into an issue: {e}. \n> I will examine it, and try again with an adjusted code.' + '\033[0m' + '\n')
                        sys.stderr.flush()

                    # Increment the error correction counter and update the messages list with the error
                    error_corrections += 1
                    messages.append({"role": "user", "content": self.error_correct_task.format(e)})

                    # Switch to gpt-4 if llm_switch is True
                    if self.llm_switch:
                        self.llm = 'gpt-4'
                        if 'ipykernel' in sys.modules:
                            # Jupyter notebook
                            display(HTML('<span style="color: #d86c00;">Switching model to gpt-4 to try to improve the outcome.</span>'))
                        else:
                            # CLI
                            print(colored('> Switching model to gpt-4 to try to improve the outcome.', 'red'), flush=True)
                            sys.stderr.write('\033[31m' + f'> Switching model to gpt-4 to try to improve the outcome.' + '\033[0m' + '\n')
                            sys.stderr.flush()

                    # Attempt to correct the code and handle rate limit errors
                    try:
                        llm_response, tokens_used = self.llm_call(messages)
                        code,reflection,flow = self._extract_code(llm_response)
                        self.total_tokens_used.append(tokens_used)
                        total_tokens_used_sum = sum(self.total_tokens_used)
                    except openai.error.RateLimitError:
                        print(
                            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
                        )
                        time.sleep(10)
                        llm_response, tokens_used = self.llm_call(messages)
                        code,reflection,flow = self._extract_code(llm_response)
                        self.total_tokens_used.append(tokens_used)
                        total_tokens_used_sum = sum(self.total_tokens_used)

            # Switch back to the original llm before the function finishes
            self.llm = original_llm

        # Get the output from the executed code
        answer = output.getvalue()

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return answer, code, reflection, flow, total_tokens_used_sum
    
