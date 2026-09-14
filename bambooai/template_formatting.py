from logger_config import get_logger
logger = get_logger(__name__)

class CodeGenPromptGenerator:
    def __init__(self, templates, model_dict):
        """
        Initialize with templates and model dictionary

        Args:
            templates (dict): Dictionary containing template strings:
                - code_generator_user_df_no_plan   (quick mode)
                - code_generator_user_gen_no_plan  (quick mode)
                - code_generator_user_df_findings  (after an investigation)
                - code_generator_user_gen_findings (after an investigation)
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

    def select_template(self, analyst: str, planning: bool, model: str, reasoning_models: list,
                        investigated: bool = False) -> str:
        """
        Select the appropriate template based on input parameters.

        `investigated` selects the consolidation templates: the Investigator has
        already run the analysis and the coder is reproducing it from findings
        plus the code that actually executed, not authoring one from a plan. It
        takes precedence over `planning` because there is no plan in that mode -
        there is a completed investigation, which is strictly more than a plan.
        """

        if investigated:
            return ('code_generator_user_df_findings' if analyst == 'Data Analyst DF'
                    else 'code_generator_user_gen_findings')
        if analyst == 'Data Analyst DF':
            return 'code_generator_user_df_no_plan'
        return 'code_generator_user_gen_no_plan'

    def generate_prompt(self, generated_datasets_path: str, analyst: str, planning: bool, model: str, reasoning_models: list,
                    plan_or_context: str, dataframe_head: str, auxiliary_datasets: str,
                    task: str, python_version: str, pandas_version: str,
                    plotly_version: str, previous_results: str, core_requirements: str,

                    investigated: bool = False, proven_code: str = None,
                    memory_cards: str = "") -> str:
        """
        Main method to generate the complete prompt.

        In investigation mode `plan_or_context` carries the technical FINDINGS
        and `proven_code` carries the kernel history - the blocks that actually
        executed during the investigation. The coder selects from that history
        rather than writing fresh code, which is why the two travel together:
        findings without the code cannot be reproduced, and code without the
        findings cannot be filtered down to what matters.
        """
        formatting_style = self.get_formatting_style(model)
        template_name = self.select_template(analyst, planning, model, reasoning_models,
                                             investigated=investigated)

        # This is the string that instructs the LLM on how to format the path for saving datasets.
        generated_datasets_path_instruction = f"{generated_datasets_path}/<descriptive_name>.csv" if generated_datasets_path else ""

        formatted_sections = {
            'plan_or_context': self.format_section(
                plan_or_context,
                formatting_style,
                'Findings' if investigated else 'Context'
            ),
            'proven_code': self.format_section(
                proven_code, formatting_style, 'Executed Code'
            ),
            'dataframe': self.format_section(dataframe_head, formatting_style, 'DataFrame'),
            'auxiliary_datasets': self.format_section(auxiliary_datasets, formatting_style, 'Auxiliary Datasets'),
            'generated_datasets_path_instruction': self.format_section(generated_datasets_path_instruction, formatting_style, 'Generated Datasets Path Instruction'),
            'task': self.format_section(task, formatting_style, 'Task'), # This is the main task description
            'python_version': self.format_section(python_version, formatting_style, 'Python Version'),
            'pandas_version': self.format_section(pandas_version, formatting_style, 'Pandas Version'),
            'plotly_version': self.format_section(plotly_version, formatting_style, 'Plotly Version'),
            'previous_results': self.format_section(previous_results, formatting_style, 'This Conversation So Far'),
            'core_requirements': self.format_section(core_requirements, formatting_style, 'Core Requirements'),
            # Deliberately NOT run through format_section: the block carries
            # its own heading, so empty memory leaves no orphaned section
            # header behind - the exact failure the retired Inspector slot
            # taught us about.
            'memory_cards': memory_cards or ''
        }

        template_string = self.templates[template_name]
        args = []

        # Assemble arguments based on the specific template being used
        if template_name == 'code_generator_user_df_findings':
            # 11 placeholders. Position 2 is
            # the executed code, which the plan templates have no equivalent of;
            # the data-model slot is gone, since the investigation supersedes it.
            args = [
                formatted_sections['plan_or_context'],                    # 1. Findings
                formatted_sections['proven_code'],                        # 2. Executed code
                formatted_sections['dataframe'],                          # 3. DataFrame preview
                formatted_sections['auxiliary_datasets'],                 # 4. Auxiliary datasets
                formatted_sections['generated_datasets_path_instruction'],# 5. Save path
                formatted_sections['task'],                               # 6. Original question
                formatted_sections['python_version'],                     # 7.
                formatted_sections['pandas_version'],                     # 8.
                formatted_sections['plotly_version'],                     # 9.
                # previous_results is deliberately absent. It carries earlier
                # chains in this thread, and a follow-up investigation has
                # already extended the same kernel and ledger - so the coder
                # would receive that history twice, in two forms, with nothing
                # marking which is current if the investigation revised an
                # earlier conclusion. The findings are the authority.
                formatted_sections['core_requirements']                   # 11.
            ]
        elif template_name == 'code_generator_user_gen_findings':
            args = [
                formatted_sections['plan_or_context'],                    # 1. Findings
                formatted_sections['proven_code'],                        # 2. Executed code
                formatted_sections['dataframe'],                          # 3. (empty in gen mode)
                formatted_sections['auxiliary_datasets'],                 # 4.
                formatted_sections['generated_datasets_path_instruction'],# 5.
                formatted_sections['task'],                               # 6.
                formatted_sections['python_version'],                     # 7.
                formatted_sections['pandas_version'],                     # 8.
                formatted_sections['plotly_version'],                     # 9.
                # previous_results is deliberately absent. It carries earlier
                # chains in this thread, and a follow-up investigation has
                # already extended the same kernel and ledger - so the coder
                # would receive that history twice, in two forms, with nothing
                # marking which is current if the investigation revised an
                # earlier conclusion. The findings are the authority.
                formatted_sections['core_requirements']                   # 11.
            ]
        elif template_name == 'code_generator_user_df_no_plan':
            # 11 placeholders. The data-model slot went with the Dataframe
            # Inspector: quick mode has no memory extract yet (step 22), and a heading that
            # promised one and then showed nothing was worse than silence.
            args = [
                formatted_sections['plan_or_context'],                   # 1. Context (task description)
                formatted_sections['dataframe'],                         # 2. DataFrame Preview
                formatted_sections['auxiliary_datasets'],                # 3. Auxiliary Datasets
                formatted_sections['generated_datasets_path_instruction'],# 4. Generated Datasets Path Instruction
                formatted_sections['memory_cards'],                      # 5. Learned methods (memory), whole cards
                formatted_sections['task'],                              # 6. Specific Task
                formatted_sections['python_version'],                    # 7. Python Version
                formatted_sections['pandas_version'],                    # 8. Pandas Version
                formatted_sections['plotly_version'],                    # 9. Plotly Version
                formatted_sections['previous_results'],                  # 10. Previous Results
                formatted_sections['core_requirements']                  # 12. Core Requirements
            ]
        elif template_name == 'code_generator_user_gen_no_plan':
            # Expected 8 placeholders
            # For gen_no_plan, plan_or_context is the task description for the first task-like placeholder
            args = [
                formatted_sections['python_version'],                    # 1. Python Version
                formatted_sections['pandas_version'],                    # 2. Pandas Version
                formatted_sections['plotly_version'],                    # 3. Plotly Version
                formatted_sections['memory_cards'],                      # 4. Learned methods (memory), whole cards
                formatted_sections['task'],                              # 5. Specific Task
                formatted_sections['previous_results'],                  # 5. Previous Results
                formatted_sections['generated_datasets_path_instruction'],# 7. Generated Datasets Path Instruction
                formatted_sections['core_requirements']                # 8. Core Requirements
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