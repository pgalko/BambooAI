import json
import re
from typing import List, Tuple
import textwrap
import yaml

def _normalize_indentation(code_segment: str) -> str:
    """Normalize the indentation of a code segment."""
    return textwrap.dedent(code_segment)

def find_main_block(code: str) -> Tuple[int, int, int]:
    """Find the start and end lines of the main block and its indentation level."""
    lines = code.splitlines()
    start_idx = None
    end_idx = None
    indent = 0
    
    for i, line in enumerate(lines):
        if 'if __name__ == "__main__"' in line or "if __name__ == '__main__'" in line:
            start_idx = i + 1  # Start after the if line
            base_indent = len(line) - len(line.lstrip())
            # Find first non-empty line in block to get indent
            for j in range(start_idx, len(lines)):
                if lines[j].strip():
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    break
            # Find the end of the block
            for j in range(start_idx, len(lines)):
                if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= base_indent:
                    end_idx = j
                    break
            if end_idx is None:  # If we didn't find the end, it's the last line
                end_idx = len(lines)
            break
            
    return start_idx, end_idx, indent

def process_main_block(code_lines: List[str], start_idx: int, end_idx: int, base_indent: int, blacklist: List[str]) -> List[str]:
    """Process the contents of the main block, preserving indentation."""
    processed_lines = []
    for line in code_lines[start_idx:end_idx]:
        # Skip empty or whitespace-only lines
        if not line.strip():
            continue
        # Skip lines with blacklisted items
        if any(banned in line for banned in blacklist):
            continue
        # Preserve the original relative indentation
        line_indent = len(line) - len(line.lstrip())
        if line_indent >= base_indent:
            # Keep the relative indentation from the base
            relative_indent = line_indent - base_indent
            processed_lines.append(" " * relative_indent + line.lstrip())
    return processed_lines

