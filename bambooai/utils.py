from datetime import datetime, timezone
import yaml
import pandas as pd
import numpy as np
import textwrap
import io
import os
import re
import sys
import pkg_resources
from typing import Optional, Union, Dict, List
import unicodedata
import pyarrow.parquet as pq
import csv
import logging # For better debugging

# Configure basic logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


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
    
    first_row = 25 # Start at the n'th row, to eliminate any inconsitencies in the first few rows
    # Ensure we don't exceed the DataFrame length
    if first_row + num_rows*2 > len(df):
        first_row = 1 # Start from the first row as the default

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
    
def aux_datasets_to_string(file_paths: List[str],
                           num_rows: int = 5,
                           execution_mode: str = 'local',
                           executor_client=None) -> str:
    """
    Load and preview the first num_rows from each dataset in file_paths
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.aux_datasets_to_string(file_paths=file_paths, num_rows=num_rows)
        if api_result is not None:
            return api_result

    # Local execution
    result = []
    if not file_paths:
        return "No auxiliary datasets provided."
    
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        
        try:
            if not os.path.exists(path):
                result.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                df = pd.read_csv(path, nrows=num_rows)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                # Read only the first batch (up to num_rows)
                # Ensure there are row groups to read
                if parquet_file.num_row_groups > 0:
                    df = parquet_file.read_row_group(0, columns=parquet_file.schema.names).to_pandas()
                    if len(df) > num_rows: # Slice if the row group is larger
                        df = df.iloc[:num_rows]
                else: # Handle empty parquet file
                    df = pd.DataFrame(columns=parquet_file.schema.names) # Empty df with correct columns
            else:
                result.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            buffer = io.StringIO()
            with pd.option_context('display.max_columns', None, 
                                  'display.width', None,
                                  'display.max_colwidth', None):
                df.to_string(buf=buffer, index=False)
            
            result.append(f"{i}.\nPath: {path}\nHead:\n{buffer.getvalue()}")
            
        except Exception as e:
            result.append(f"{i}.\nPath: {path}\nError: {str(e)}")
    
    return "\n\n".join(result)

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

def get_aux_datasets_columns(file_paths: List[str],
                             execution_mode: str = 'local',
                             executor_client=None) -> str:
    """
    Extract only the column names from each dataset in file_paths
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.get_aux_datasets_columns(file_paths=file_paths)
        if api_result is not None:
            return api_result
        # Fallback or error handling

    # Local execution
    result = []
    if not file_paths:
        return "No auxiliary datasets provided."
    
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        
        try:
            if not os.path.exists(path):
                result.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                with open(path, 'r', newline='', encoding='utf-8') as csvfile: # Specify encoding
                    reader = csv.reader(csvfile)
                    columns = next(reader)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                columns = parquet_file.schema.names
            else:
                result.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            columns_str = ", ".join(columns)
            result.append(f"{i}.\nPath: {path}\nColumns:\n{columns_str}")
            
        except StopIteration: # Handles empty CSV file
             result.append(f"{i}.\nPath: {path}\nError: CSV file is empty or has no header")
        except Exception as e:
            result.append(f"{i}.\nPath: {path}\nError: {str(e)}")
    
    return "\n\n".join(result)
 
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

