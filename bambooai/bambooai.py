
import os
import re
import sys
from contextlib import redirect_stdout
import io
import time
import openai
import pandas as pd
from termcolor import colored, cprint
from IPython.display import display, HTML

class BambooAI:
    def __init__(self, df: pd.DataFrame,max_conversations: int = 3 ,llm: str = 'gpt-3.5-turbo'):

        self.API_KEY = os.environ.get('OPENAI_API_KEY')
        self.MAX_ERROR_CORRECTIONS = 3
        # Set the maximum number of question/answer pairs to be kept in the conversation memmory
        self.MAX_CONVERSATIONS = (max_conversations*2) - 1

        self.original_df = df
        self.df = df.copy()  # make a copy of the dataframe
        self.df_head = self.original_df.head(1)
    
        self.llm = llm

        self.task = """
        There is a pandas dataframe.
        The name of the dataframe is `df`.
        This is the result of `print(df.head(1))`:
        {}.
        Return the python code that prints out the answer to the following question : {}.
        Always include the import statements at the top of the code, and comments where necessary. 
        Prefix the python code with <code> and suffix the code with </code> .
        Offer a short, couple of sentences reflection on your answer.
        Prefix the reflection with <reflection> and suffix the reflection with </reflection>.

        """

        self.error_correct_task = """
        The code you provided resulted in an error.
        The error message is: {}.
        The code you provided is: {}.
        The question was: {}.
        Return a corrected python code that fixes the error.
        Always include the import statements at the top of the code, and comments where necessary.
        Prefix the python code with <code> and suffix the code with </code>.
        Offer a short, couple of sentences reflection on your answer.
        Prefix the reflection with <reflection> and suffix the reflection with </reflection>.
        """

        openai.api_key = self.API_KEY
        self.total_tokens_used = []

        # print the model name in red
        print(colored("\nUsing Model: {}".format(llm), "red"))

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
    
    # Function to sanitize the output from the LLM
    def _extract_code(self,response: str, separator: str = "```") -> str:

        # Define a blacklist of Python keywords and functions that are not allowed
        blacklist = ['os','subprocess','sys','eval','exec','file','open','socket','urllib',
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

        # Set the initial value of code to the response
        code = response

        # If the response contains the separator, extract the code block between the separators
        if len(response.split(separator)) > 1:
            code = response.split(separator)[1]

        # Search for a pattern between <code> and </code> in the extracted code
        match = re.search(r"<code>(.*)</code>", code, re.DOTALL)
        if match:
            # If a match is found, extract the code between <code> and </code>
            code = match.group(1)
            # Remove the "python" or "py" prefix if present
            if re.match(r"^(python|py)", code):
                code = re.sub(r"^(python|py)", "", code)

        # If the code is between single backticks, extract the code between them
        if re.match(r"^`.*`$", code):
            code = re.sub(r"^`(.*)`$", r"\1", code)

        # Remove any instances of "df = pd.read_csv('filename.csv')" from the code
        code = re.sub(r"df\s*=\s*pd\.read_csv\('.*?'\)", "", code)
        
        # Remove any occurrences of df = pd.DataFrame() with any number of characters inside the parentheses.
        code = re.sub(r"df\s*=\s*pd\.DataFrame\(.*?\)", "", code)

        # Define the regular expression pattern to match the blacklist items
        pattern = r"^(.*\b(" + "|".join(blacklist) + r")\b.*)$"

        # Replace the blacklist items with comments
        code = re.sub(pattern, r"# not allowed \1", code, flags=re.MULTILINE)

        # Return the cleaned and extracted code
        return code.strip(), reflection.strip()


    def pd_agent_converse(self, question=None):
        # Initialize the messages list with a system message containing the task prompt
        messages = [{"role": "system", "content": self.task.format(self.df_head, "")}]

        # Function to display results nicely
        def display_results(answer, code, reflection, total_tokens_used_sum):
            if 'ipykernel' in sys.modules:
                # Jupyter notebook or ipython
                display(HTML(f'<p><b style="color:green;">Answer:</b><br><span style="color:green;">{answer}</span></p><br>'))
                display(HTML(f'<p><b style="color:green;">Code:</b><br><span style="color:green;">{code}</span></p><br>'))
                display(HTML(f'<p><b style="color:green;">Thoughts:</b><br><span style="color:green;">{reflection}</span></p><br>'))
                display(HTML(f'<p><b style="color:green;">Total Tokens Used:</b><br><span style="color:green;">{total_tokens_used_sum}</span></p><br>'))
            else:
                # Other environment (like terminal)
                cprint(f"\nAnswer:\n{answer}\n", 'green', attrs=['bold'])
                cprint(f"Code:\n{code}\n", 'green', attrs=['bold'])
                cprint(f"Thoughts:\n{reflection}\n", 'green', attrs=['bold'])
                cprint(f"Total tokens used:\n{total_tokens_used_sum}\n", 'yellow', attrs=['bold'])

        # If a question is provided, skip the input prompt
        if question is not None:
            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, reflection, total_tokens_used_sum = self.pd_agent(question, messages, self.df)
            display_results(answer, code, reflection, total_tokens_used_sum)
            return

        # Start an infinite loop to keep asking the user for questions
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

            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer, code, reflection, total_tokens_used_sum = self.pd_agent(question, messages, self.df)
            display_results(answer, code, reflection, total_tokens_used_sum)

    def pd_agent(self, question, messages, df=None):
        # Add a user message with the updated task prompt to the messages list
        messages.append({"role": "user", "content": self.task.format(self.df_head, question)})
        
        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'<p><b style="color:red;"></b><br><span style="color:red;"> Processing your request, please wait...</span></p><br>'))
        else:
            # Other environment (like terminal)
            cprint(f"\n> Processing your request, please wait...\n", 'red', attrs=['bold'])

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
        code,reflection = self._extract_code(llm_response)

        # Update the total tokens used
        self.total_tokens_used.append(tokens_used)
        total_tokens_used_sum = sum(self.total_tokens_used)

        # Initialize error correction counter
        error_corrections = 0

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
                    exec(code)
                    break
                except Exception as e:
                    # Increment the error correction counter and update the messages list with the error
                    error_corrections += 1
                    messages.append({"role": "user", "content": self.error_correct_task.format(e, code, question)})

                    # Attempt to correct the code and handle rate limit errors
                    try:
                        llm_response, tokens_used = self.llm_call(messages)
                        code,reflection = self._extract_code(llm_response)
                        self.total_tokens_used.append(tokens_used)
                        total_tokens_used_sum = sum(self.total_tokens_used)
                    except openai.error.RateLimitError:
                        print(
                            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
                        )
                        time.sleep(10)
                        llm_response, tokens_used = self.llm_call(messages)
                        code,reflection = self._extract_code(llm_response)
                        self.total_tokens_used.append(tokens_used)
                        total_tokens_used_sum = sum(self.total_tokens_used)

        # Get the output from the executed code
        answer = output.getvalue()

        # Reset the StringIO buffer
        output.truncate(0)
        output.seek(0)

        return answer, code, reflection, total_tokens_used_sum
    