def _extract_code(response: str, analyst: str, provider: str) -> str:
    """Extract and sanitize code while preserving comments and structure."""
    blacklist = [
        'subprocess', 'sys', 'exec', 'socket', 'urllib',
        'shutil', 'pickle', 'ctypes', 'multiprocessing', 'tempfile', 'glob', 'pty',
        'commands', 'cgi', 'cgitb', 'xml.etree.ElementTree', 'builtins'
    ]
    
    # Extract code from markdown blocks
    # Replace <|im_sep|> with ``` to match the markdown code block syntax
    response = re.sub(re.escape("<|im_sep|>"), "```", response)
    # Find all code segments enclosed in triple backticks with "python"
    code_segments = re.findall(r'```python\n(\s*.*?)\s*```', response, re.DOTALL)
    # If no segments found, try without "python"
    if not code_segments:
      code_segments = re.findall(r'```(?:python\n|\n)(\s*.*?)\s*```', response, re.DOTALL)

    if not code_segments:
      return ""
    
    # Normalize the indentation for each code segment
    normalized_code_segments = [_normalize_indentation(segment) for segment in code_segments]

    # Combine the normalized code segments into a single string
    code = '\n\n'.join(normalized_code_segments).lstrip()

    # Split the code into lines
    lines = code.splitlines()
    
    # Process the code line by line
    processed_lines = []
    main_start, main_end, main_indent = find_main_block(code)
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Handle empty lines
        if not line.strip():
            processed_lines.append(line)
            i += 1
            continue
        
        # Handle main block
        if main_start and i == main_start - 1:  # We're at the if __name__ line
            main_content = process_main_block(lines, main_start, main_end, main_indent, blacklist)
            processed_lines.extend(main_content)
            i = main_end
            continue
            
        # Handle blacklisted imports
        pattern = r"\b(" + "|".join(blacklist) + r")\b" # Match whole words
        if re.search(pattern, line):
            processed_lines.append(f"# not allowed {line}")
            i += 1
            continue
            
        # Handle transformations
        if 'plt.savefig' in line:
            indent = len(line) - len(line.lstrip())
            line = ' ' * indent + 'plt.show()'
        #line = re.sub(r"df\s*=\s*pd\.read_csv\((.*?)\)", "", line) # Temporary disable #TODO
        line = re.sub(r'plt\.style\.use\s*\(\s*\'seaborn\'\s*\)', 'sns.set_style("whitegrid")', line)
        
        if analyst == "Data Analyst DF" and provider == "local":
            if re.search(r"data=pd\.", line):
                line = re.sub(r"\bdata\b", "df", line)
            line = re.sub(
                r"(?<![a-zA-Z0-9_-])df\s*=\s*pd\.DataFrame\((.*?)\)",
                "# The dataframe df has already been defined",
                line
            )
        
        processed_lines.append(line)
        i += 1
    
    # Clean up multiple empty lines
    result = '\n'.join(processed_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()

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

def _extract_expert(response: str) -> tuple:
    # Create a pattern to match any of the substrings
    pattern = r'Data Analyst|Research Specialist'
    
    # Extract YAML content from within triple-backticks
    yaml_segment = re.findall(r'```(?:yaml\s*)?(.*?)\s*```', response, re.DOTALL)
    # If no YAML segment is found, use the entire response
    yaml_content = yaml_segment[0] if yaml_segment else response

    try:
        data = yaml.safe_load(yaml_content)
        requires_dataset = data['requires_dataset']
        expert = data['expert']
        confidence = data['confidence']
        return expert, requires_dataset, confidence
    except (yaml.YAMLError, KeyError):
        # Fallback: try to match using regex if parsing fails or keys are missing
        match = re.search(pattern, response)
        if match:
            return match.group(), None, None
        else:
            return None, None, None

def _extract_analyst(response: str) -> tuple:
    # Create a pattern to match any of the substrings
    pattern = r'Data Analyst DF|Data Analyst Generic'
    
    # Extract YAML content from within triple-backticks
    yaml_segment = re.findall(r'```(?:yaml\s*)?(.*?)\s*```', response, re.DOTALL)
    # If no YAML segment is found, use the entire response
    yaml_content = yaml_segment[0] if yaml_segment else response

    try:
        data = yaml.safe_load(yaml_content)
        analyst = data['analyst']
        query_unknown = data['unknown']
        query_condition = data['condition']
        intent_breakdown = data['intent_breakdown']
        return analyst, query_unknown, query_condition, intent_breakdown
    except (yaml.YAMLError, KeyError):
        # Fallback: try to match using regex if parsing fails or keys are missing
        match = re.search(pattern, response)
        if match:
            return match.group(), None, None, None
        else:
            return None, None, None, None
        
def _extract_plan(response: str) -> str:

    yaml_segment = re.findall(r'```(?:yaml\s*)?(.*?)\s*```', response, re.DOTALL)

    if yaml_segment:
        return yaml_segment[-1]
    else:
        # Look for content that starts with a YAML root key and capture everything until the next root key. This is in case the YAML content is not enclosed in triple backticks.
        yaml_pattern = r'^([a-zA-Z_][a-zA-Z0-9_]*:(?:\n(?:[ ]{2}.*|\n)*)+)'
        yaml_content = re.findall(yaml_pattern, response, re.MULTILINE)
        
        if yaml_content:
            # Join all found YAML-like sections
            return '\n'.join(yaml_content)
    
    return ""

def _extract_data_model(response: str) -> str:

    yaml_segment = re.findall(r'```(?:yaml\s*)?(.*?)\s*```', response, re.DOTALL)

    if yaml_segment:
        return yaml_segment[-1]
    else:
        # Look for content that starts with a YAML root key and capture everything until the next root key. This is in case the YAML content is not enclosed in triple backticks.
        yaml_pattern = r'^([a-zA-Z_][a-zA-Z0-9_]*:(?:\n(?:[ ]{2}.*|\n)*)+)'
        yaml_content = re.findall(yaml_pattern, response, re.MULTILINE)
        
        if yaml_content:
            # Join all found YAML-like sections
            return '\n'.join(yaml_content)
    
    return response

# Function to remove examples from messages when no longer needed
def _remove_examples(messages: str) -> str:
    # Define the regular expression pattern
    pattern = 'EXAMPLE OUTPUT:\s*```python.*?```\s*'

    # Iterate over the list of dictionaries
    for dict in messages:
        # Access and clean up 'content' field
        if dict.get('role') == 'user' and 'content' in dict:
            dict['content'] = re.sub(pattern, '', dict['content'], flags=re.DOTALL)

    return messages

def _remove_all_except_task_xml(text):
    pattern = r'<task>(.*?)</task>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text  # Return the original text if no <task> tags are found

def _remove_all_except_task_text(text):
     # The pattern to search for is the string 'TASK:' followed by any characters until the next occurrence of the string 'Before we begin, here are the version specifications you need to adhere to:', 'PYTHON VERSION:', or the end of the text
    pattern = r'TASK:\s*\n\s*(.*?)(?=\n\s*(?:Before we begin, here are the version specifications you need to adhere to:|PYTHON VERSION:|$))'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text

def _remove_all_except_task_ontology_text(text):
    pattern = r'TASK:\s*\n\s*(.*?)(?=\n\s*Create a YAML structure with:)'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text