def compute_aux_dataset_sample(file_paths: List[str],
                               num_rows: int = 100,
                               execution_mode: str = 'local',
                               executor_client=None) -> List[str]: # Returns list of HTML strings
    """
    Load a sample of each dataset in file_paths and convert to HTML
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.compute_aux_dataset_sample(file_paths=file_paths, num_rows=num_rows)
        if api_result is not None:
            return api_result 
        # Fallback or error handling

    # Local execution
    html_results = []
    if not file_paths: # Handle empty file_paths list
        error_df = pd.DataFrame([{"Error": "No auxiliary dataset paths provided."}])
        html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
        return html_results

    for path in file_paths:
        file_ext = os.path.splitext(path)[1].lower()
        
        try:
            if not os.path.exists(path):
                df = pd.DataFrame([{"Error": f"File not found: {os.path.basename(path)}"}])
            elif file_ext == '.csv':
                df = pd.read_csv(path, nrows=num_rows)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                if parquet_file.num_row_groups > 0:
                    first_row_group_reader = parquet_file.reader.read_row_group(0)
                    df = first_row_group_reader.to_pandas(use_threads=True)
                    if len(df) > num_rows:
                        df = df.head(num_rows)
                else: 
                    df = pd.DataFrame([{"Info": f"Parquet file is empty: {os.path.basename(path)}"}])
            else:
                df = pd.DataFrame([{"Error": f"Unsupported file format: {file_ext}"}])
            
            html = df.to_html(classes='dataframe', border=0, index=False)
            html_results.append(html)
            
        except Exception as e:
            error_df = pd.DataFrame([{"Error": f"Failed to process {os.path.basename(path)}: {str(e)}"}])
            html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
    
    return html_results
    
def inspect_dataframe(df, prompt_manager=None, log_and_call_manager=None, output_manager=None, chain_id=None, query=None, execution_mode='local', df_ontology=None, df_id=None, aux_file_paths=None, executor_client=None, messages=[]):
    agent = "Dataframe Inspector"
    df_inspector_messages = messages

    if log_and_call_manager:
        try:
            from bambooai import models

            # Generate the DataFrame preview and auxiliary datasets preview
            primary_df_head = dataframe_to_string(df=df, execution_mode=execution_mode, df_id=df_id, executor_client=executor_client)
            auxiliary_datasets_heads = aux_datasets_to_string(file_paths=aux_file_paths, execution_mode=execution_mode, executor_client=executor_client)
            
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

            prompt = inject_content(prompt_manager.dataframe_inspector_user, ontology=ontology, dataframe_preview=primary_df_head, auxiliary_datasets=auxiliary_datasets_heads, task=query)
                
            df_inspector_messages.append({"role": "user", "content": prompt})

            llm_response = models.llm_stream(prompt_manager, log_and_call_manager, output_manager, df_inspector_messages, agent=agent, chain_id=chain_id)

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
    def create_node_label(node_data, node_name_override=None):
        label_parts = []
        primary_name = node_name_override if node_name_override else node_data.get('name', 'Unnamed')
        if not primary_name: 
            primary_name = "Unnamed_Node_In_Label"
            # This warning is useful if it happens
            logging.warning(f"Node data missing 'name', using '{primary_name}' in label. Data: {str(node_data)[:100]}...")


        label_parts.append(f"<b>{primary_name}</b>") 
        props_to_include_map = {
            'type': 'Type',
            'dataset_source_identifier': 'Source ID',
            'domain_label': 'Domain',
            'category': 'Category',
            'units': 'Units',
            'recording_frequency': 'Frequency',
            'role_in_grouping': 'Grouping Role',
            'derivation_method': 'Derived By'
        }
        for key, display_name in props_to_include_map.items():
            if node_data.get(key):
                prop_value = str(node_data[key])
                if len(prop_value) > 40 and key not in ['role_in_grouping', 'derivation_method']:
                     prop_value = prop_value[:37] + "..."
                elif len(prop_value) > 60 : 
                     prop_value = prop_value[:57] + "..."
                label_parts.append(f"{display_name}: {prop_value}")
        description = node_data.get('description')
        if description:
            desc_text = str(description)
            if len(desc_text) < 50:
                label_parts.append(f"Desc: {desc_text}")
            else:
                label_parts.append(f"Desc: {desc_text[:47]}...")
        return '<br/>'.join(label_parts)

    def generate_mermaid_hierarchical(data):
        mermaid_code = [
            "graph TD",
            "%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '12px', 'fontFamily': 'Arial', 'nodeBorder': '#777777', 'lineColor': '#777777', 'textColor': '#333333'}}}%%",
            "classDef subgraphStyle fill:none,stroke:#AAAAAA,stroke-width:2px,color:#555555;"
        ]
        node_ids = {} 
        added_relationships = set() 

        def define_node(original_name, display_label_str, node_type_hint):
            if not original_name: # Should be a string
                logging.error(f"Attempted to define a node with no/empty original_name. Label: '{display_label_str[:50]}...', Type: '{node_type_hint}'. Skipping node.")
                return None 

            node_id = sanitize_id(original_name)
            if original_name not in node_ids: 
                # logging.info(f"Defining node: Original='{original_name}', ID='{node_id}', Type='{node_type_hint}'") # Minimized
                node_ids[original_name] = node_id
                escaped_label = display_label_str.replace('"', '"') 
                mermaid_code.append(f'    {node_id}["{escaped_label}"]')
                style_type = node_type_hint or 'default'
                mermaid_code.append(f"    style {node_id} {get_node_style(style_type)}")
            return node_id

        # --- Phase 1: Node Definition ---
        node_definition_sources = [
            (data.get('data_hierarchy', []), lambda item: item.get('type', 'container')),
            (data.get('keys', []), lambda item: 'key'),
            (data.get('measurements_attributes', []), lambda item: 'measurement'),
            (data.get('components_sub_entities', []), lambda item: item.get('type', 'component')),
        ]

        for item_list, type_extractor_func in node_definition_sources:
            for item_data in item_list:
                if not isinstance(item_data, dict):
                    logging.warning(f"Skipping non-dictionary item in node definition source: {str(item_data)[:100]}...")
                    continue
                node_name = item_data.get('name')
                if not isinstance(node_name, str) or not node_name: # Ensure name is a non-empty string
                    logging.warning(f"Item missing 'name' or name is not a string, cannot define node: {str(item_data)[:100]}...")
                    continue
                node_type = type_extractor_func(item_data)
                label_str = create_node_label(item_data)
                define_node(node_name, label_str, node_type)
                
                if 'derived_objects' in item_data and item_list is data.get('data_hierarchy', []): # Check if item_list is indeed data_hierarchy
                    for derived_obj_data in item_data.get('derived_objects',[]): 
                        if not isinstance(derived_obj_data, dict):
                            logging.warning(f"Skipping non-dictionary derived_object: {str(derived_obj_data)[:100]}...")
                            continue
                        derived_name = derived_obj_data.get('name')
                        if not isinstance(derived_name, str) or not derived_name:
                            logging.warning(f"Derived object missing 'name' or name is not a string: {str(derived_obj_data)[:100]}...")
                            continue
                        derived_type = derived_obj_data.get('type', 'derived_object') 
                        derived_label_str = create_node_label(derived_obj_data)
                        define_node(derived_name, derived_label_str, derived_type)
        
        if 'functions' in data:
            for function_data in data.get('functions', []):
                if not isinstance(function_data, dict):
                    logging.warning(f"Skipping non-dictionary function item: {str(function_data)[:100]}...")
                    continue
                func_name = function_data.get('name')
                if not isinstance(func_name, str) or not func_name:
                    logging.warning(f"Function item missing 'name' or name is not a string: {str(function_data)[:100]}...")
                    continue
                func_label_parts = [f"<b>{func_name}</b>"]
                if function_data.get('rdfs_comment'):
                    comment = str(function_data['rdfs_comment'])
                    func_label_parts.append(f"Desc: {comment[:60] + '...' if len(comment) > 60 else comment}")
                func_label_str = "<br/>".join(func_label_parts)
                define_node(func_name, func_label_str, 'function')
        
        # logging.info(f"Defined node_ids map: {node_ids}") # Minimized

        # --- Phase 2: Subgraph Definition ---
        domain_groups = {}
        if 'data_hierarchy' in data:
            for item_data in data.get('data_hierarchy', []):
                if not isinstance(item_data, dict) or not item_data.get('name'): continue 
                domain_title = item_data.get('domain_label', 'Uncategorized_Data') 
                if not isinstance(domain_title, str): domain_title = str(domain_title) # Ensure string for sanitize_id

                if domain_title not in domain_groups:
                    domain_groups[domain_title] = []
                
                item_name = item_data['name']
                if item_name in node_ids: 
                    if node_ids[item_name] not in domain_groups[domain_title]:
                        domain_groups[domain_title].append(node_ids[item_name])
                
                if 'derived_objects' in item_data:
                    for derived_obj_data in item_data.get('derived_objects',[]):
                        if isinstance(derived_obj_data, dict) and derived_obj_data.get('name') in node_ids:
                            derived_node_id = node_ids[derived_obj_data['name']]
                            if derived_node_id not in domain_groups[domain_title]:
                                domain_groups[domain_title].append(derived_node_id)

        if 'functions' in data and any(isinstance(f, dict) and f.get('name') in node_ids for f in data.get('functions',[])):
            mermaid_code.append("subgraph Functions_Domain [Functions]")
            for function_data in data.get('functions', []):
                if isinstance(function_data, dict) and function_data.get('name') in node_ids:
                     mermaid_code.append(f"        {node_ids[function_data['name']]}")
            mermaid_code.append("    end")
            mermaid_code.append(f"    class Functions_Domain subgraphStyle;")

        for domain_title, nodes_in_domain_group in domain_groups.items():
            subgraph_id = sanitize_id(f"{domain_title}_Domain") 
            formatted_subgraph_title = format_label(domain_title, max_width=30).replace('<br/>', ' ').replace('<br>', ' ') 
            mermaid_code.append(f"subgraph {subgraph_id} [{formatted_subgraph_title}]")
            for node_id_in_group in nodes_in_domain_group:
                mermaid_code.append(f"        {node_id_in_group}")
            mermaid_code.append("    end")
            mermaid_code.append(f"    class {subgraph_id} subgraphStyle;")
        
        # --- Phase 3: Relationship Drawing ---
        def add_relationship(source_original_name, target_original_name, relationship_label, is_dashed=False):
            if not (isinstance(source_original_name, str) and source_original_name) or \
               not (isinstance(target_original_name, str) and target_original_name):
                logging.warning(f"Skipping relationship '{relationship_label}' due to invalid/empty source/target name. Source='{source_original_name}', Target='{target_original_name}'")
                return

            if source_original_name in node_ids and target_original_name in node_ids:
                source_id = node_ids[source_original_name]
                target_id = node_ids[target_original_name]
                
                rel_display_label = str(relationship_label) # Ensure it's a string
                rel_display = sanitize_id(rel_display_label).replace("_", " ")
                if not rel_display: rel_display = "related" # Fallback for empty label after sanitize

                relationship_signature = (source_id, target_id, rel_display) 
                
                if relationship_signature not in added_relationships:
                    arrow = "-.->" if is_dashed else "-->"
                    mermaid_code.append(f"    {source_id} {arrow}|{rel_display}| {target_id}")
                    added_relationships.add(relationship_signature)
                    # logging.info(f"Added relationship: {source_original_name} --{rel_display} ({'dashed' if is_dashed else 'solid'})--> {target_original_name}") # Minimized
            else:
                # This warning is important if relationships are expected but nodes are missing
                logging.warning(f"Cannot draw relationship '{relationship_label}' between '{source_original_name}' and '{target_original_name}'. One or both nodes not found in defined node_ids. Source defined: {source_original_name in node_ids}, Target defined: {target_original_name in node_ids}")

        # 3a. Data Hierarchy 'contains' and 'derived_objects'
        if 'data_hierarchy' in data:
            for item_data in data.get('data_hierarchy',[]):
                if not isinstance(item_data, dict) or not item_data.get('name'): continue
                parent_name = item_data['name']
                if item_data.get('contains'):
                    contained_items_refs = item_data['contains']
                    if not isinstance(contained_items_refs, list): contained_items_refs = [contained_items_refs]
                    for contained_ref in contained_items_refs:
                        contained_name = contained_ref if isinstance(contained_ref, str) else (contained_ref.get('name') if isinstance(contained_ref, dict) else None)
                        if contained_name: # Ensure contained_name is valid
                            add_relationship(parent_name, contained_name, "contains")
                if 'derived_objects' in item_data:
                    for derived_obj_data in item_data.get('derived_objects',[]):
                        if isinstance(derived_obj_data, dict) and derived_obj_data.get('name'):
                            derived_name = derived_obj_data['name']
                            add_relationship(parent_name, derived_name, "derives")
                            comp_func_refs = derived_obj_data.get('canBeComputedUsingFunction')
                            if comp_func_refs:
                                if not isinstance(comp_func_refs, list): comp_func_refs = [comp_func_refs]
                                for func_name_ref in comp_func_refs:
                                    if isinstance(func_name_ref, str) and func_name_ref: 
                                        add_relationship(func_name_ref, derived_name, "computes")


        # 3b. Keys 'associated_object' and 'hasRelation'
        if 'keys' in data:
            for key_data in data.get('keys',[]):
                if not isinstance(key_data, dict) or not key_data.get('name'): continue
                key_name = key_data['name']
                associated_obj_ref = key_data.get('associated_object') 
                if isinstance(associated_obj_ref, str) and associated_obj_ref:
                    add_relationship(associated_obj_ref, key_name, "has key")
                elif isinstance(associated_obj_ref, list): 
                     for assoc_obj_name_item in associated_obj_ref:
                         if isinstance(assoc_obj_name_item, str) and assoc_obj_name_item:
                            add_relationship(assoc_obj_name_item, key_name, "has key")
                
                key_relations_ref = key_data.get('hasRelation') 
                if key_relations_ref:
                    if not isinstance(key_relations_ref, list): key_relations_ref = [key_relations_ref]
                    for related_key_name_item in key_relations_ref:
                        if isinstance(related_key_name_item, str) and related_key_name_item:
                            add_relationship(key_name, related_key_name_item, "has relation")


        # 3c. Measurements 'associated_objects'
        if 'measurements_attributes' in data:
            for measurement_data in data.get('measurements_attributes',[]):
                if not isinstance(measurement_data, dict) or not measurement_data.get('name'): continue
                measurement_name = measurement_data['name']
                associated_objs_list = measurement_data.get('associated_objects')
                if associated_objs_list: 
                    if not isinstance(associated_objs_list, list): associated_objs_list = [associated_objs_list]
                    for assoc_obj_name_item in associated_objs_list:
                        if isinstance(assoc_obj_name_item, str) and assoc_obj_name_item:
                            add_relationship(assoc_obj_name_item, measurement_name, "has measurement") 

        # 3d. Functions relationships
        if 'functions' in data:
            for function_data in data.get('functions',[]):
                if not isinstance(function_data, dict) or not function_data.get('name'): continue
                func_name = function_data['name']
                
                applies_to_objs_ref = function_data.get('applicableToDataObject')
                if applies_to_objs_ref:
                    if not isinstance(applies_to_objs_ref, list): applies_to_objs_ref = [applies_to_objs_ref]
                    for target_obj_name_item in applies_to_objs_ref:
                        if isinstance(target_obj_name_item, str) and target_obj_name_item:
                            add_relationship(func_name, target_obj_name_item, "applies to") 
                
                computes_items_ref = function_data.get('computes') 
                if computes_items_ref:
                    if not isinstance(computes_items_ref, list): computes_items_ref = [computes_items_ref]
                    for computed_item_name_item in computes_items_ref:
                        if isinstance(computed_item_name_item, str) and computed_item_name_item:
                            add_relationship(func_name, computed_item_name_item, "computes")
                
                required_measurements_ref = function_data.get('functionRequiresMeasurements') 
                if required_measurements_ref:
                    if not isinstance(required_measurements_ref, list): required_measurements_ref = [required_measurements_ref]
                    for req_measurement_name_item in required_measurements_ref:
                        if isinstance(req_measurement_name_item, str) and req_measurement_name_item:
                            add_relationship(req_measurement_name_item, func_name, "input for")
        
        # 3e. Components / Sub-Entities relationships
        if 'components_sub_entities' in data:
            for component_data in data.get('components_sub_entities',[]):
                if not isinstance(component_data, dict) or not component_data.get('name'): continue
                comp_name = component_data['name']
                parent_ref_str = component_data.get('relationship_to_parent')
                inferred_parent_name = None
                if isinstance(parent_ref_str, str) and parent_ref_str:
                    match = re.match(r"(?:subset_of_|component_of_|related_to_)?(.*)", parent_ref_str)
                    if match: inferred_parent_name = match.group(1)
                
                if inferred_parent_name:
                    rel_label = component_data.get('type', 'relates to') 
                    if rel_label == "derived_subset": rel_label = "is subset of"
                    elif rel_label == "computed": rel_label = "derived from" 
                    add_relationship(inferred_parent_name, comp_name, rel_label)

        # 3f. Generic 'relationships' section from YAML
        if 'relationships' in data:
            for rel_data in data.get('relationships', []):
                if not isinstance(rel_data, dict): continue
                source_original_name = None
                target_original_name = None
                rel_label = rel_data.get('type', 'related to')
                is_dashed_link = False
                computation_func = rel_data.get('computation_function')

                if rel_label == 'links_for_merge':
                    source_original_name = rel_data.get('from_dataset')
                    target_original_name = rel_data.get('to_dataset')
                    is_dashed_link = True 
                    from_key = rel_data.get('from_key')
                    to_key = rel_data.get('to_key')
                    if from_key and to_key:
                        rel_label = f"merge on ({from_key} / {to_key})"
                    else:
                        rel_label = "links for merge"
                else: 
                    source_original_name = rel_data.get('from')
                    target_original_name = rel_data.get('to')
                
                if source_original_name and target_original_name: # Ensure both are not None
                    add_relationship(source_original_name, target_original_name, rel_label, is_dashed=is_dashed_link)
                    if isinstance(computation_func, str) and computation_func and target_original_name: 
                        add_relationship(computation_func, target_original_name, "computes via")
        
        return mermaid_code

    try:
        data = yaml.safe_load(yaml_string)
        if not isinstance(data, dict):
            logging.error("Parsed YAML is not a dictionary. Cannot generate graph.")
            return None
            
        mermaid_code_lines = generate_mermaid_hierarchical(data)
        return "\n".join(mermaid_code_lines)
    except yaml.YAMLError as ye:
        logging.error(f"YAML Parsing Error: {str(ye)}")
        if hasattr(ye, 'problem_mark') and ye.problem_mark:
            logging.error(f"  Problem at line {ye.problem_mark.line+1}, column {ye.problem_mark.column+1}")
        return None
    except Exception as e: # Catch any other exception
        import traceback
        logging.error(f"Unexpected error generating model graph: {str(e)}")
        logging.error(traceback.format_exc()) # This will print the full traceback for any error
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
        logging.error(f"Error generating plan graph: {str(e)}")
        return None
    
