import os

class CodeGenPromptGenerator:
    def __init__(self, templates, model_dict):
        """
        Initialize with templates and model dictionary

        Args:
            templates (dict): Dictionary containing template strings:
                - code_generator_user_df_plan
                - code_generator_user_df_no_plan
                - code_generator_user_gen_plan
                - code_generator_user_gen_no_plan
            model_dict (dict): Dictionary containing model capabilities and formatting preferences
        """
        self.templates = templates
        self.model_dict = model_dict

    def get_formatting_style(self, model: str) -> str:
        """
        Get the formatting style (xml or text) for the given model
        """
        return self.model_dict.get(model, {}).get('templ_formating', 'text')

    def format_section(self, content: str, formatting_style: str, section_name: str) -> str:
        """
        Format a section based on formatting style

        Args:
            content (str): The content to format
            formatting_style (str): 'xml' or 'text'
            section_name (str): Name of the section (e.g., 'plan', 'dataframe')
        """
        if not content: # Return empty string if content is None or empty
            return ''

        # Determine if content should be yaml-formatted
        needs_yaml = any(keyword in section_name.lower() for keyword in ['plan', 'model', 'context']) # Added 'context'

        if formatting_style == 'xml':
            tag = section_name.lower().replace(' ', '_')
            if needs_yaml and content.strip(): # Ensure content is not just whitespace for yaml
                return f"<{tag}>\n```yaml\n{content}\n```\n</{tag}>"
            else:
                return f"<{tag}>\n{content}\n</{tag}>"
        else:  # text formatting
            header = section_name.upper()
            if needs_yaml and content.strip(): # Ensure content is not just whitespace for yaml
                return f"{header}:\n```yaml\n{content}\n```"
            else:
                return f"{header}:\n{content}"

    def select_template(self, analyst: str, planning: bool, model: str, reasoning_models: list) -> str:
        """
        Select the appropriate template based on input parameters
        """
        # Use no_plan template if planning is False or it's a reasoning model
        use_plan = planning and model not in reasoning_models

        if analyst == 'Data Analyst DF':
            return 'code_generator_user_df_plan' if use_plan else 'code_generator_user_df_no_plan'
        else:  # Data Analyst Generic
            return 'code_generator_user_gen_plan' if use_plan else 'code_generator_user_gen_no_plan'

    def generate_prompt(self, generated_datasets_path: str, analyst: str, planning: bool, model: str, reasoning_models: list,
                       plan_or_context: str, dataframe_head: str, auxiliary_datasets: str,
                       data_model: str, task: str, python_version: str, pandas_version: str,
                       plotly_version: str, previous_results: str, example_code: str) -> str:
        """
        Main method to generate the complete prompt
        """
        formatting_style = self.get_formatting_style(model)
        template_name = self.select_template(analyst, planning, model, reasoning_models)
        use_plan = planning and model not in reasoning_models

        # This is the string that instructs the LLM on how to format the path for saving datasets.
        generated_datasets_path_instruction = f"{generated_datasets_path}/<descriptive_name>.csv" if generated_datasets_path else ""

        formatted_sections = {
            'plan_or_context': self.format_section(
                plan_or_context,
                formatting_style,
                'Plan' if use_plan else 'Context' # Label for formatting
            ),
            'dataframe': self.format_section(dataframe_head, formatting_style, 'DataFrame'),
            'auxiliary_datasets': self.format_section(auxiliary_datasets, formatting_style, 'Auxiliary Datasets'),
            'generated_datasets_path_instruction': self.format_section(generated_datasets_path_instruction, formatting_style, 'Generated Datasets Path Instruction'),
            'data_model_and_helper_functions': self.format_section(data_model, formatting_style, 'Data Model and Helper Functions'),
            'task': self.format_section(task, formatting_style, 'Task'), # This is the main task description
            'python_version': self.format_section(python_version, formatting_style, 'Python Version'),
            'pandas_version': self.format_section(pandas_version, formatting_style, 'Pandas Version'),
            'plotly_version': self.format_section(plotly_version, formatting_style, 'Plotly Version'),
            'previous_results': self.format_section(previous_results, formatting_style, 'Previous Results'),
            'example_code': self.format_section(example_code, formatting_style, 'Example Code')
        }

        template_string = self.templates[template_name]
        args = []

        # Assemble arguments based on the specific template being used
        if template_name == 'code_generator_user_df_plan':
            # Expected 11 placeholders
            args = [
                formatted_sections['plan_or_context'],                   # 1. Plan
                formatted_sections['dataframe'],                         # 2. DataFrame Preview
                formatted_sections['auxiliary_datasets'],                # 3. Auxiliary Datasets
                formatted_sections['generated_datasets_path_instruction'],# 4. Generated Datasets Path Instruction
                formatted_sections['data_model_and_helper_functions'],   # 5. Data Model and Helper Functions
                formatted_sections['task'],                              # 6. Specific Task
                formatted_sections['python_version'],                    # 7. Python Version
                formatted_sections['pandas_version'],                    # 8. Pandas Version
                formatted_sections['plotly_version'],                    # 9. Plotly Version
                formatted_sections['previous_results'],                  # 10. Previous Results
                formatted_sections['example_code']                       # 11. Example Code / Final instructions
            ]
        elif template_name == 'code_generator_user_df_no_plan':
            # Expected 11 placeholders
            # For df_no_plan, the first {} is for context (which is plan_or_context, holding the task).
            args = [
                formatted_sections['plan_or_context'],                   # 1. Context (task description)
                formatted_sections['dataframe'],                         # 2. DataFrame Preview
                formatted_sections['auxiliary_datasets'],                # 3. Auxiliary Datasets
                formatted_sections['generated_datasets_path_instruction'],# 4. Generated Datasets Path Instruction
                formatted_sections['data_model_and_helper_functions'],   # 5. Data Model and Helper Functions
                formatted_sections['task'],                              # 6. Specific Task
                formatted_sections['python_version'],                    # 7. Python Version
                formatted_sections['pandas_version'],                    # 8. Pandas Version
                formatted_sections['plotly_version'],                    # 9. Plotly Version
                formatted_sections['previous_results'],                  # 10. Previous Results
                formatted_sections['example_code']                       # 11. Example Code / Final instructions
            ]
        elif template_name == 'code_generator_user_gen_plan':
            # Expected 8 placeholders
            args = [
                formatted_sections['python_version'],                    # 1. Python Version
                formatted_sections['pandas_version'],                    # 2. Pandas Version
                formatted_sections['plotly_version'],                    # 3. Plotly Version
                formatted_sections['plan_or_context'],                   # 4. Plan
                formatted_sections['task'],                              # 5. Specific Task
                formatted_sections['previous_results'],                  # 6. Previous Results
                formatted_sections['example_code'],                      # 7. Example Code
                formatted_sections['generated_datasets_path_instruction'] # 8. Generated Datasets Path Instruction
            ]
        elif template_name == 'code_generator_user_gen_no_plan':
            # Expected 7 placeholders
            # For gen_no_plan, plan_or_context is the task description for the first task-like placeholder
            args = [
                formatted_sections['python_version'],                    # 1. Python Version
                formatted_sections['pandas_version'],                    # 2. Pandas Version
                formatted_sections['plotly_version'],                    # 3. Plotly Version
                formatted_sections['task'],                              # 4. Specific Task
                formatted_sections['previous_results'],                  # 5. Previous Results
                formatted_sections['example_code'],                      # 6. Example Code
                formatted_sections['generated_datasets_path_instruction'] # 7. Generated Datasets Path Instruction
            ]
        else:
            # This case should ideally not be reached if select_template is comprehensive
            raise ValueError(f"Unknown or unhandled template_name: {template_name}")

        # Crucial: Verify argument count matches placeholder count in the template string
        num_placeholders = template_string.count('{}')
        if len(args) != num_placeholders:
            error_message = (
                f"Argument count mismatch for template '{template_name}'. "
                f"Expected {num_placeholders} placeholders, but got {len(args)} arguments.\n"
                f"This usually means the 'args' list in 'generate_prompt' is not correctly assembled for this template.\n"
                f"Template first 500 chars: {template_string[:500]}..."
            )

            raise ValueError(error_message)

        return template_string.format(*args)