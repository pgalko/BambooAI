
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
    def __init__(self, df: pd.DataFrame,max_conversations: int = 2 ,llm: str = 'gpt-3.5-turbo',debug: bool = False, llm_switch: bool = False, exploratory: bool = True, flow_diagram: bool = False):

        self.API_KEY = os.environ.get('OPENAI_API_KEY')
        self.MAX_ERROR_CORRECTIONS = 5
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1

        self.original_df = df
        self.df = df.copy()  # make a copy of the dataframe
        self.df_head = self.original_df.head(1)
    
        self.llm = llm
        self.debug = debug
        self.llm_switch = llm_switch

        # Set the exploratory mode. This mode is True when you want the model to evaluate the original prompt and suggest a few possible approaches.
        self.exploratory = exploratory

        # Show flow diagram
        self.flow_diagram = flow_diagram

        self.task_evaluation = """
        You are an AI data analyst and your task is to design a heuristic algorithm to solve the following problem: "{}" with code. 
        Your method will be used for data analysis and applied to a pandas dataframe.
        The name of the dataframe is `df`, and the result of `print(df.head(1))` is:
        {}.
        The dataframe df has already been defined and populated with the required data.
         
        Work the solution out in a step by step way to be sure we have the right answer. 
        Your solution should be no longer than 8 steps, but can be less if 8 is not necessary.
        Don’t generate code.

        Example Input:       
        Can you please describe this dataset ?

        Example Output:
        1. Identify the dataframe `df`.
        2. Call the `describe()` method on `df`.
        3. Print the output of the `describe()` method.         
        """

        self.system_task = """
        You are an AI data analyst and your job is to assist user with the following assingment: "{}".
        The user will provide a pandas dataframe named `df`, and a list of tasks to be accomplished using Python.
        The dataframe df has already been defined and populated with the required data.

        Prefix the python code with <code> and suffix the code with </code>.

        Deliver a comprehensive evaluation of the outcomes obtained from employing your method, including in-depth insights, 
        identification of nuanced or hidden patterns, and potential use cases. 
        Additionally, consider suggesting other methods that could potentially offer better results or efficiencies.
        Don’t include any code or mermaid diagrams in the analisys.
        Prefix the evaluation with <reflection> and suffix the evaluation with </reflection>.

        Finally output the code for mermaid diagram. The code should start with "graph TD;"
        Prefix the mermaid code with <flow> and suffix the mermaid code with </flow>.
        
        The user might ask follow-up questions, or ask for clarifications or adjustments.

        Example input:
        1. Identify the dataframe `df`.
        2. Call the `describe()` method on `df`.
        3. Print the output of the `describe()` method.

        Example Output:
        <code>
        import pandas as pd

        # Identify the dataframe `df`
        # df has already been defined and populated with the required data

        # Call the `describe()` method on `df`
        df_description = df.describe()

        # Print the output of the `describe()` method
        print(df_description)
        </code>

        <reflection>
        The code imports pandas and uses the describe() method to generate summary statistics of the dataframe. 
        The output of the describe() method includes the count, mean, standard deviation, minimum, 25th percentile, median, 75th percentile, and maximum values for each column in the dataframe. 
        This information can be used to gain insights into the distribution and range of values in the dataframe, identify potential outliers or missing values, 
        and inform data cleaning and preprocessing steps. The code is straightforward and accomplishes the task as described. 
        However, it may be useful to further explore the data using visualizations or additional statistical analyses to gain a deeper understanding 
        of the data and identify any patterns or relationships that may be present.
        </reflection>

        <flow>
        graph TD;
        A[Identify dataframe df] --> B[Call describe() method on df];
        B --> C[Print output of describe() method];
        </flow>
        """

        self.task = """
        You have been presented with a pandas dataframe named `df`.
        The dataframe df has already been defined and populated with the required data.
        The result of `print(df.head(1))` is:
        {}.
        Return the python code that acomplishes the following tasks: {}.
        Always include the import statements at the top of the code, and comments and print statement where necessary.
        When working with machine learning models, ensure that the target variable, which the model is intended to predict, is not included among the feature variables used to train the model.
        Make sure to also include a reflection on your answer and the code for mermaid diagram.
        Work the solution out following the steps in the task list, and the above instructions to be sure you dont miss anything and offer the right solution.
        """

        self.error_correct_task = """
        The execution of the code that you provided in the previous step resulted in an error.
        The error message is: {}
        Return a corrected python code that fixes the error.
        Always include the import statements at the top of the code, and comments and print statement where necessary.
        Make sure to also include a reflection on your answer and the code for the mermaid diagram.
        """

        self.debug_code_task = """
        Your job as an AI QA engineer is to inspect the given code and make sure that it meets its objective.
        Code:
        {}.
        Objective:
        {}.
        The dataframe df has already been defined and populated with the required data. 

        Your task is to examine the code line by line, and confirm that the code incorporates all numerical data, additional values, 
        and formulas including the correct operators as detailed in the objective, and to ensure that these formulas are accurately implemented and perform as expected. 
        Thoroughly examine each line of the code and refine it to optimize its accuracy and efficiency for its intended purpose. 
        After making the necessary adjustments, supply the complete, updated code. Do not use <code></code> from "Example Output:" below.
        Prefix the code with <code> and suffix the code with </code>.

        Provide a summary of your evaluation. Don’t include any code in the summary.
        Prefix the summary with <reflection> and suffix the summary with </reflection>.

        Example Input
        Task List:
        1. Identify the dataframe `df`.
        2. Call the `describe()` method on `df`.
        3. Print the output of the `describe()` method.

        Code: 
        # Identify the dataframe `df`
        # df has already been defined and populated with the required data

        # Call the `describe()` method on `df`
        df_description = df.describe()

        # Print the output of the `describe()` method
        print(df_description)

        Example Output:
        <code>
        import pandas as pd

        # Identify the dataframe `df`
        # df has already been defined and populated with the required data

        # Call the `describe()` method on `df`
        df_description = df.describe()

        # Print the output of the `describe()` method
        print(df_description)
        </code>

        <reflection>
        The provided Python script attempts to perform operations on a pandas DataFrame (df.describe()) without importing the necessary pandas library first. 
        This will result in a NameError being raised, indicating that "pandas" is not defined.
        Suggested Fix:
        The script should import pandas at the beginning. This can be done by adding the line import pandas as pd at the top of the script. 
        This will ensure that the pandas library is loaded into the Python environment and its methods are accessible to the script.        
        </reflection>
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
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {self.llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">Trying to determine the best method to analyse your data, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n> Calling Model: {self.llm}", "magenta"))
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

    def debug_code(self,code,question):
        # Initialize the messages list with a system message containing the task prompt
        debug_messages = [{"role": "system", "content": self.debug_code_task.format(code,question)}]

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {self.llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">I have now received the LLM response. I am going to check the returned code for any errors, bugs or inconsistencies, and correct it if necessary. Please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n> Calling Model: {self.llm}", "magenta"))
            cprint(f"\n> I have now received the LLM response. I am going to check the returned code for any errors, bugs or inconsistencies, and correct it if necessary. Please wait...\n", 'magenta', attrs=['bold'])

        # Function to display results nicely
        def display_task(debug_insight):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:blue;">I have finished debugging the code, below are my thoughts:</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{debug_insight}</pre></p><br>'))
                display(HTML(f'<p><b style="color:magenta;">I am proceeding to the execution...</b></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\n> I have finished debugging the code, below are my thoughts:\n{debug_insight}\n", 'magenta', attrs=['bold'])
                cprint(f"\n> I am proceeding to the execution...\n", 'magenta', attrs=['bold'])

        # Call the OpenAI API and handle rate limit errors
        try:
            llm_response, tokens_used = self.llm_call(debug_messages,temperature=0) # higher temperature results in more "creative" answers (sometimes too creative :-))
            
        except openai.error.RateLimitError:
            print(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)
            llm_response, tokens_used = self.llm_call(debug_messages)
        
        # Extract the code from the API response
        debugged_code,debug_insight,flow = self._extract_code(llm_response)       
        display_task(debug_insight)

        self.total_tokens_used.append(tokens_used)

        return debugged_code

    def pd_agent_converse(self, question=None):
        # Function to display results nicely
        def display_results(answer, code, reflection, flow, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:blue;">Answer:</b><br><pre style="color:black;"><b>{answer}</b></pre></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Here is the final code that accomplishes the task:</b><br><pre style="color:#555555;">{code}</pre></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Final Thoughts:</b><br><pre style="color:black; white-space: pre-wrap; font-weight: bold;">{reflection}</pre></p><br>'))
                if self.flow_diagram:
                    display(HTML(f'<p><b style="color:blue;">Below is my approch as a Flow chart:</b><br><img src="{self.mm(flow)}" alt="Analysis Flow"></img></p><br>'))
                display(HTML(f'<p><b style="color:blue;">Total Tokens Used:</b><br><span style="color:black;">{total_tokens_used_sum}</span></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\n> Answer:\n{answer}\n", 'green', attrs=['bold'])
                cprint(f"> Here is the final code that accomplishes the task:\n{code}\n", 'green', attrs=['bold'])
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
            display(HTML(f'<p style="color:magenta;">\nCalling Model: {self.llm}</p>'))
            display(HTML(f'<p><b style="color:magenta;">I have sent your request to the LLM and awaiting response, please wait...</b></p><br>'))
        else:
            # Other environment (like terminal)
            print(colored(f"\n> Calling Model: {self.llm}", "magenta"))
            cprint(f"\n> I have sent your request to the LLM and awaiting response, please wait...\n", 'magenta', attrs=['bold'])

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

        # Debug code
        if self.debug:
            code = self.debug_code(code, question)

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
    
