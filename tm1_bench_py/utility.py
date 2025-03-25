import random
import os
import functools
import time
import string
import pandas as pd
from tm1_bench_py import exec_metrics_logger, basic_logger

# ------------------------------------------------------------------------------------------------------------
# Utility: Logging helper functions
# ------------------------------------------------------------------------------------------------------------


def execution_metrics_logger(func, *args, **kwargs):
    """Measures and logs the runtime of any function."""
    start_time = time.perf_counter()
    result = func(*args, **kwargs)
    exec_id = kwargs.get("_execution_id")

    if exec_id is None:
        exec_id = 0

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    exec_metrics_logger.debug(f"exec_time {execution_time:.2f} s", extra={
        "func": func.__name__,
        "fileName": os.path.basename(func.__code__.co_filename),
        "exec_id": f"exec_id {exec_id}"
    })

    return result


def log_exec_metrics(func):
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return execution_metrics_logger(func, *args, **kwargs)
    return wrapper


def set_logging_level(logging_level: str):
    basic_logger.setLevel(logging_level)
    exec_metrics_logger.setLevel(logging_level)

# ------------------------------------------------------------------------------------------------------------
# Utility: df_template generation helping functions
# ------------------------------------------------------------------------------------------------------------

# helping function to traverse a nested dictionary into a list of rows,
# where a rows[] element build by all N level element of the hierarchy traversing the path from the root to the element
def traverse_hierarchy(node, path=None, weights=None, rows=None):
    """
    Recursive function to traverse the hierarchical tree structure.

    Parameters:
    node (dict): Current node in the hierarchy
    path (dict): Dictionary tracking the path from root to current node
    weights (dict): Dictionary tracking weights from root to current node
    rows (list): List to collect row data for the DataFrame

    Returns:
    list: Collected rows for the DataFrame
    """
    if path is None:
        path = {}
    if weights is None:
        weights = {}
    if rows is None:
        rows = []

    # Add current node to path
    current_level = node.get('level')
    if current_level != 'leaf':
        path[current_level] = node.get('element_name')
        weights[f"{current_level}_weight"] = node.get('weight')

    # If it's a leaf node, create a row
    if 'children' not in node or not node['children']:
        row = {
            'element_id': node.get('element_name'),
            'element_type': node.get('type')
        }

        # Add path information
        for level, name in path.items():
            row[level] = name

        # Add weight information
        for weight_key, weight_val in weights.items():
            row[weight_key] = weight_val

        rows.append(row)

    # Recursively process children
    if 'children' in node and node['children']:
        for child in node['children']:
            # Create copies of path and weights to avoid modifying the original
            child_path = path.copy()
            child_weights = weights.copy()
            traverse_hierarchy(child, child_path, child_weights, rows)

    return rows

# generate the element attributes dataframe based on the generation methods
def _generate_element_attributes(attribute_name, num_elements):
    """
    Generate attributes for elements based on attribute info.

    Parameters:
    attribute_info (dict): Information about how to generate the attribute
    num_elements (int): Number of elements to generate attributes for

    Returns:
    list: List of attribute values
    """

    attribute_type = attribute_name.split(":")[-1] if ":" in attribute_name else "s"  # Default to string

    if attribute_type == "n":
        # Same value for all elements
        values = [0] * num_elements
    elif attribute_type == "s" or attribute_type == "a":
        # Randomly select from list for each element
        values = [""] * num_elements
    else:
        values = [""] * num_elements

    return values

# get a hierarchy defined by a nested dictionary and create a dataframe in the expected format of TM1py
# see expected format:https://github.com/cubewise-code/tm1py/blob/master/TM1py/Services/HierarchyService.py
def hierarchy_to_dataframe(df_template, hierarchy_dict):
    """
    Convert a hierarchical tree structure (nested dictionary) to a pandas DataFrame.

    Parameters:
    data (dict): Nested dictionary representing a hierarchical tree structure

    Returns:
    pandas.DataFrame: Flattened representation of the hierarchy
    """
    # Traverse the hierarchy and collect rows
    rows = traverse_hierarchy(hierarchy_dict)

    # Create DataFrame from collected rows
    df = pd.DataFrame(rows)

    # Ensure all expected columns are present for hierarchy
    level_columns = [level_info["name"] for level_info in df_template["levels"]]
    level_weight_columns = [f"{level}_weight" for level in level_columns]

    expected_columns = ["element_id", "element_type"] + level_columns + level_weight_columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
        else:
            # Replace NaN values with 0
            df[col] = df[col].fillna(0)

    # Add attributes if specified in template and reorder columns
    column_order = ["element_id", "element_type"] + level_columns + level_weight_columns
    if "attributes" in df_template:
        num_elements = len(df)
        attr_list = df_template["attributes"]
        for i in range(len(attr_list)):
            attribute_name =attr_list[i]
            attribute_values = _generate_element_attributes(attribute_name, num_elements)
            df[attribute_name] = attribute_values
            column_order += attribute_name

    # Only include columns that exist in the dataframe
    column_order = [col for col in column_order if col in df.columns]
    df = df[column_order]

    return df

