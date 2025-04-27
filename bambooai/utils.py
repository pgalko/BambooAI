from datetime import datetime, timezone
import yaml
import pandas as pd
import numpy as np
import textwrap
import io
import re
import sys
import pkg_resources
from typing import Optional, Union, Dict
import unicodedata


# Utility functions

def ordinal(n):
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10, 'th')}"

def get_readable_date(date_obj=None, tz=None):
    if date_obj is None:
        date_obj = datetime.now().replace(tzinfo=timezone.utc)

    if tz:
        date_obj = date_obj.replace(tzinfo=tz)

    return date_obj.strftime(f"%a {ordinal(date_obj.day)} of %b %Y")

def get_package_versions():
    # Get package versions
    versions = {
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    
    # Get installed packages
    installed_packages = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
    
    # Check for pandas
    versions['pandas_version'] = installed_packages.get('pandas', 'Not installed')
    
    # Check for plotly
    versions['plotly_version'] = installed_packages.get('plotly', 'Not installed')
    
    return versions

def dataframe_to_string(df: pd.DataFrame, 
                       num_rows: int = 5,
                       execution_mode: str = 'local',
                       df_id: Optional[str] = None,
                       executor_client=None) -> str:
    """
    Convert a DataFrame head to a string either locally or via executor API.
    Returns string representation of the DataFrame (5 rows).
    """
    
    if execution_mode == 'api' and df_id is not None:
        result = executor_client.dataframe_to_string(df_id, num_rows)
        if result is not None:
            return result
    
    first_row = 50 # Start at the 50th row, to eliminate any inconsitencies in the first few rows
    last_row = first_row + num_rows
    try:
        # Set display options to show all columns
        with pd.option_context('display.max_columns', None, 
                            'display.width', None,
                            'display.max_colwidth', None):
            # Create a string buffer and write the DataFrame to it
            buffer = io.StringIO()
            df.iloc[first_row:last_row].to_string(buf=buffer, index=False)
            
            # Get the string value and reset the buffer
            df_string = buffer.getvalue()
            buffer.close()
        
        return df_string
    except:
        return df.iloc[first_row:last_row].to_string(index=False)

def get_dataframe_columns(df: pd.DataFrame,
                         execution_mode: str = 'local',
                         df_id: Optional[str] = None,
                         executor_client=None) -> str:
    """
    Get DataFrame columns either locally or via executor API.
    Returns string of column names.
    """
    if execution_mode == 'api' and df_id is not None:
        result = executor_client.get_dataframe_columns(df_id)
        if result is not None:
            return ', '.join(result['columns'])
    
    return ', '.join(df.columns.tolist())

    
#This only works for sports data, otherwise it will return the original dataframe   
def computeDataframeSample(df: pd.DataFrame, 
                         execution_mode: str = 'local',
                         df_id: Optional[str] = None,
                         executor_client=None) -> pd.DataFrame:
    """
    Compute the index of a DataFrame either locally or via executor API.
    Returns a DataFrame with aggregated statistics for each activity.
    """
    
    if execution_mode == 'api' and df_id is not None:
        result = executor_client.compute_dataframe_sample(df_id)
        if result is not None:
            return result

    try:
        df_sample = df.head(100)
    except:
        return df

    return df_sample
    
def inspect_dataframe(df, log_and_call_manager=None, output_manager=None, chain_id=None, query=None, execution_mode='local', df_ontology=None, df_id=None, executor_client=None, messages=[]):
    agent = "Dataframe Inspector"
    df_inspector_messages = messages

    if log_and_call_manager:
        try:
            # Import prompts module
            try:
                # Attempt package-relative import
                from . import models, prompts
            except ImportError:
                # Fall back to script-style import
                import models, prompts
            
            # Read ontology from the text file path provided in df_ontology
            ontology = ""
            if df_ontology and isinstance(df_ontology, str):
                try:
                    with open(df_ontology, 'r') as file:
                        ontology = file.read()
                except Exception as e:
                    output_manager.display_system_messages(f"Error reading ontology file: {str(e)}")
                    raise
            
            output_manager.display_tool_start(agent, models.get_model_name(agent)[0], chain_id)

            def inject_content(template, **kwargs):
                for key, value in kwargs.items():
                    placeholder = f"<< {key} >>"
                    template = template.replace(placeholder, value)
                return template

            # Usage
            prompt = inject_content(prompts.dataframe_inspector_user, ontology=ontology, task=query)
                
            df_inspector_messages.append({"role": "user", "content": prompt})

            llm_response = models.llm_stream(log_and_call_manager, output_manager, df_inspector_messages, agent=agent, chain_id=chain_id)

            if llm_response:
                df_inspector_messages.append({"role": "assistant", "content": llm_response})

            return llm_response, df_inspector_messages
        except Exception:
            output_manager.display_system_messages(f"Error generating Data Model")
            raise
    else:
        return dataframe_to_string(df=df, execution_mode=execution_mode, df_id=df_id, executor_client=executor_client)
    
# Visualization functions

NODE_COLORS = {
    'container': 'none',
    'data': 'none',
    'function': 'none',
    'derived_object': 'none',
    'measurement': 'none',
    'default': 'none'
}

def get_node_style(node_type):
    fill_color = NODE_COLORS.get(node_type, NODE_COLORS['default'])
    return f'fill:{fill_color},stroke:#CCCCCC,stroke-width:2px'

def format_label(label, max_width=20):
    clean_label = re.sub(r'[^\w\s-]', '', label)
    wrapped_lines = textwrap.wrap(clean_label, width=max_width)
    return '<br/>' + '<br/>'.join(wrapped_lines)

def sanitize_id(label):
    sanitized = re.sub(r'[^\w\s-]', '_', label)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_').replace(' ', '_')

NODE_COLORS = {
    'container': 'none',
    'data': 'none',
    'function': 'none',
    'derived_object': 'none',
    'measurement': 'none',
    'default': 'none'
}

def get_node_style(node_type):
    fill_color = NODE_COLORS.get(node_type, NODE_COLORS['default'])
    return f'fill:{fill_color},stroke:#CCCCCC,stroke-width:2px'

def format_label(label, max_width=20):
    if not isinstance(label, str):
        label = str(label)
    
    # Normalize and convert to ASCII, using a simple replacement
    normalized = unicodedata.normalize('NFKD', label).encode('ascii', 'ignore').decode('ascii')
    
    clean_label = re.sub(r'[^\w\s-]', '', normalized)
    wrapped_lines = textwrap.wrap(clean_label, width=max_width)
    return '<br/>' + '<br/>'.join(wrapped_lines)
def sanitize_id(label):
    sanitized = re.sub(r'[^\w\s-]', '_', label)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_').replace(' ', '_')

def generate_model_graph(yaml_string):
    def sanitize_yaml(yaml_str):
        pattern = r'\s*allowedValues:.*\n'
        return re.sub(pattern, '\n', yaml_str)
    
    def create_node_label(node_data):
        if isinstance(node_data, dict):
            label = node_data.get('name', 'Unnamed')
            if node_data.get('category'):
                label += f"<br/>Category: {node_data['category']}"
            if node_data.get('type'):
                label += f"<br/>Type: {node_data['type']}"
            if node_data.get('units'):
                label += f"<br/>Units: {node_data['units']}"
            if node_data.get('recording_frequency'):
                label += f"<br/>Frequency: {node_data['recording_frequency']}"
            return label
        return format_label(str(node_data))

    def generate_mermaid_hierarchical(data):
        mermaid_code = [
            "graph TD",
            "%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'Arial' }}}%%",
            "classDef subgraphStyle fill:none,stroke:#CCCCCC,stroke-width:2px;"
        ]
        node_ids = {}
        derived_objects = []
        added_relationships = set()

        def create_node(name, label, node_type):
            if name not in node_ids:
                node_id = sanitize_id(name)
                node_ids[name] = node_id
                escaped_label = label.replace('"', '\\"')
                mermaid_code.append(f'{node_id}["{escaped_label}"]')
                mermaid_code.append(f"style {node_id} {get_node_style(node_type)}")
            return node_ids[name]

        def add_relationship(source, target, relationship_type, is_cross_domain=False):
            arrow = "-.->" if is_cross_domain else "-->"
            relationship = f"{source} {arrow}|{relationship_type}| {target}"
            if relationship not in added_relationships:
                mermaid_code.append(relationship)
                added_relationships.add(relationship)

        # Create Functions subgraph
        mermaid_code.append("subgraph Functions[Functions]")
        for function in data.get('functions', []):
            label = f"{function['name']}<br>Type: {function['type']}"
            create_node(function['name'], label, 'function')
        mermaid_code.append("end")

        # Create Activity Data subgraph
        mermaid_code.append("subgraph Activity_Data[Activity Data]")
        for item in data['data_hierarchy']:
            if 'Activity' in item['name']:
                label = create_node_label(item)
                create_node(item['name'], label, item.get('type', 'container'))
                if 'derived_objects' in item:
                    for derived in item['derived_objects']:
                        derived_objects.append((item['name'], derived))
        mermaid_code.append("end")

        # Create Wellness Data subgraph
        mermaid_code.append("subgraph Wellness_Data[Wellness Data]")
        for item in data['data_hierarchy']:
            if 'Wellness' in item['name']:
                label = create_node_label(item)
                create_node(item['name'], label, item.get('type', 'container'))
        mermaid_code.append("end")

        # Create measurement nodes for both domains
        for measurement in data.get('measurements', []):
            label = create_node_label(measurement)
            create_node(measurement['name'], label, 'measurement')

        # Add explicit containment relationships
        for item in data['data_hierarchy']:
            if item.get('contains'):
                for contained in item['contains']:
                    if item['name'] in node_ids and contained in node_ids:
                        add_relationship(node_ids[item['name']], node_ids[contained], "contains")

        # Add measurement relationships
        for measurement in data.get('measurements', []):
            associated_object = measurement.get('associated_object')
            if measurement['name'] in node_ids and associated_object in node_ids:
                add_relationship(node_ids[associated_object], node_ids[measurement['name']], "contains")

        # Add function relationships
        for function in data.get('functions', []):
            if 'computes' in function:
                for computed in function['computes']:
                    if computed in node_ids and function['name'] in node_ids:
                        add_relationship(node_ids[function['name']], node_ids[computed], "computes")
            if 'applies_to' in function:
                applies_to = function['applies_to']
                if isinstance(applies_to, str):
                    applies_to = [applies_to]
                for target in applies_to:
                    if target in node_ids:
                        add_relationship(node_ids[function['name']], node_ids[target], "applies to")

        # Add derived object relationships
        for parent, derived in derived_objects:
            if parent in node_ids and derived['name'] in node_ids:
                add_relationship(node_ids[parent], node_ids[derived['name']], "derives")

        # Add cross-domain relationships
        for relationship in data.get('relationships', []):
            if relationship.get('type') == 'references':
                source = relationship.get('from')
                target = relationship.get('to')
                if source in node_ids and target in node_ids:
                    add_relationship(node_ids[source], node_ids[target], 
                                  f"references", True)

        return mermaid_code

    try:
        sanitized_yaml_string = sanitize_yaml(yaml_string)
        data = yaml.safe_load(sanitized_yaml_string)
        mermaid_code = "\n".join(generate_mermaid_hierarchical(data))
        return mermaid_code
    except Exception as e:
        print(f"Error generating model graph: {str(e)}")
        return None

def generate_plan_graph(yaml_string):
    def should_reverse(key):
        reverse_sections = ['analysis_steps', 'data_operations', 'visualization_requirements']
        return any(section in key for section in reverse_sections)

    def generate_mermaid(data, parent=None, depth=0):
        mermaid_code = []
        if depth == 0:
            mermaid_code.extend([
                "graph TB",
                "%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '24px', 'fontFamily': 'Arial' }}}%%",
                "    %% Main structure",
                "    A[Plan]",
                "    style A fill:none,stroke:#CCCCCC,stroke-width:2px"
            ])
        
        items = list(data.items())
        if parent and should_reverse(parent):
            items.reverse()
            
        for key, value in items:
            node_id = sanitize_id(f"{parent}_{key}" if parent else key)
            content_node_id = f"{node_id}_content"  # Always create a content node ID
            
            if depth == 0:
                mermaid_code.extend([
                    f"    A --> {node_id}",
                    f"    subgraph {node_id}[{format_label(key)}]",
                    f"    style {node_id} fill:none,stroke:#CCCCCC,stroke-width:2px",
                    f"    {node_id}_space[ ]",
                    f"    style {node_id}_space height:30px,fill:none,stroke:none"
                ])
            
            if isinstance(value, dict):
                mermaid_code.extend(generate_mermaid(value, node_id, depth + 1))
            elif isinstance(value, list):
                if all(isinstance(item, str) for item in value):
                    list_id = f"{node_id}_list"
                    mermaid_code.extend([
                        f"    {list_id}[{format_label(key)}]",
                        f"    style {list_id} {get_node_style('data')}"
                    ])
                    items = list(enumerate(value))
                    if should_reverse(str(node_id)):
                        items.reverse()
                    for i, item in items:
                        item_id = sanitize_id(f"{node_id}_item_{i}")
                        mermaid_code.extend([
                            f"    {list_id} --> {item_id}[{format_label(item)}]",
                            f"    style {item_id} {get_node_style('measurement')}"
                        ])
                else:
                    items = list(enumerate(value))
                    if should_reverse(str(node_id)):
                        items.reverse()
                    for i, item in items:
                        if isinstance(item, dict):
                            sub_id = sanitize_id(f"{node_id}_{i}")
                            mermaid_code.append(f"    subgraph {sub_id}")
                            sub_items = list(item.items())
                            if should_reverse(str(node_id)):
                                sub_items.reverse()
                            for sub_key, sub_value in sub_items:
                                sub_node_id = sanitize_id(f"{sub_id}_{sub_key}")
                                content_sub_node_id = f"{sub_node_id}_content"  # Create content node ID for sub-nodes
                                mermaid_code.extend([
                                    f"        {content_sub_node_id}[{format_label(sub_key)}]",
                                    f"        style {content_sub_node_id} {get_node_style('function')}"
                                ])
                                if isinstance(sub_value, list):
                                    sub_value_items = list(enumerate(sub_value))
                                    if should_reverse(str(node_id)):
                                        sub_value_items.reverse()
                                    for j, sub_item in sub_value_items:
                                        sub_item_id = sanitize_id(f"{sub_node_id}_{j}")
                                        mermaid_code.extend([
                                            f"        {content_sub_node_id} --> {sub_item_id}[{format_label(sub_item)}]",
                                            f"        style {sub_item_id} {get_node_style('derived_object')}"
                                        ])
                                else:
                                    value_id = sanitize_id(f"{sub_node_id}_value")
                                    mermaid_code.extend([
                                        f"        {content_sub_node_id} --> {value_id}[{format_label(str(sub_value))}]",
                                        f"        style {value_id} {get_node_style('derived_object')}"
                                    ])
                            mermaid_code.extend([
                                "    end",
                                f"    style {sub_id} {get_node_style('function')}"
                            ])
                        else:
                            item_id = sanitize_id(f"{node_id}_item_{i}")
                            mermaid_code.extend([
                                f"    {content_node_id} --> {item_id}[{format_label(str(item))}]",
                                f"    style {item_id} {get_node_style('measurement')}"
                            ])
            else:
                value_id = sanitize_id(f"{node_id}_value")
                mermaid_code.extend([
                    f"    {content_node_id}[{format_label(key)}] --> {value_id}[{format_label(str(value))}]",
                    f"    style {content_node_id} fill:none,stroke:#CCCCCC,stroke-width:2px",
                    f"    style {value_id} {get_node_style('derived_object')}"
                ])
            
            if depth == 0:
                mermaid_code.append("    end")
        
        return mermaid_code

    try:
        data = yaml.safe_load(yaml_string)
        return "\n".join(generate_mermaid(data))
    except Exception as e:
        print(f"Error generating Mermaid diagram: {str(e)}")
        return None
    
