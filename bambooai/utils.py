from datetime import datetime, timezone
import yaml
import numpy as np


def ordinal(n):
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10, 'th')}"

def get_readable_date(date_obj=None, tz=None):
    if date_obj is None:
        date_obj = datetime.now().replace(tzinfo=timezone.utc)

    if tz:
        date_obj = date_obj.replace(tzinfo=tz)

    return date_obj.strftime(f"%a {ordinal(date_obj.day)} of %b %Y")

def inspect_dataframe(df, log_and_call_manager=None,chain_id=None,query=None):
    agent = "Dataframe Inspector"
    if log_and_call_manager:
        try:
            # Attempt package-relative import
            from . import models, prompts, df_ontology, output_manager
        except ImportError:
            # Fall back to script-style import
            import models, prompts, df_ontology, output_manager

        output_handler = output_manager.OutputManager()

        using_model,provider = models.get_model_name(agent)

        output_handler.display_tool_start(agent,using_model)

        # Get the ontology
        ontology = df_ontology.ontology

        prompt = prompts.dataframe_inspector_system.format(ontology, query)
            
        messages = [{"role": "user", "content": prompt}]

        llm_response = models.llm_stream(log_and_call_manager,messages, agent=agent, chain_id=chain_id)

        return llm_response
    
    else:
        # Create a dictionary to store column statistics
        stats_dict = {}
        # Iterate over each column in the dataframe
        for column in df.columns:
            # Gather common statistics
            col_stats = {
                'dtype': str(df[column].dtype),
                'count_of_values': int(df[column].count()),
                'count_of_nulls': int(df[column].isna().sum())
            }

            # Check if the column is numerical
            if np.issubdtype(df[column].dtype, np.number):
                col_stats['mean'] = float(df[column].mean())
            
            # Special handling for datetime columns
            elif np.issubdtype(df[column].dtype, np.datetime64):
                sorted_dates = np.sort(df[column].dropna())  # Sort dates and drop NaNs
                if len(sorted_dates) > 1:
                    intervals = np.diff(sorted_dates)  # Calculate differences between consecutive dates
                    col_stats['interval_between_records'] = str(np.mean(intervals))

            # Handle non-numerical columns
            else:
                non_null_values = df[column].dropna()
                if not non_null_values.empty:
                    col_stats['first_value'] = str(non_null_values.iloc[0])
                    col_stats['last_value'] = str(non_null_values.iloc[-1])

            # Add the stats to the main dictionary, using the column name as the key
            stats_dict[column] = col_stats
        # Convert dictionary to YAML format
        return yaml.dump(stats_dict, sort_keys=False, default_flow_style=False)
