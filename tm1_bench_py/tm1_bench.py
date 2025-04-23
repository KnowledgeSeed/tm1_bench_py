from TM1py import TM1Service
from TM1py.Objects import Cube
import os
import yaml
import importlib
from typing import Dict, List, Any
from tm1_bench_py import basic_logger, df_generator_for_dataset, utility, dimension_builder

class SchemaLoader:
    def __init__(self, schema_dir: str, env: str):
        self.schema_dir = schema_dir
        self.dimensions = {
            'elementlist': {},
            'df_templates': {},
            'custom': {}
        }
        self.cubes = {}
        self.datasets = {}
        self.config = {}
        self.variables = {}
        self.env = env

    def _load_yaml_file(self, relative_path: str, filename: str) -> Dict[str, Any]:
        """Helper to load a single YAML file with error handling."""
        base_path = self.config.get('paths', {}).get(relative_path, relative_path)  # Use configured path
        full_path = os.path.join(self.schema_dir, base_path, f"{filename}.yaml")
        try:
            with open(full_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            basic_logger.error(f"Schema file not found: {full_path}")
            return {}
        except yaml.YAMLError as e:
            basic_logger.error(f"Error parsing YAML file {full_path}: {e}")
            return {}

    def _load_env_specific_yaml(self, relative_path: str, filename: str) -> Dict[str, Any]:
        """Loads YAML and extracts the environment-specific section."""
        loaded_content = self._load_yaml_file(relative_path, filename)
        if loaded_content is None:
            return {}

        if self.env not in loaded_content:
            full_path = os.path.join(self.schema_dir, self.config.get('paths', {}).get(relative_path, relative_path),
                                     f"{filename}.yaml")
            basic_logger.error(f"Environment key '{self.env}' not found in {full_path}")
            return {}

        return loaded_content[self.env]

    def load_schema(self) -> Dict[str, Any]:
        """Load the main schema file and all referenced files, filtering by environment."""
        main_schema_path = os.path.join(self.schema_dir, 'schema.yaml')
        try:
            with open(main_schema_path, 'r') as f:
                main_schema = yaml.safe_load(f)
        except FileNotFoundError:
            basic_logger.error(f"Main schema file not found: {main_schema_path}")
            raise
        except yaml.YAMLError as e:
            basic_logger.error(f"Error parsing main schema file {main_schema_path}: {e}")
            raise

        # --- Load config FIRST to get env and paths ---
        config_schema_path = os.path.join(self.schema_dir, 'config.yaml')
        try:
            with open(config_schema_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            basic_logger.error(f"Config file not found: {main_schema_path}")
            raise
        except yaml.YAMLError as e:
            basic_logger.error(f"Error parsing config file {main_schema_path}: {e}")
            raise
        if self.config is None or 'default_yaml_env' not in self.config:
             raise ValueError("Failed to load config or 'default_yaml_env' missing in config.yaml")
        if self.env == '':
            self.env = self.config['default_yaml_env']
            basic_logger.info(f"Loading schema for environment: '{self.env}'")

        # Validate paths configuration exists
        if 'paths' not in self.config:
             basic_logger.warning("'paths' section missing in config.yaml, using default hardcoded paths.")

        # Load variables (not environment specific)
        variables_filename = main_schema.get('import', {}).get('variables', ["variables"])
        self.variables = self._load_yaml_file('variables', variables_filename)
        if self.variables is None:
             basic_logger.warning(f"Failed to load variables file: {variables_filename}.yaml. Proceeding without variables.")
             self.variables = {}

        # --- Load dimensions, cubes, datasets using the determined env ---
        dimension_imports = main_schema.get('import', {}).get('dimensions', {})
        self._load_dimensions(dimension_imports)

        cube_imports = main_schema.get('import', {}).get('cubes', [])
        self._load_cubes(cube_imports)

        dataset_imports = main_schema.get('import', {}).get('datasets', [])
        self._load_datasets(dataset_imports)

        return {
            'dimensions': self.dimensions,
            'cubes': self.cubes,
            'datasets': self.datasets,
            'variables': self.variables,
            'config': self.config,
            'env': self.env
        }

    def _load_dimensions(self, dimension_refs: Dict[str, List[str]]) -> None:
        """Load all dimension definitions by type, extracting env-specific config."""
        for dim_type, path_key_suffix in [
            ('elementlist', 'dimensions_elementlist'),
            ('df_templates', 'dimensions_df_templates'),
            ('custom', 'dimensions_custom')
        ]:
            path_key = path_key_suffix # Directly use the key from config.yaml paths
            for dim_name in dimension_refs.get(dim_type, []):
                 env_specific_content = self._load_env_specific_yaml(path_key, dim_name)
                 if env_specific_content:
                     # Store only the env-specific part
                     self.dimensions[dim_type][dim_name] = env_specific_content
                 else:
                      basic_logger.warning(f"Skipping dimension '{dim_name}' of type '{dim_type}' due to loading error or missing env key '{self.env}'.")

    def _load_cubes(self, cube_refs: List[str]) -> None:
        """Load all cube definitions, extracting env-specific config."""
        path_key = 'cubes' # Key from config.yaml paths
        for cube_file_name in cube_refs: # cube_refs is now just a list of filenames
            env_specific_content = self._load_env_specific_yaml(path_key, cube_file_name)
            if env_specific_content:
                 # Use the 'name' defined *inside* the env block as the key
                 cube_name = env_specific_content.get('name')
                 if cube_name:
                      self.cubes[cube_name] = env_specific_content
                 else:
                      basic_logger.error(f"Cube definition in '{cube_file_name}.yaml' for env '{self.env}' is missing the required 'name' key.")
            else:
                 basic_logger.warning(f"Skipping cube definition '{cube_file_name}' due to loading error or missing env key '{self.env}'.")


    def _load_datasets(self, datasets_refs: List[str]) -> None:
        """Load all dataset definitions, extracting env-specific config."""
        path_key = 'datasets' # Key from config.yaml paths
        for dataset_name in datasets_refs:
             env_specific_content = self._load_env_specific_yaml(path_key, dataset_name)
             if env_specific_content:
                  self.datasets[dataset_name] = env_specific_content
             else:
                  basic_logger.warning(f"Skipping dataset '{dataset_name}' due to loading error or missing env key '{self.env}'.")

@utility.log_exec_metrics
def create_dimensions(tm1: TM1Service, schema):
    for template_type in schema['dimensions']:
        for dimension in schema['dimensions'][template_type]:
            dimension_name = schema['dimensions'][template_type][dimension]['dimension_name']
            basic_logger.info(f" {dimension_name} is creating..." )
            match template_type:
                case "elementlist":
                    edges = schema['dimensions'][template_type][dimension]['edges']
                    edges_dict = {}
                    if edges:
                        for parent, child, value in schema['dimensions'][template_type][dimension]['edges']:
                            edges_dict[(parent, child)] = value
                    dimension_builder.create_dimension_from_element_list (
                        dimension_name = dimension_name,
                        tm1 = tm1,
                        elements_dic = schema['dimensions'][template_type][dimension]['elements'],
                        edges = edges_dict,
                        element_attributes_dic = schema['dimensions'][template_type][dimension]['attributes']
                    )
                case "df_templates":
                    dimension_builder.create_dimension_from_dataframe_template(
                    dimension_name=dimension_name,
                    tm1=tm1,
                    df_template = schema['dimensions'][template_type][dimension]['df_template']
                    )
                case "custom":
                    func = schema['dimensions'][template_type][dimension]['callable']
                    kwargs = schema['dimensions'][template_type][dimension]['kwargs']
                    if isinstance(func, str):
                        try:
                            # Split the string into module and function name
                            module_name, func_name = func.rsplit('.', 1)
                            module = importlib.import_module('.' + module_name, 'tm1_bench_py')
                            func = getattr(module, func_name)
                            basic_logger.info(f"Successfully resolved function: {func}")
                            result_df = func(**kwargs)
                            tm1.hierarchies.update_or_create_hierarchy_from_dataframe(
                                dimension_name=dimension_name, hierarchy_name=dimension_name, df=result_df,
                                element_column="element_id", element_type_column="element_type",
                                verify_unique_elements=True,
                                verify_edges=True)
                        except Exception as e:
                            basic_logger.info(f"Error resolving function: {e}")
                            raise
            basic_logger.info(f" {dimension_name} is created.")

@utility.log_exec_metrics
def create_cubes(tm1: TM1Service, schema):
    for cubes in schema['cubes']:
        print(cubes)
        cube_name = schema['cubes'][cubes]['name']
        cube_dimensions = schema['cubes'][cubes]['dimensions']
        cube_rules = schema['cubes'][cubes]['rules']
        cube = Cube(name=cube_name, dimensions=cube_dimensions)
        tm1.cubes.update_or_create(cube)
        rule_str = '\r\n'.join(cube_rules) + '\r\n'
        tm1.cubes.update_or_create_rules(cube_name=cube_name, rules=rule_str)

@utility.log_exec_metrics
def generate_data(tm1: TM1Service, schema, system_defaults):
    for datasets in schema['datasets']:
        dataset_template = schema['datasets'][datasets]
        target_cube = schema['datasets'][datasets]['targetCube']
        if target_cube.startswith('}ElementAttributes_'):
            pos = target_cube.find('_')
            dim_name = target_cube[pos + 1:]
            cube_dims = [dim_name, target_cube]
        else:
            cube_dims = schema['cubes'][target_cube]['dimensions']
        async_write = system_defaults['async_write']
        slice_size_of_dataframe = system_defaults['slice_size_of_dataframe']
        use_ti=system_defaults['use_ti']
        use_blob=system_defaults['use_blob']
        if schema['datasets'][datasets].get('df_from_mdx') is None:
            dataframe = df_generator_for_dataset.generate_dataframe(dataset_template, tm1, schema)
        else:
            dataframe = utility._tm1_mdx_to_dataframe_default(tm1_service=tm1, data_mdx=schema['datasets'][datasets]['df_from_mdx'])
            if schema['datasets'][datasets].get('data') is not None:
                callable_str = schema['datasets'][datasets]['data'].get('callable')
                callable_param = schema['datasets'][datasets]['data'].get('params')
                try:
                    module_name, func_name = callable_str.rsplit('.', 1)
                    module = importlib.import_module('.' + module_name, 'tm1_bench_py')
                    generator_func = getattr(module, func_name)
                    generator_kwargs = {
                        'params': callable_param,
                    }
                    generator_func(dataframe,**generator_kwargs)
                except (ImportError, AttributeError, ValueError) as e:
                    basic_logger.error(f"Error resolving function '{callable_str}' for dataset '{datasets}': {e}",
                                       exc_info=True)
                    continue  # Skip to the next data column

        print(dataframe)
        utility._dataframe_to_cube_default(
            tm1_service=tm1,
            dataframe=dataframe,
            cube_name=target_cube,
            cube_dims=cube_dims,
            use_ti=use_ti,
            use_blob=use_blob,
            increment=False,
            async_write=async_write,
            slice_size_of_dataframe=slice_size_of_dataframe
        )

@utility.log_exec_metrics
def build_model(tm1: TM1Service, schema, system_defaults, env):
    if tm1 is None:
        tm1 = utility.tm1_connection()

    # Get the directory where your script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate one level up to project_folder/
    parent_dir = os.path.dirname(script_dir)
    # Create the absolute path to your schema directory
    schema_dir = os.path.join(parent_dir, "schema")
    if schema is None:
        loader = SchemaLoader(schema_dir, env)
        schema = loader.load_schema()

    if system_defaults is None:
        _DEFAULT_DF_TO_CUBE_KWARGS = schema['config']['df_to_cube_default_kwargs']

    try:
        create_dimensions(tm1, schema)
        create_cubes(tm1, schema)
        generate_data(tm1, schema, system_defaults)
    finally:
        tm1.logout()

@utility.log_exec_metrics
def delete_dimensions(tm1: TM1Service, schema):
    for template_type in schema['dimensions']:
        for dimension in schema['dimensions'][template_type]:
            dimension_name = schema['dimensions'][template_type][dimension]['dimension_name']
            if tm1.dimensions.exists(dimension_name):
                tm1.dimensions.delete(dimension_name)

@utility.log_exec_metrics
def delete_cubes(tm1: TM1Service, schema):
    for cubes in schema['cubes']:
        cube_name = schema['cubes'][cubes]['name']
        if tm1.cubes.exists(cube_name):
            tm1.cubes.delete(cube_name)

@utility.log_exec_metrics
def destroy_model(tm1: TM1Service, schema):
    if tm1 is None:
        tm1 = utility.tm1_connection()

    try:
        delete_cubes(tm1, schema)
        delete_dimensions(tm1, schema)
    finally:
        tm1.logout()