# prompts.py
import os
import yaml
import importlib.resources
import sys
import warnings

_DEFAULT_PROMPTS_PACKAGE_PATH = "bambooai.messages"
_DEFAULT_PROMPTS_FILENAME = "default_prompts.yaml"

_EXPECTED_TEMPLATES = [
    "default_example_output_df", "default_example_output_gen",
    "default_example_plan_df", "default_example_plan_gen",
    "semantic_memory_plan_example", "semantic_memory_code_example",
    "expert_selector_system", "expert_selector_user",
    "analyst_selector_system", "analyst_selector_user",
    "planner_system", "planner_user_gen", "planner_user_df",
    "planner_user_gen_reasoning", "planner_user_df_reasoning",
    "theorist_system", "dataframe_inspector_system", "dataframe_inspector_user",
    "google_search_query_generator_system", "google_search_react_system",
    "google_search_summarizer_system",
    "code_generator_system_df", "code_generator_system_gen",
    "code_generator_user_df_plan", "code_generator_user_df_no_plan",
    "code_generator_user_gen_plan", "code_generator_user_gen_no_plan",
    "error_corector_system", "error_corector_system_reasoning",
    "error_corector_edited_system", "error_corector_edited_system_reasoning",
    "reviewer_system", "solution_summarizer_system",
    "solution_summarizer_custom_code_system", "plot_query", "plot_query_routing"
]

class PromptManager:
    def __init__(self, custom_prompt_file_path: str = None):
        """
        Initializes the PromptManager.
        Args:
            custom_prompt_file_path (str, optional): Path to a custom prompts YAML file.
                                                     If None, only defaults are loaded.
        """
        self._prompts_loaded = False
        self.effective_custom_prompts_file = custom_prompt_file_path
        self._load_all_prompts()

    def _load_yaml_file(self, package_path, filename, is_default=True, direct_path=None):
        data = {}
        try:
            if is_default:
                with importlib.resources.open_text(package_path, filename, encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            elif direct_path and os.path.exists(direct_path):
                with open(direct_path, "r", encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            elif not is_default and direct_path: # Custom file specified but not found
                 warnings.warn(f"Custom prompt file specified but not found: {direct_path}", UserWarning)

        except (FileNotFoundError, ModuleNotFoundError) as e:
            if is_default:
                warnings.warn(
                    f"Default prompts file ('{package_path}/{filename}') not found. "
                    "Prompts relying on defaults may be empty.", UserWarning
                )
        except yaml.YAMLError as e:
            file_in_error = filename if is_default else direct_path
            warnings.warn(f"Error parsing YAML file '{file_in_error}': {e}. Check its format.", UserWarning)
        except Exception as e:
            file_in_error = filename if is_default else direct_path
            warnings.warn(f"Unexpected error loading YAML file '{file_in_error}': {e}", UserWarning)
        return data

    def _load_all_prompts(self):
        if self._prompts_loaded:
            return

        default_prompts_data = self._load_yaml_file(
            _DEFAULT_PROMPTS_PACKAGE_PATH, _DEFAULT_PROMPTS_FILENAME, is_default=True
        )
        
        custom_prompts_data = {}
        if self.effective_custom_prompts_file:
            custom_prompts_data = self._load_yaml_file(
                None, None, is_default=False, direct_path=self.effective_custom_prompts_file
            )
        
        for template_name in _EXPECTED_TEMPLATES:
            value = custom_prompts_data.get(template_name)
            if value is None:
                value = default_prompts_data.get(template_name)

            if not isinstance(value, str):
                if value is not None:
                    warnings.warn(
                        f"Prompt template '{template_name}' loaded as type {type(value)} instead of string. "
                        f"Using empty string. Value: {str(value)[:50]}...", UserWarning
                    )
                value = ""
            setattr(self, template_name, value)

        self._prompts_loaded = True