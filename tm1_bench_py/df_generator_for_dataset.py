import pandas as pd
import random
import importlib
from TM1py import TM1Service
from TM1py.Objects import Subset
from typing import Dict, Any, List, Union, Optional
from tm1_bench_py import basic_logger
import re
import itertools

# ------------------------------------------------------------------------------------------------------------
# Utility: Subset utilities
# ------------------------------------------------------------------------------------------------------------
def _create_subset_from_mdx(dimension: str,
                            hierarchy: str,
                            mdx: str ,
                            tm1: Optional[Any],
                            subset_name: Optional[str] = None) -> List[str]:
    """
    Create a subset from MDX and return its elements

    :param dimension: Dimension name
    :param hierarchy: Hierarchy name
    :param mdx: MDX query string
    :return: List of element names
    """
    try:
        # Create a temporary subset
        if subset_name is None:
            subset_name = f"}}Temp_Subset_{hash(mdx)}"

        # Create subset using MDX
        # define Subset Object by MDX Expression
        subset = Subset(dimension_name=dimension,subset_name=subset_name,hierarchy_name=hierarchy ,expression=mdx)
        #post the object ot the server
        if not tm1.subsets.exists(dimension_name=dimension,subset_name=subset_name):
            tm1.subsets.create(subset=subset)

        # Retrieve elements from the subset
        subset_elements = tm1.subsets.get_element_names(
            dimension_name=dimension,
            hierarchy_name=hierarchy,
            subset_name=subset_name
        )
        # Delete temporary subset
        if subset_name is None:
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
def _get_nested_value(schema: Dict[str, Any], path: str) -> Any:
    """
    Retrieve a nested value from a dictionary using a dot-separated path.

    :param data: The dictionary or nested dictionary to search
    :param path: Dot-separated path to the desired value
    :return: The value at the specified path, or None if not found
    """
    # Split the path into components
    keys = path.split('.')

    # Traverse the nested dictionary
    current = schema
    for key in keys:
        # If current is not a dictionary or key doesn't exist, return None
        if not isinstance(current, dict) or key not in current:
            return None

        # Move to the next level
        current = current[key]
    return current

def _index_from_variable_list (schema: Dict[str, Any],params: Dict, index, **_kwargs) -> Any:
    variable_path = params['variable_path']
    return_value = _get_nested_value(schema, variable_path)

    if return_value is None:
        print(f"Warning: No valid list found at path {variable_path}")
        return None
    if isinstance(return_value, list):
        return return_value[index]
    if isinstance(return_value, dict):
        # Get the list of keys
        keys = list(return_value.keys())
        print(keys[index], keys)
        return keys[index]

def _random_from_variable_list (schema: Dict[str, Any],params: Dict, **_kwargs):
    variable_path = params['variable_path']

    return_value = _get_nested_value(schema, variable_path)
    if return_value is None:
        print(f"Warning: No valid list found at path {variable_path}")
        return None
    elif isinstance(return_value, list):
        # Randomly select and return a member from the list
        return random.choice(return_value)
    # Check if the list is valid and not empty
    if isinstance(return_value, dict):
        # Get the list of keys
        keys = list(return_value.keys())

        # Randomly select and return a key
        if keys:
            return random.choice(keys)

def _look_up_based_on_column_value(row_data: pd.DataFrame, cur_row_data: Dict, params: Dict, schema: Dict[str, Any], **_kwargs) -> Any:
    referred_column = params['referred_column']
    variable_path = params['variable_path']
    variable_key = params['variable_key']
    prefix = params.get('prefix')
    postfix = params.get('postfix')
    if prefix:
        pref = str(prefix)
    else: pref = ""
    if postfix:
        post = str(postfix)
    else: post = ""

    # Convert reference dictionary keys and values to lists for easier indexing
    ref_keys = list(cur_row_data.keys())
    ref_values = list(cur_row_data.values())
    n = len(ref_keys)
    # find in the previously generaed content the matching dictionaries based on the given referred column
    for row  in row_data:
        cur_key = list(row.keys())
        cur_values = list(row.values())
        if len(cur_key) != len(ref_keys):
            match_found = all(
                cur_key[i] == ref_keys[i] and
                cur_values[i] == ref_values[i]
                for i in range(n-1)
            )

            # If all n-1 elements and their keys match, find the n element with the given path and key the looked up variable value
            if match_found and cur_values[n-1] == str(referred_column):
                variable_path = variable_path+"."+str(cur_values[n])+"."+variable_key
                searched_obj = _get_nested_value(schema, variable_path)
                if searched_obj is None:
                    return None
                elif isinstance(searched_obj, str):
                    return pref + str(searched_obj) + post
                elif isinstance(searched_obj, int):
                    return searched_obj
                elif isinstance(searched_obj, list):
                    chosen_obj = random.choice(searched_obj)
                    return pref + str(chosen_obj) + post

