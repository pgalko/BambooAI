
import os
import re
import sys
import io
import time
import openai
import pandas as pd
from termcolor import colored

class BambooAI:
    def __init__(self, df: pd.DataFrame, llm: str = 'gpt-3.5-turbo'):

        self.API_KEY = os.environ.get('OPENAI_API_KEY')
        self.MAX_ERROR_CORRECTIONS = 3

        self.df = df
        self.df_head = df.head(1)
    
        self.llm = llm

        self.task = """
        There is a pandas dataframe.
        The name of the dataframe is `df`.
        This is the result of `print(df.head(1))`:
        {}.

        Return the python code that prints out the answer to the following question : {}. 
        Prefix the python code with <code> and suffix the code with </code> .
        """

        self.error_correct_task = """
        The code you provided resulted in an error.
        The error message is: {}.
        The code you provided is: {}.
        The question was: {}.
        Return a corrected python code that fixes the error.
        Prefix the python code with <code> and suffix the code with </code>.
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

    def _extract_code(self, response: str, separator: str = "```") -> str:
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

        # Return the cleaned and extracted code
        return code.strip()

    def pd_agent_converse(self, question=None):
        # Initialize the messages list with a system message containing the task prompt
        messages = [{"role": "system", "content": self.task.format(self.df_head, "")}]

        # If a question is provided, skip the input prompt
        if question is not None:
            answer = self.pd_agent(question, messages, self.df)
            print(colored("\nAnswer:\n{}".format(answer), "green"))
            return

        # Start an infinite loop to keep asking the user for questions
        while True:
            # Prompt the user to enter a question or type 'exit' to quit
            question = input(colored("Enter your question or type 'exit' to quit: ", "cyan"))

            # If the user types 'exit', break out of the loop
            if question.strip().lower() == 'exit':
                break

            # Call the pd_agent method with the user's question, the messages list, and the dataframe
            answer = self.pd_agent(question, messages, self.df)

            # Print the answer returned by the pd_agent method
            print(colored("\nAnswer:\n{}".format(answer), "green"))


    def pd_agent(self, question, messages, df=None):
        # Add a user message with the updated task prompt to the messages list
        messages.append({"role": "user", "content": self.task.format(self.df_head, question)})

        # Call the OpenAI API and handle rate limit errors
        try:
            code, tokens_used = self.llm_call(messages)
        except openai.error.RateLimitError:
            print(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)
            code, tokens_used = self.llm_call(messages)

        # Extract the code from the API response
        code = self._extract_code(code)

        # Update the total tokens used
        self.total_tokens_used.append(tokens_used)
        total_tokens_used_sum = sum(self.total_tokens_used)

        # Redirect standard output to a StringIO buffer
        output = io.StringIO()
        sys.stdout = output

        # Initialize error correction counter
        error_corrections = 0

        # Try to execute the code and handle errors
        while error_corrections < self.MAX_ERROR_CORRECTIONS:
            try:
                messages.append({"role": "assistant", "content": code})
                exec(code)
                break
            except Exception as e:
                # Increment the error correction counter and update the messages list with the error
                error_corrections += 1
                messages.append({"role": "user", "content": self.error_correct_task.format(e, code, question)})

                # Attempt to correct the code and handle rate limit errors
                try:
                    code, tokens_used = self.llm_call(messages)
                    code = self._extract_code(code)
                    self.total_tokens_used.append(tokens_used)
                    total_tokens_used_sum = sum(self.total_tokens_used)
                except openai.error.RateLimitError:
                    print(
                        "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
                    )
                    time.sleep(10)
                    code, tokens_used = self.llm_call(messages)
                    code = self._extract_code(code)
                    self.total_tokens_used.append(tokens_used)
                    total_tokens_used_sum = sum(self.total_tokens_used)

        # Print the generated code
        print("\nCode:\n{}".format(code))

        # Restore standard output
        sys.stdout = sys.__stdout__

        # Print the total tokens used
        print(colored("\nTotal tokens used:{}".format(total_tokens_used_sum), "yellow"))

        # Get the output from the executed code
        answer = output.getvalue()

        return answer
    