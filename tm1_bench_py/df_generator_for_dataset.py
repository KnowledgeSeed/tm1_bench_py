from dataclasses import replace

import pandas as pd
import random
from pathlib import Path
import configparser
import importlib
from TM1py import TM1Service, SubsetService
from TM1py.Objects import Dimension, Element, ElementAttribute, Hierarchy, Cube, Subset
import os
from typing import Dict, Any, List, Union
from tm1_bench_py import  exec_metrics_logger, basic_logger,tm1_bench
import re
import itertools
from tm1_bench import SubsetService, Subset
import string

# ------------------------------------------------------------------------------------------------------------
# Utility: Subset utilities
# ------------------------------------------------------------------------------------------------------------
def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1

def _create_subset_from_mdx(dimension: str, hierarchy: str, mdx: str ,tm1) -> List[str]:
    """
    Create a subset from MDX and return its elements

    :param dimension: Dimension name
    :param hierarchy: Hierarchy name
    :param mdx: MDX query string
    :return: List of element names
    """
    try:
        # Create a temporary subset
        subset_name = f"}}Temp_Subset_{hash(mdx)}"

        # Create subset using MDX
        # define Subset Object by MDX Expression
        subset = Subset(dimension_name=dimension,subset_name=subset_name,hierarchy_name=hierarchy ,expression=mdx)
        #post the object ot the server
        tm1.subsets.create(subset=subset)

        # Retrieve elements from the subset
        subset_elements = tm1.subsets.get_element_names(
            dimension_name=dimension,
            hierarchy_name=hierarchy,
            subset_name=subset_name
        )
        # Delete temporary subset
        tm1.dimensions.subsets.delete(
            dimension_name=dimension,
            subset_name=subset_name
        )

        # Return list of element names
        return subset_elements

    except Exception as e:
        raise ValueError(f"Error creating subset from MDX: {e}")

def _get_metadata_from_mdx(mdx: str,tm1) -> Dict[str, Union[str, List[str]]]:
    """
    Extract dimension, hierarchy, and elements from MDX string

    :param mdx: MDX query string
    :return: Dictionary with dimension, hierarchy, and elements
    """
    # Extract dimension and hierarchy using regex
    patterns = [
        # Matches [Dimension].[Hierarchy]
        r'\[([^\]]+)\]\.\[([^\]]+)\]',
        # Matches [Dimension] (assumes same name for hierarchy)
        r'\[([^\]]+)\]'
    ]

    for pattern in patterns:
        match = re.search(pattern, mdx)
        if match:
            if len(match.groups()) == 2:
                # Explicit dimension and hierarchy
                dimension = match.group(1)
                hierarchy = match.group(2)
            else:
                # Single match, use same name for dimension and hierarchy
                dimension = match.group(1)
                hierarchy = dimension

            try:
                # Attempt to create subset and get elements
                elements = _create_subset_from_mdx(dimension, hierarchy, mdx, tm1)

                # Return dictionary with dimension, hierarchy, and elements
                return {
                    "dimension_name": dimension,
                    "hierarchy_name": hierarchy,
                    "elements": elements
                }

            except Exception as e:
                raise ValueError(f"Failed to extract elements for MDX: {mdx}. Error: {e}")

    raise ValueError(f"Could not extract dimension from MDX: {mdx}")

def _split_mdx_string(mdx_string: str) -> list:
    """
    Split an MDX string into individual MDX components using * as a separator
    :param mdx_string: Input MDX string potentially containing multiple MDX queries
    :return: List of individual MDX strings
    """
    # Remove any leading/trailing whitespace
    mdx_string = mdx_string.strip()

    # Split by * character and strip each resulting MDX
    mdx_list = [mdx.strip() for mdx in mdx_string.split('*') if mdx.strip()]

    return mdx_list

# ------------------------------------------------------------------------------------------------------------
# Utility: Generator lambdas utilities
# ------------------------------------------------------------------------------------------------------------
def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """
    Retrieve a nested value from a dictionary using a dot-separated path.

    :param data: The dictionary or nested dictionary to search
    :param path: Dot-separated path to the desired value
    :return: The value at the specified path, or None if not found
    """
    # Split the path into components
    keys = path.split('.')

    # Traverse the nested dictionary
    current = data
    for key in keys:
        # If current is not a dictionary or key doesn't exist, return None
        if not isinstance(current, dict) or key not in current:
            return None

        # Move to the next level
        current = current[key]

    return current

