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
        if not content:
            return ''
        
        # Determine if content should be yaml-formatted
        needs_yaml = any(keyword in section_name.lower() for keyword in ['plan', 'model'])
        
        if formatting_style == 'xml':
            tag = section_name.lower().replace(' ', '_')
            if needs_yaml:
                return f"<{tag}>\n```yaml\n{content}\n```\n</{tag}>"
            else:
                return f"<{tag}>\n{content}\n</{tag}>"
        else:  # text formatting
            header = section_name.upper()
            if needs_yaml:
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

    def generate_prompt(self, analyst: str, planning: bool, model: str, reasoning_models: list, 
                       plan_or_context: str, dataframe_head: str, auxiliary_datasets: str, 
                       data_model: str, task: str, python_version: str, pandas_version: str, 
                       plotly_version: str, previous_results: str, example_code: str) -> str:
        """
        Main method to generate the complete prompt
        """
        # Get formatting style from model_dict
        formatting_style = self.get_formatting_style(model)
        
        # Select template
        template_name = self.select_template(analyst, planning, model, reasoning_models)
        use_plan = planning and model not in reasoning_models
        
        # Format each section according to the model's style
        formatted_sections = {
            'plan_context': self.format_section(
                plan_or_context, 
                formatting_style, 
                'plan' if use_plan else 'context'
            ),
            'dataframe': self.format_section(dataframe_head, formatting_style, 'dataframe'),
            'auxiliary_datasets': self.format_section(auxiliary_datasets, formatting_style, 'auxiliary_datasets'),
            'data_model_and_helper_functions': self.format_section(data_model, formatting_style, 'data_model_and_helper_functions'),
            'task': self.format_section(task, formatting_style, 'task'),
            'python_version': self.format_section(python_version, formatting_style, 'python_version'),
            'pandas_version': self.format_section(pandas_version, formatting_style, 'pandas_version'),
            'plotly_version': self.format_section(plotly_version, formatting_style, 'plotly_version'),
            'previous_results': self.format_section(previous_results, formatting_style, 'previous_results'),
            'example_code': self.format_section(example_code, formatting_style, 'examples')
        }
        
        # Get the template string
        template_string = self.templates[template_name]
        
        # Prepare arguments based on analyst type
        if analyst == 'Data Analyst DF':
            args = [
                formatted_sections['plan_context'],
                formatted_sections['dataframe'],
                formatted_sections['auxiliary_datasets'],
                formatted_sections['data_model_and_helper_functions'],
                formatted_sections['task'],
                formatted_sections['python_version'],
                formatted_sections['pandas_version'],
                formatted_sections['plotly_version'],
                formatted_sections['previous_results'],
                formatted_sections['example_code']
            ]
        else:  # Data Analyst Generic
            args = [
                formatted_sections['python_version'],
                formatted_sections['pandas_version'],
                formatted_sections['plotly_version'],
                formatted_sections['plan_context'],
                formatted_sections['task'],
                formatted_sections['previous_results'],
                formatted_sections['example_code']
            ]
        
        # Return formatted template
        return template_string.format(*args)