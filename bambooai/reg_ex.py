
import re

def _normalize_indentation(code_segment: str) -> str:
    # Determine the minimum indentation of non-empty lines
    lines = code_segment.strip().split('\n')
    min_indent = min(len(re.match(r'^\s*', line).group()) for line in lines if line.strip())
    
    # Remove the minimum indentation from each line
    return '\n'.join(line[min_indent:] for line in lines)

# Function to sanitize the LLM response, and extract the code.
def _extract_code(response: str, analyst: str, provider: str) -> str:
  
    # Use re.sub to replace all occurrences of the <|im_sep|> with the ```.
    response = re.sub(re.escape("<|im_sep|>"),"```", response)

    # Define a blacklist of Python keywords and functions that are not allowed
    blacklist = ['subprocess','sys','eval','exec','socket','urllib',
                'shutil','pickle','ctypes','multiprocessing','tempfile','glob','pty'
                'commands','cgi','cgitb','xml.etree.ElementTree','builtins'
                ]
        
    # Use a regular expression to find all code segments enclosed in triple backticks with "python"
    #code_segments = re.findall(r'```python\s*(.*?)\s*```', response, re.DOTALL)
    # Use a regular expression to find all code segments enclosed in triple backticks with or without "python"
    code_segments = re.findall(r'```(?:python\s*)?(.*?)\s*```', response, re.DOTALL)
    if not code_segments:
         code_segments = re.findall(r'\[PYTHON\](.*?)\[/PYTHON\]', response, re.DOTALL)

    # Normalize the indentation for each code segment
    normalized_code_segments = [_normalize_indentation(segment) for segment in code_segments]

    # Combine the normalized code segments into a single string
    code = '\n'.join(normalized_code_segments).lstrip()

    # Remove any instances of "df = pd.read_csv('filename.csv')" from the code
    code = re.sub(r"df\s*=\s*pd\.read_csv\((.*?)\)", "", code)
    
    # This is necessary for local OS models, as they are not as good as OpenAI models deriving the instruction from the promt
    if analyst == "Data Analyst DF" and provider == "local":
        # Replace all occurrences of "data" with "df" if "data=pd." is present
        if re.search(r"data=pd\.", code):
            code = re.sub(r"\bdata\b", "df", code)
        # Comment out the df instantiation if it is present in the generated code
        code = re.sub(r"(?<![a-zA-Z0-9_-])df\s*=\s*pd\.DataFrame\((.*?)\)", "# The dataframe df has already been defined", code)

    # Define the regular expression pattern to match the blacklist items
    pattern = r"^(.*\b(" + "|".join(blacklist) + r")\b.*)$"

    # Replace the blacklist items with comments
    code = re.sub(pattern, r"# not allowed \1", code, flags=re.MULTILINE)

    # Return the cleaned and extracted code
    return code.strip()

def _extract_rank(response: str) -> str:

    # Search for a pattern between <rank> and </rank> in the response
    match = re.search(r"<rank>(.*)</rank>", response)
    if match:
        # If a match is found, extract the rank between <rank> and </rank>
        rank = match.group(1)
    else:
        rank = ""

    # Return the cleaned and extracted code
    return rank.strip()

def _extract_expert(response: str) -> str:
    # Create a pattern to match any of the substrings
    pattern = r'Data Analyst|Data Analysis Theorist|Internet Research Specialist'
    
    # Use re.search to find the first match in the input string
    match = re.search(pattern, response)
    
    if match:
        # If a match is found, return it
        return match.group()
    else:
        # If no match is found, return None
        return None
    
def _extract_analyst(response: str) -> str:
    # Create a pattern to match any of the substrings
    pattern = r'Data Analyst DF|Data Analyst Generic'
    
    # Use re.search to find the first match in the input string
    match = re.search(pattern, response)
    
    if match:
        # If a match is found, return it
        return match.group()
    else:
        # If no match is found, return None
        return None

# Function to remove examples from messages when no longer needed
def _remove_examples(messages: str) -> str:
    # Define the regular expression pattern
    pattern = 'Example Output:\s*```python.*?```\s*'

    # Iterate over the list of dictionaries
    for dict in messages:
        # Access and clean up 'content' field
        if dict.get('role') == 'user' and 'content' in dict:
            dict['content'] = re.sub(pattern, '', dict['content'], flags=re.DOTALL)

    return messages