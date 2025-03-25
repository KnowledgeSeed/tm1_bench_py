import configparser
from pathlib import Path
from TM1py.Exceptions import TM1pyRestException
from pandas.core.frame import DataFrame
import pandas as pd
import pytest
import parametrize_from_file
from TM1py import TM1Service
from tm1_bench_py import utility as utility


EXCEPTION_MAP = {
    "ValueError": ValueError,
    "TypeError": TypeError,
    "TM1pyRestException": TM1pyRestException,
    "IndexError": IndexError,
    "KeyError": KeyError
}

@pytest.fixture(scope="session")
def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1

@parametrize_from_file
def test_nested_dictionary_to_dataframe(dict, df_template, df_col, test_dic):
    dataframe = pd.DataFrame.from_dict(test_dic, orient='columns')
    result_df = utility.hierarchy_to_dataframe(df_template,dict)
    pd.testing.assert_frame_equal(result_df, dataframe)

#test simple monhtly creation
@parametrize_from_file
def test_period_creation_with_custom_function(parameters, expected_df_data, expected_df_columns):
    df = utility.generate_time_dimension(**parameters)
    expected_df = pd.DataFrame(expected_df_data, columns=expected_df_columns)
    expected_df = utility._create_typed_period_dataframe(expected_df)
    pd.testing.assert_frame_equal(df, expected_df)