# prompts.py
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
    def __init__(self):
        """The prompts of the package's file, each an attribute by its name."""
        self._prompts_loaded = False
        self._load_all_prompts()

    def _load_yaml_file(self, package_path, filename):
        data = {}
        try:
            with importlib.resources.open_text(package_path, filename, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except (FileNotFoundError, ModuleNotFoundError) as e:
            warnings.warn(
                f"Default prompts file ('{package_path}/{filename}') not found. "
                "Prompts relying on defaults may be empty.", UserWarning
            )
        except yaml.YAMLError as e:
            warnings.warn(f"Error parsing YAML file '{filename}': {e}. Check its format.", UserWarning)
        except Exception as e:
            warnings.warn(f"Unexpected error loading YAML file '{filename}': {e}", UserWarning)
        return data

    def _load_all_prompts(self):
        if self._prompts_loaded:
            return

        default_prompts_data = self._load_yaml_file(_DEFAULT_PROMPTS_PACKAGE_PATH, _DEFAULT_PROMPTS_FILENAME)

        for template_name in _EXPECTED_TEMPLATES:
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