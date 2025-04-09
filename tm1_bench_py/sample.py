from tm1_bench_py import utility, tm1_bench
import os

# Example usage and running tests
def main():
    # Get the directory where your script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate one level up to project_folder/
    parent_dir = os.path.dirname(script_dir)
    # Create the absolute path to your schema directory
    schema_dir = os.path.join(parent_dir, "schema")
    # Define which enviroment should be built, if not specifed it will use the .\config.yaml default_yaml_env parameter
    _ENV = 'try'
    loader = tm1_bench.SchemaLoader(schema_dir, _ENV)
    schema = loader.load_schema()

    tm1 = utility.tm1_connection()

    _DEFAULT_DF_TO_CUBE_KWARGS = schema['config']['df_to_cube_default_kwargs']


    tm1_bench.build_model(tm1=tm1, schema=schema, env=_ENV, system_defaults=_DEFAULT_DF_TO_CUBE_KWARGS)
    tm1_bench.destroy_model(tm1=tm1, schema=schema)
if __name__ == '__main__':
    main()