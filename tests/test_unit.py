import configparser
import os

import yaml
from pathlib import Path
from TM1py.Exceptions import TM1pyRestException
from pandas.core.frame import DataFrame
import pandas as pd
import pytest
import parametrize_from_file
from TM1py import TM1Service

from tm1_bench_py import utility, df_generator_for_dataset, tm1_bench, dimension_builder, dimension_period_builder

EXCEPTION_MAP = {
    "ValueError": ValueError,
    "TypeError": TypeError,
    "TM1pyRestException": TM1pyRestException,
    "IndexError": IndexError,
    "KeyError": KeyError
}

utility.set_logging_level("WARNING")

@pytest.fixture(scope="session")
def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    tm1 = None
    try:
        config = configparser.ConfigParser()
        config.read(Path(__file__).parent.joinpath('config.ini'))

        tm1 = TM1Service(**config['tm1srv'])
        yield tm1
    finally:
        if tm1 is not None:
            tm1.logout()


def get_file_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    schema_dir = os.path.join(parent_dir, "schema")
    return schema_dir


def test_tm1_connection(tm1_connection):
    server_name = tm1_connection.server.get_server_name()
    print("Connection to TM1 established! Your server name is: {}".format(server_name))


@parametrize_from_file
def test_nested_dictionary_to_dataframe(dict, df_template, df_col, test_dic):
    dataframe = pd.DataFrame.from_dict(test_dic, orient='columns')
    result_df = dimension_builder.hierarchy_to_dataframe(df_template,dict)
    pd.testing.assert_frame_equal(result_df, dataframe)

#test simple monhtly creation
@parametrize_from_file
def test_period_creation_with_custom_function(parameters, expected_df_data, expected_df_columns):
    df = dimension_period_builder.generate_time_dimension(**parameters)
    expected_df = pd.DataFrame(expected_df_data, columns=expected_df_columns)
    expected_df = utility._create_typed_period_dataframe(expected_df)
    pd.testing.assert_frame_equal(df, expected_df)


@parametrize_from_file
def test_dataframe_find_and_replace(dataframe, params, expected_dataframe):
    df = pd.DataFrame(dataframe)
    expected_df = pd.DataFrame(expected_dataframe)
    utility.dataframe_find_and_replace(df, params)

    pd.testing.assert_frame_equal(df, expected_df)


@parametrize_from_file
def test_generate_dataframe_based_on_schema(tm1_connection, file_name, dataset_size):
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()
    try:
        tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)

        with open(f"{schema_dir}/datasets/{file_name}") as d:
            dataset_template = yaml.safe_load(d)[dataset_size]
        assert isinstance(
            df_generator_for_dataset.generate_dataframe(
                dataset_template=dataset_template, tm1=tm1_connection, schema=schema),
            DataFrame
        )
    finally:
        tm1_bench.delete_dimensions(tm1_connection, schema)


@parametrize_from_file
def test_generate_dataframe_based_on_schema_check_columns(tm1_connection, file_name, dataset_size, expected_columns):
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()
    try:
        tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)
        with open(f"{schema_dir}/datasets/{file_name}") as d:
            dataset_template = yaml.safe_load(d)[dataset_size]

        df = df_generator_for_dataset.generate_dataframe(dataset_template=dataset_template,tm1=tm1_connection, schema=schema)
        assert all(c == ec for c, ec in zip(df.columns, expected_columns))

    finally:
        tm1_bench.delete_dimensions(tm1=tm1_connection, schema=schema)

# ------------------------------------------------------------------------------------------------------------
# dimension_builder: building dimensions based on dataframe template os element list
# ------------------------------------------------------------------------------------------------------------

@parametrize_from_file
def test_generate_hierarchy_dictionary_match_key_value_pairs(df_template_file, dataset_size, expected_hierarchy):
    is_matching = False
    schema_dir = get_file_path()
    with open(schema_dir + df_template_file) as s:
        schema = yaml.safe_load(s)[dataset_size]
    df_template = schema['df_template']
    hierarchy = dimension_builder.generate_hierarchy_dictionary(df_template=df_template)
    hierarchy.pop('children')

    for key in hierarchy.keys():
        if str(hierarchy.get(key)) == str(expected_hierarchy.get(key)):
            is_matching = True
        else: is_matching = False
    assert is_matching is True


@parametrize_from_file
def test_hierarchy_to_dataframe_check_if_instance(df_template_file, dataset_size):
    schema_dir = get_file_path()
    with open(schema_dir + df_template_file) as s:
        schema = yaml.safe_load(s)[dataset_size]
    df_template = schema['df_template']
    hierarchy = dimension_builder.generate_hierarchy_dictionary(df_template=df_template)
    assert isinstance(
        dimension_builder.hierarchy_to_dataframe(df_template=df_template, hierarchy_dict=hierarchy),
        DataFrame
    )


@parametrize_from_file
def test_create_dimension_from_dataframe_template_check_if_created(tm1_connection,df_template_file, dataset_size):
    is_created = False
    schema_dir = get_file_path()
    with open(schema_dir + df_template_file) as s:
        schema = yaml.safe_load(s)[dataset_size]
    dimension_name = schema['dimension_name']
    df_template = schema['df_template']
    try:
        dimension_builder.create_dimension_from_dataframe_template(
            tm1=tm1_connection,
            df_template=df_template,
            dimension_name=dimension_name
        )
        is_created = tm1_connection.dimensions.exists(dimension_name)
        assert is_created is True
    finally:
        if is_created:
            tm1_connection.dimensions.delete(dimension_name)