def _generate_from_subset_mdx(params: Dict, mdx_cache: Dict, tm1: TM1Service, **_kwargs):
    dimension = params['dimension_name']
    hierarchy = params.get('hierarchy_name')
    subsetMDX = params['subsetMDX']

    if hierarchy == None:
        hierarchy = dimension

    if subsetMDX not in mdx_cache:
        subset_name = f"}}tm1bench_Random_Subset_{hash(subsetMDX)}"
        element_list = _create_subset_from_mdx(dimension=dimension, hierarchy=hierarchy, mdx=subsetMDX, tm1=tm1,
                                               subset_name=subset_name)
        mdx_cache[subsetMDX] = element_list
    return random.choice(mdx_cache[subsetMDX])

def _getCapitalLetters(cur_row_data: Dict, params: Dict, **_kwargs) -> str:
    """
    Extract and return only the capital letters from the input string

    :param string: Input string
    :return: String containing only capital letters from the original
    """
    apply_on_column = params['apply_on_column']
    element = str(cur_row_data[apply_on_column])
    return ''.join(c for c in element if c.isupper())


def _random_number_based_on_statistic(params: Dict, **_kwargs):
    """
    Generate a random number with various distribution methods.

    Args:
        min_val (int or float): Minimum value of the range
        max_val (int or float): Maximum value of the range
        num_type (str, optional): Type of number to generate.
                                  Supports 'int' or 'float'.
                                  Defaults to 'int'.
        distribution (str, optional): Random distribution method.
                                      Supports:
                                      - 'uniform' (default)
                                      - 'normal' (Gaussian)
                                      - 'exponential'
                                      - 'triangular'
        **kwargs: Additional parameters for specific distributions

    Returns:
        int or float: A random number generated according to specified distribution

    Raises:
        ValueError: If an unsupported distribution or number type is provided
        TypeError: If min_val or max_val are not numbers
    """
    #get kwargs
    min_val = params['min_val']
    max_val = params['max_val']
    num_type = params['num_type']
    distribution = params['distribution']

    # Validate input types
    if not (isinstance(min_val, (int, float)) and isinstance(max_val, (int, float))):
        raise TypeError("Min and max values must be numbers")

    # Ensure min_val is less than max_val
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    # Distribution selection
    if distribution.lower() == 'uniform':
        # Standard uniform distribution
        if num_type.lower() == 'int':
            return random.randint(int(min_val), int(max_val))
        elif num_type.lower() == 'float':
            return random.uniform(min_val, max_val)

    elif distribution.lower() == 'normal':
        # Normal (Gaussian) distribution
        # Requires mean and standard deviation
        mean =  params.get('mean', (min_val + max_val) / 2)
        std_dev =  params.get('std_dev', (max_val - min_val) / 6)

        while True:
            num = random.gauss(mean, std_dev)
            if min_val <= num <= max_val:
                return int(num) if num_type.lower() == 'int' else num

    elif distribution.lower() == 'exponential':
        # Exponential distribution
        # Requires lambda parameter (rate)
        rate = params.get('distribution', 1.0)

        while True:
            # Generate exponential distribution
            num = min_val + random.expovariate(rate)
            if num <= max_val:
                return int(num) if num_type.lower() == 'int' else num

    elif distribution.lower() == 'triangular':
        # Triangular distribution
        # Requires mode (peak) parameter
        mode = params.get('mode', (min_val + max_val) / 2)

        return random.triangular(min_val, max_val, mode)

    else:
        raise ValueError(f"Unsupported distribution: {distribution}")
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

def generate_dataframe(dataset_template: Dict[Any, Any], tm1:TM1Service, schema) -> pd.DataFrame:
    """
    Generate DataFrame based on the schema

    :return: Pandas DataFrame
    """
    # Get from schema dictionary the row mdx and the expected row number
    rows_mdx = dataset_template['rows']['mdx']
    number_of_rows = dataset_template['rows']['number_of_rows']
    #split the mdx if it is a product of multiple dimension
    row_mdx_list = _split_mdx_string(rows_mdx)
    mdx_cache = {}

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
        params = dataset_template['data'][data]['params']
        index = 0

        # Pre-resolve the function once per data column
        generator_func = None
        if method == 'function' and isinstance(callable_str, str):
            try:
                module_name, func_name = callable_str.rsplit('.', 1)
                module = importlib.import_module('.' + module_name, 'tm1_bench_py')
                generator_func = getattr(module, func_name)
                basic_logger.debug(f"Successfully resolved generator function: {func_name} from {module_name}")
            except (ImportError, AttributeError, ValueError) as e:
                basic_logger.error(f"Error resolving function '{callable_str}' for data column '{data}': {e}",
                                   exc_info=True)
                basic_logger.warning(f"Skipping data column '{data}' due to function resolution error.")
                continue  # Skip to the next data column
        else:
            basic_logger.warning(
                f"Unsupported method '{method}' or invalid callable for data column '{data}'. Skipping.")
            continue

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
                    # Prepare kwargs for the generator function
                    generator_kwargs = {
                        'cur_row_data': cur_row_data.copy(),  # Pass a copy to prevent modification
                        'schema': schema,
                        'params': params,
                        'tm1': tm1,
                        'index': index,
                        'row_data': df_row,
                        'mdx_cache': mdx_cache
                    }
                    row_data['Value'] = generator_func(**generator_kwargs)
                except Exception as e:
                    basic_logger.info(f"Error resolving function: {e}")
                    raise
            index += 1
            df_row.append(row_data)

    return pd.DataFrame.from_dict(df_row)