def _random_from_variable_list (variable_path: str, row_data: {}):
    # Get the directory where your script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate one level up to project_folder/
    parent_dir = os.path.dirname(script_dir)
    # Create the absolute path to your schema directory
    schema_dir = os.path.join(parent_dir, "schema")
    loader = tm1_bench.SchemaLoader(schema_dir)
    schema = loader.load_schema()
    value_list = _get_nested_value(schema, variable_path)
    # Check if the list is valid and not empty
    if not value_list or not isinstance(value_list, list):
        print(f"Warning: No valid list found at path {variable_path}")
        return None

    # Randomly select and return a member from the list
    return random.choice(value_list)

def _look_up_based_on_column_value():
    pass

def _generate_from_subset_MDX():
    pass

def _generate_String_wit_ElementId():
    pass

def _getCapitalLetters(apply_on_column: str, row_data: {} ) -> str:
    """
    Extract and return only the capital letters from the input string

    :param string: Input string
    :return: String containing only capital letters from the original
    """
    print(row_data)
    element = str(row_data[apply_on_column])
    print(element, ''.join(c for c in element if element.isupper()))
    return ''.join(c for c in element if element.isupper())

# ------------------------------------------------------------------------------------------------------------
# Utility: Dataframe generator functions
# ------------------------------------------------------------------------------------------------------------
def _generate_row_combinations(list_of_row_dictionaries, number_of_rows) -> List[str]:

    # Determine row generation strategy
    # Generate row combinations
    if number_of_rows == -1:
        # Cartesian product of all dimensions
        row_combinations = list(itertools.product(
            *[result['elements'] for result in list_of_row_dictionaries]
        ))
    else:
        # Random selection with unique rows
        row_combinations = set()
        attempts = 0
        max_attempts = number_of_rows * 10  # Prevent infinite loop

        while len(row_combinations) < number_of_rows and attempts < max_attempts:
            # Randomly select one element from each dimension
            combination = tuple(
                random.choice(result['elements']) for result in list_of_row_dictionaries
            )
            row_combinations.add(combination)
            attempts += 1
        row_combinations = list(row_combinations)
    return row_combinations

def generate_dataframe(dataset_template: Dict[Any, Any],tm1) -> pd.DataFrame:
    """
    Generate DataFrame based on the schema

    :return: Pandas DataFrame
    """
    # Get from schema dictionary the row mdx and the expected row number
    rows_mdx = dataset_template['rows']['mdx']
    number_of_rows = dataset_template['rows']['number_of_rows']
    #split the mdx if it is a product of multiple dimension
    row_mdx_list = _split_mdx_string(rows_mdx)

    list_of_row_dictionaries = []
    for mdx in row_mdx_list:
        list_of_row_dictionaries.append(_get_metadata_from_mdx(mdx,tm1))

    rows = _generate_row_combinations(list_of_row_dictionaries, number_of_rows)

    # Results to build DataFrame
    df_row = []

    # get data column
    data_column_dim_name = str(dataset_template['data_colum_dimension'])

    # Process each combination
    for data in dataset_template['data']:
        callable_str = dataset_template['data'][data]['callable']
        method = dataset_template['data'][data]['method']
        kwargs = dataset_template['data'][data]['kwargs']
        # Create a row dictionary
        for combination in rows:
            row_data = {}
            cur_row_data = {}
            # Add dimension elements to row
            for i, dim_dict in enumerate(list_of_row_dictionaries):
            # Use dimension name as column name to avoid conflicts
                row_data[dim_dict['dimension_name']] = combination[i]
                cur_row_data[dim_dict['dimension_name']] = combination[i]
        # Add data colum with the current data value
            if len( data_column_dim_name ) != 0:
                row_data[data_column_dim_name] = data
                cur_row_data[data_column_dim_name] = data
        # Add value column with generated value
            if method == 'function' and isinstance(callable_str, str):
                try:
                    # Split the string into module and function name
                    module_name, func_name = callable_str.rsplit('.', 1)
                    module = importlib.import_module(module_name)
                    func = getattr(module, func_name)
                    kwargs['row_data'] = cur_row_data
                    row_data['Value'] = func(**kwargs)
                    basic_logger.info(f"Successfully resolved function: {func}")
                except Exception as e:
                    basic_logger.info(f"Error resolving function: {e}")
                    raise

            df_row.append(row_data)

    return pd.DataFrame.from_dict(df_row)

# Example usage and running tests
def main():
    # Get the directory where your script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate one level up to project_folder/
    parent_dir = os.path.dirname(script_dir)
    # Create the absolute path to your schema directory
    schema_dir = os.path.join(parent_dir, "schema")

    loader = tm1_bench.SchemaLoader(schema_dir)
    schema = loader.load_schema()

    tm1 = tm1_connection()
    tst_yaml_content = schema['datasets']['version_attributes']['unit_test']

    dataset = generate_dataframe(tst_yaml_content,tm1)
    print(dataset)

if __name__ == '__main__':
    main()