@parametrize_from_file
def test_create_dimension_from_element_list_check_if_created(tm1_connection, elementlist_file, dataset_size):
    is_created = False
    schema_dir = get_file_path()
    with open(schema_dir + elementlist_file) as s:
        schema = yaml.safe_load(s)[dataset_size]
    dimension_name = schema['dimension_name']
    elements_dic = schema['elements']
    edges = schema['edges']
    element_attributes_dic = schema['attributes']
    try:
        dimension_builder.create_dimension_from_element_list(
            tm1=tm1_connection,
            dimension_name=dimension_name,
            elements_dic=elements_dic,
            edges=edges,
            element_attributes_dic=element_attributes_dic
        )
        is_created = tm1_connection.dimensions.exists(dimension_name)
        assert is_created is True
    finally:
        if is_created:
            tm1_connection.dimensions.delete(dimension_name)


# ------------------------------------------------------------------------------------------------------------
# tm1_bench: building models based on schema
# ------------------------------------------------------------------------------------------------------------

@parametrize_from_file
def test_create_dimension_check_if_created(tm1_connection, schema, name):
    is_created = None
    try:
        tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)
        is_created = tm1_connection.dimensions.exists(name)
        assert is_created is True
    finally:
        if is_created:
            tm1_connection.dimensions.delete(name)


@parametrize_from_file
def test_delete_dimensions(tm1_connection, dataset_size, dim_names):
    # Load schema
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()

    # Create dimensions for testing
    is_created = []
    tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)
    for name in dim_names:
        is_created.append(tm1_connection.dimensions.exists(name))
    if any(is_created) is False:
        print("Some dimensions could not be created.")

    # Delete dimensions
    does_exist = []
    tm1_bench.delete_dimensions(tm1=tm1_connection, schema=schema)
    for name in dim_names:
        does_exist.append(tm1_connection.dimensions.exists(name))

    assert all(does_exist) is False


@parametrize_from_file
def test_create_cube_check_if_created(tm1_connection, dataset_size):
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()
    is_created = []
    try:
        tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)
        tm1_bench.create_cubes(tm1=tm1_connection, schema=schema)
        for cubes in schema['cubes']:
            is_created.append(tm1_connection.cubes.exists(schema['cubes'][cubes]['name']))
        assert all(is_created) is True
    finally:
        print("done")
        if all(is_created):
            for cubes in schema['cubes']:
                tm1_connection.cubes.delete(schema['cubes'][cubes]['name'])
            for cubes in schema['cubes']:
                for dim in schema['cubes'][cubes]['dimensions']:
                    if tm1_connection.dimensions.exists(dim):
                        tm1_connection.dimensions.delete(dim)


@parametrize_from_file
def test_delete_cubes(tm1_connection, dataset_size):
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()

    is_created = []
    tm1_bench.create_dimensions(tm1=tm1_connection, schema=schema)
    tm1_bench.create_cubes(tm1=tm1_connection, schema=schema)
    for cubes in schema['cubes']:
        is_created.append(tm1_connection.cubes.exists(schema['cubes'][cubes]['name']))
    if any(is_created) is False:
        print("Some cubes could not be created.")

    does_exist = []
    tm1_bench.delete_cubes(tm1=tm1_connection, schema=schema)
    tm1_bench.delete_dimensions(tm1=tm1_connection, schema=schema)
    for cubes in schema['cubes']:
        does_exist.append(tm1_connection.cubes.exists(schema['cubes'][cubes]['name']))

    assert all(does_exist) is False


@pytest.mark.xfail
@pytest.mark.parametrize("dataset_size", ['bedrock_test_10000'] )
def test_generate_data(tm1_connection, dataset_size):
    schema_dir = get_file_path()
    loader = tm1_bench.SchemaLoader(schema_dir, dataset_size)
    schema = loader.load_schema()
    _DEFAULT_DF_TO_CUBE_KWARGS = schema['config']['df_to_cube_default_kwargs']
    tm1_bench.create_dimensions(tm1_connection, schema)
    tm1_bench.create_cubes(tm1_connection, schema)
    try:
        tm1_bench.generate_data(tm1=tm1_connection, schema=schema, system_defaults=_DEFAULT_DF_TO_CUBE_KWARGS)
    finally:
        tm1_bench.destroy_model(tm1=tm1_connection, schema=schema)
        print("exec ended, model destroyed")


@pytest.mark.xfail
@pytest.mark.parametrize("envname", ['bedrock_test_10000'] )
def test_build_model(tm1_connection, envname):
    schema_dir = get_file_path()
    schemaloader = tm1_bench.SchemaLoader(schema_dir, envname)
    schema = schemaloader.load_schema()
    default_df_to_cube_kwargs = schema['config']['df_to_cube_default_kwargs']
    try:
        tm1_bench.build_model(tm1=tm1_connection, schema=schema, env=envname, system_defaults=default_df_to_cube_kwargs)

    finally:
        tm1_bench.destroy_model(tm1=tm1_connection, schema=schema)
        print("exec ended, model destroyed")