# get a dimension template, then create the defined nested dictionary for the hierarchy representation
def generate_hierarchy_dictionary(df_template):
    """
    Generate a nested dictionary representing a hierarchical structure based on a template.

    Parameters:
    df_template (dict): Template containing instructions for generating the hierarchy

    Returns:
    dict: Generated hierarchical nested dictionary
    """
    # Extract template information
    elements_info = df_template["elements"]
    levels_info = df_template["levels"]

    # Generate leaf elements
    num_elements = elements_info["NumberOfElements"]
    element_prefix = elements_info["ElementPrefix"]
    element_length = elements_info["ElementLength"]

    elements = []
    for i in range(1, num_elements + 1):
        if elements_info["Method"] == "enumerate":
            # Generate element name with prefix and sequential number
            element_name = f"{element_prefix}{str(i).zfill(element_length - len(element_prefix))}"
        else:
            # For other methods, we could implement different generation logic
            # For now, default to random if not enumerate
            random_suffix = ''.join(random.choices(string.digits, k=element_length - len(element_prefix)))
            element_name = f"{element_prefix}{random_suffix}"

        elements.append({
            "type": "numeric",
            "level": "leaf",
            "element_name": element_name,
            "weight": 1
        })

    # Process levels from bottom to top (reverse order)
    levels_reversed = list(reversed(levels_info))

    # Start with leaf elements as current_nodes
    current_nodes = elements

    # Process each level to build the hierarchy
    for level_info in levels_reversed:
        level_name = level_info["name"]

        # Determine number of groups at this level
        if level_name == levels_info[0]["name"]:  # Top level (root)
            num_groups = 1
        elif "content_template" in level_info:
            # Determine a reasonable number of groups based on current nodes and level
            # A simple approach: we'll use approximately sqrt of the number of current nodes
            num_groups = max(1, int(len(current_nodes) ** 0.5))
        else:
            num_groups = 1

        # Create groups
        new_nodes = []
        nodes_per_group = len(current_nodes) // num_groups
        remainder = len(current_nodes) % num_groups

        start_idx = 0
        for i in range(num_groups):
            # Distribute nodes evenly accounting for remainder
            group_size = nodes_per_group + (1 if i < remainder else 0)
            group_nodes = current_nodes[start_idx:start_idx + group_size]
            start_idx += group_size

            # Generate group name
            if level_name == levels_info[0]["name"] and "constant_content" in level_info:
                # Use constant content for top level
                group_name = level_info["constant_content"]
            elif "content_template" in level_info:
                # Generate name based on template
                template = level_info["content_template"]
                prefix = template["Prefix"]
                length = template["Length"]

                if template["Method"] == "random":
                    # Generate random suffix
                    suffix = ''.join(random.choices(string.digits, k=length))
                    group_name = f"{prefix}{suffix}"
                else:
                    # Default to sequential numbering
                    group_name = f"{prefix}{str(i + 1).zfill(length)}"
            else:
                # Default name
                group_name = f"{level_name}_group_{i + 1}"

            # Create group node
            group_node = {
                "type": "consolidated",
                "level": level_name,
                "element_name": group_name,
                "weight": 1,
                "children": group_nodes
            }

            new_nodes.append(group_node)

        # Update current_nodes for next level processing
        current_nodes = new_nodes

    # Return the root node (should be only one node at the end)
    if current_nodes:
        return current_nodes[0]
    else:
        # Handle edge case of empty result
        return {
            "type": "consolidated",
            "level": levels_info[0]["name"],
            "element_name": "Empty Hierarchy",
            "weight": 1,
            "children": []
        }

# Print a limited version of hierarchical nested dictionary for demonstration
def _print_limited_nested_dictionary(node, depth=0, max_children=2, max_depth=2):
    """Helper function to print a limited view of the hierarchy for demonstration"""
    basic_logger.debug("Generated Hierarchy Preview:")
    indent = "  " * depth
    print(f"{indent}- {node['element_name']} ({node['level']})")

    if depth < max_depth and 'children' in node and node['children']:
        children_to_print = node['children'][:max_children]
        for child in children_to_print:
            _print_limited_nested_dictionary(child, depth + 1, max_children, max_depth)
        if len(node['children']) > max_children:
            basic_logger.debug(f"{indent}  ... and {len(node['children']) - max_children} more children")

# Count total elements of a nested dictionary
def _count_nested_dictionary_elements(node):
    """Helper function to count total elements in the hierarchy"""
    if 'children' not in node or not node['children']:
        return 1
    return sum(_count_nested_dictionary_elements(child) for child in node['children'])
