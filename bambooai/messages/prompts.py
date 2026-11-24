# prompts.py
import os
import yaml
import importlib.resources
import warnings

_DEFAULT_PROMPTS_PACKAGE_PATH = "bambooai.messages"
_DEFAULT_PROMPTS_FILENAME = "default_prompts.yaml"

# The prompts by name: the loader makes an attribute of each name listed here and of no other, so a prompt in the file
# is listed here and read somewhere (a test holds the three to each other). The analyst's own prompts are not here:
# analyst/contract.md and the files beside it.
_EXPECTED_TEMPLATES = [
    "synthesis_infographic_template",
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