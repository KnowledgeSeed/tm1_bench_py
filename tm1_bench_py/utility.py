import os
import functools
import time
import pandas as pd
from tm1_bench_py import exec_metrics_logger, basic_logger
import re
from typing import List, Dict
from TM1py import TM1Service
import configparser
from pathlib import Path

# ------------------------------------------------------------------------------------------------------------
# Utility: Tm1 service creator
# ------------------------------------------------------------------------------------------------------------

def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1


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
# Utility: df to tm1 loading functions
# ------------------------------------------------------------------------------------------------------------
def __get_kwargs_dict_from_set_mdx_list(mdx_expressions: List[str]) -> Dict[str, str]:
    """
    Generate a dictionary of kwargs from a list of MDX expressions.

    Args:
        mdx_expressions (List[str]): A list of MDX expressions.

    Returns:
        Dict[str, str]: A dictionary where keys are dimension names (in lowercase, spaces removed)
            and values are the MDX expressions.
    """
    regex = r"\{\s*\[\s*([\w\s]+?)\s*\]\s*"
    return {
        re.search(regex, mdx).group(1).lower().replace(" ", ""): mdx
        for mdx in mdx_expressions
        if re.search(regex, mdx)
    }


def __get_dimensions_from_set_mdx_list(mdx_sets: List[str]) -> List[str]:
    """
    Extracts unique dimension names from a list of MDX set strings,
    preserving the order of their first appearance.

    MDX members are expected in formats like:
    [Dimension].[Hierarchy].[Element]
    or
    [Dimension].[Element]

    Handles whitespace:
    - Around braces {}, commas , dots . and brackets []
    - Inside the first dimension bracket, e.g., [  Dimension Name  ]

    Args:
        mdx_sets: A list of strings, where each string represents an MDX set
                  (e.g., '{[Dim].[Hier].[Elem], [Dim].[Elem]}').

    Returns:
        A list of unique dimension names found across all sets, ordered
        by the sequence in which they were first encountered in the
        input list. Returns an empty list if no valid MDX members are
        found or the input list is empty.
    """
    pattern = r'\{\s*\[([^\]]+?)\]'
    ordered_dimension_names = []

    for mdx_set_string in mdx_sets:
        match = re.search(pattern, mdx_set_string)
        if match:
            cleaned_name = match.group(1).strip()
            ordered_dimension_names.append(cleaned_name)

    return ordered_dimension_names


def __parse_unique_element_names_from_mdx(mdx_string: str) -> List[str]:
    """
    Extracts unique [X].[Y].[Z] patterns from an MDX string,
    where X, Y, and Z can contain spaces and special characters.

    Parameters:
        mdx_string (str): The input MDX query as a string.

    Returns:
        List[str]: A list of unique [X].[Y].[Z] style matches.
    """
    pattern = r'\[.*?\]\.\[.*?\]\.\[.*?\]'
    matches = re.findall(pattern, mdx_string)
    unique_matches = list(set(matches))
    return unique_matches

def _clear_cube_default(
        tm1_service: TM1Service,
        cube_name: str,
        clear_set_mdx_list: List[str],
        **_kwargs
) -> None:
    """
    Clears a cube with filters by generating clear parameters from a list of set MDXs.

    Args:
        tm1_service (TM1Service): An active TM1Service object for the TM1 server connection.
        cube_name (str): The name of the cube to clear.
        clear_set_mdx_list (List[str]): A list of valid MDX set expressions defining the clear space.
        **_kwargs (Any): Additional keyword arguments.
    """
    clearing_kwargs = __get_kwargs_dict_from_set_mdx_list(clear_set_mdx_list)
    tm1_service.cells.clear(cube_name, **clearing_kwargs)

def _dataframe_to_cube_default(
        tm1_service: TM1Service,
        dataframe: pd.DataFrame,
        cube_name: str,
        cube_dims: List[str],
        use_blob: bool,
        slice_size_of_dataframe: int,
        async_write: bool = False,
        use_ti: bool = False,
        increment: bool = False,
        sum_numeric_duplicates: bool = True,
        **kwargs
) -> None:
    """
    Writes a DataFrame to a cube using the TM1 service.

    Args:
        tm1_service (TM1Service): An active TM1Service object for the TM1 server connection.
        dataframe (DataFrame): The DataFrame to write to the cube.
        cube_name (str): The name of the target cube.
        cube_dims (List[str]): A list of dimensions for the target cube.
        async_write (bool, optional): Whether to write data asynchronously. Defaults to False.
        use_ti (bool, optional): Whether to use TurboIntegrator. Defaults to False.
        use_blob (bool, optional): Whether to use the 'blob' method. Defaults to False.
        increment (bool, optional): Increments the values in the cube instead of replacing them. Defaults to False.
        sum_numeric_duplicates (bool, optional): Aggregate numerical values for duplicated intersections.
            Defaults to True.
        **kwargs (Any): Additional keyword arguments.

    Returns:
        None
    """
    if async_write:
        tm1_service.cells.write_dataframe_async(
            cube_name=cube_name,
            data=dataframe,
            dimensions=cube_dims,
            deactivate_transaction_log=True,
            reactivate_transaction_log=True,
            skip_non_updateable=True,
            increment=increment,
            sum_numeric_duplicates=sum_numeric_duplicates,
            slice_size_of_dataframe=slice_size_of_dataframe,
            **kwargs
        )
    else:
        tm1_service.cells.write_dataframe(
            cube_name=cube_name,
            data=dataframe,
            dimensions=cube_dims,
            deactivate_transaction_log=True,
            reactivate_transaction_log=True,
            skip_non_updateable=True,
            use_ti=use_ti,
            use_blob=use_blob,
            remove_blob=True,
            increment=increment,
            sum_numeric_duplicates=sum_numeric_duplicates,
            **kwargs
        )