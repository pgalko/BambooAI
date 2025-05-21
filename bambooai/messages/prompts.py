import json
from pathlib import Path

class Prompts:
    default_example_output_df: str
    default_example_output_gen: str
    default_example_plan_df: str
    default_example_plan_gen: str
    expert_selector_system: str
    expert_selector_user: str
    analyst_selector_system: str
    analyst_selector_user: str
    planner_system: str
    planner_user_gen: str
    planner_user_df: str
    planner_user_gen_reasoning: str
    planner_user_df_reasoning: str
    theorist_system: str
    dataframe_inspector_system: str
    dataframe_inspector_user: str
    google_search_query_generator_system: str
    google_search_summarizer_system: str
    google_search_react_system: str
    code_generator_system_df: str
    code_generator_system_gen: str
    code_generator_user_df_plan: str
    code_generator_user_df_no_plan: str
    code_generator_user_gen_plan: str
    code_generator_user_gen_no_plan: str
    error_corector_system: str
    error_corector_system_reasoning: str
    error_corector_edited_system: str
    error_corector_edited_system_reasoning: str
    reviewer_system: str
    solution_summarizer_system: str
    solution_summarizer_custom_code_system: str
    plot_query: str
    plot_query_routing: str
    
    def __init__(self, config_file: str = None):
        self._load_default_prompts()
        if config_file:
            self.load_prompts(config_file)

    def _load_default_prompts(self):
        current_dir = Path(__file__).parent
        file_path = current_dir / 'default_prompts.json'
        self.load_prompts(file_path)
    
    def load_prompts(self, config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            templates = json.load(f)
        
        for key in templates:
            setattr(self, key, templates[key])