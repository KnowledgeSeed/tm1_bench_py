from pathlib import Path
import configparser
from TM1py import TM1Service, SubsetService
from TM1py.Objects import Dimension, Element, ElementAttribute, Hierarchy, Cube, Subset
import utility as utility
import os
import yaml
import importlib
from typing import Dict, List, Any, Callable
from TM1_bedrock_py import basic_logger


def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1

class SchemaLoader:
    def __init__(self, schema_dir: str):
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
        self.generator_cache = {}

    def load_schema(self) -> Dict[str, Any]:
        """Load the main schema file and all referenced files"""
        main_schema_path = os.path.join(self.schema_dir, 'schema.yaml')
        with open(main_schema_path, 'r') as f:
            main_schema = yaml.safe_load(f)

        # Load dimensions by type
        self._load_dimensions(main_schema['import']['dimensions'])

        # Load cubes by type
        self._load_cubes(main_schema['import']['cubes'])

        # Load datasets by type
        self._load_datasets(main_schema['import']['datasets'])

        # Load datasets by type
        self._load_config(main_schema['import']['config'])

        # Load datasets by type
        self._load_variables(main_schema['import']['variables'])

        return {
            'dimensions': self.dimensions,
            'cubes': self.cubes,
            'datasets': self.datasets,
            'variables': self.variables,
            'config': self.config
        }

    def _load_dimensions(self, dimension_refs: Dict[str, List[str]]) -> None:
        """Load all dimension definitions by type"""
        # Load elementlist dimensions
        for dim_name in dimension_refs.get('elementlist', []):
            path = os.path.join(self.schema_dir, 'dimensions', 'elementlist', f"{dim_name}.yaml")
            with open(path, 'r') as f:
                self.dimensions['elementlist'][dim_name] = yaml.safe_load(f)

        # Load template dimensions
        for dim_name in dimension_refs.get('df_templates', []):
            path = os.path.join(self.schema_dir, 'dimensions', 'df_templates', f"{dim_name}.yaml")
            with open(path, 'r') as f:
                self.dimensions['df_templates'][dim_name] = yaml.safe_load(f)

        # Load custom dimensions
        for dim_name in dimension_refs.get('custom', []):
            path = os.path.join(self.schema_dir, 'dimensions', 'custom', f"{dim_name}.yaml")
            with open(path, 'r') as f:
                self.dimensions['custom'][dim_name] = yaml.safe_load(f)

    def _load_cubes(self, cube_refs: Dict[str, List[str]]) -> None:
        """Load all cube definitions by type"""
        for cube_name in cube_refs:
            path = os.path.join(self.schema_dir, 'cubes', f"{cube_name}.yaml")
            with open(path, 'r') as f:
                self.cubes[cube_name] = yaml.safe_load(f)

    def _load_datasets(self, datasets_refs: Dict[str, List[str]]) -> None:
        """Load all dataset definitions by type"""
        for dataset in datasets_refs:
            path = os.path.join(self.schema_dir, 'datasets', f"{dataset}.yaml")
            with open(path, 'r') as f:
                self.datasets[dataset] = yaml.safe_load(f)

    def _load_config(self, config_refs: Dict[str, Any]) -> None:
        """Load config definitions"""
        path = os.path.join(self.schema_dir, "config.yaml")
        if os.path.exists(path):
            with open(path, 'r') as f:
                self.config = yaml.safe_load(f)

    def _load_variables(self, variables_refs: Dict[str, Any]) -> None:
        """Load variables definitions"""
        path = os.path.join(self.schema_dir, "variables.yaml")
        if os.path.exists(path):
            with open(path, 'r') as f:
                self.variables = yaml.safe_load(f)

    def get_generator(self, generator_path: str) -> Callable:
        """Dynamically import a custom generator class"""
        if generator_path in self.generator_cache:
            return self.generator_cache[generator_path]

        module_path, class_name = generator_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        generator_class = getattr(module, class_name)
        self.generator_cache[generator_path] = generator_class
        return generator_class

# generate from Tm1 element, Hierarchy and Dimension Object a dimension
@utility.log_exec_metrics
def create_dimension_from_elementlist(dimension_name,elements_dic,edges,element_attributes_dic,tm1):
    elements = []
    for i in range(len(elements_dic)):
        elements.append(Element(name=elements_dic[i].get("name"), element_type=elements_dic[i].get("element_type")))
    print(elements)
    element_attributes = []
    for i in range(len(element_attributes_dic)):
        element_attributes.append(ElementAttribute(name=element_attributes_dic[i].get("name"),
                                                   attribute_type=element_attributes_dic[i].get("attribute_type")))
    hierarchy = Hierarchy(name=dimension_name, dimension_name=dimension_name, elements=elements,
                          element_attributes=element_attributes,
                          edges=edges)
    dimension = Dimension(name=dimension_name, hierarchies=[hierarchy])
    tm1.dimensions.update_or_create(dimension)

# generate df for the input https://github.com/cubewise-code/tm1py/blob/master/TM1py/Services/HierarchyService.py in update_or_create_hierarchy_from_dataframe
@utility.log_exec_metrics
def create_dimension_from_dataframe_template(tm1,df_template,dimension_name):
    # Generate hierarchy based on template
    hierarchy_dict = utility.generate_hierarchy_dictionary(df_template)

    #this will print only if debug is the logging mode
    utility._print_limited_nested_dictionary(hierarchy_dict)
    total_elements = utility._count_nested_dictionary_elements(hierarchy_dict)
    basic_logger.info(f"\nTotal elements in hierarchy: {total_elements}")

    # Create the DataFrame
    result_df = utility.hierarchy_to_dataframe(df_template,hierarchy_dict)

    tm1.hierarchies.update_or_create_hierarchy_from_dataframe(
        dimension_name=dimension_name,hierarchy_name=dimension_name,df=result_df,
        element_column="element_id",element_type_column="element_type",verify_unique_elements=True,verify_edges=True)

@utility.log_exec_metrics
def create_dimensions(tm1: TM1Service, schema, env):
    for template_type in schema['dimensions']:
        for dimension in schema['dimensions'][template_type]:
            dimension_name = schema['dimensions'][template_type][dimension][env]['dimension_name']
            basic_logger.info(f" {dimension_name} is creating..." )
            print(dimension_name)
            match template_type:
                case "elementlist":
                    edges = schema['dimensions'][template_type][dimension][env]['edges']
                    edges_dict = {}
                    if edges:
                        for parent, child, value in schema['dimensions'][template_type][dimension][env]['edges']:
                            edges_dict[(parent, child)] = value
                    create_dimension_from_elementlist (
                        dimension_name = dimension_name,
                        tm1 = tm1,
                        elements_dic = schema['dimensions'][template_type][dimension][env]['elements'],
                        edges = edges_dict,
                        element_attributes_dic = schema['dimensions'][template_type][dimension][env]['attributes']
                    )
                case "df_templates":
                    create_dimension_from_dataframe_template(
                    dimension_name=dimension_name,
                    tm1=tm1,
                    df_template = schema['dimensions'][template_type][dimension][env]['df_template']
                    )
                case "custom":
                    func = schema['dimensions'][template_type][dimension][env]['callable']
                    kwargs = schema['dimensions'][template_type][dimension][env]['kwargs']
                    if isinstance(func, str):
                        try:
                            # Split the string into module and function name
                            module_name, func_name = func.rsplit('.', 1)
                            module = importlib.import_module(module_name)
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
def create_cubes(tm1: TM1Service, schema, env):
    for cubes in schema['cubes']:
        cube_name = schema['cubes'][cubes][env]['name']
        cube_dimensions = schema['cubes'][cubes][env]['dimensions']
        cube_rules = schema['cubes'][cubes][env]['rules']
        cube = Cube(name=cube_name, dimensions=cube_dimensions)
        tm1.cubes.update_or_create(cube)
        rule_str = '\r\n'.join(cube_rules) + '\r\n'
        tm1.cubes.update_or_create_rules(cube_name=cube_name, rules=rule_str)

if __name__ == '__main__':
    # Get the directory where your script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate one level up to project_folder/
    parent_dir = os.path.dirname(script_dir)
    # Create the absolute path to your schema directory
    schema_dir = os.path.join(parent_dir, "schema")

    loader = SchemaLoader(schema_dir)
    schema = loader.load_schema()

    tm1 = tm1_connection()

    #CONSTANTS
    _ENV = schema['config']['default_yaml_env']
    _DEFAULT_DF_TO_CUBE_KWARGS = schema['config']['df_to_cube_default_kwargs']
    print(_DEFAULT_DF_TO_CUBE_KWARGS)
    try:
        #create_dimensions(tm1, schema, _ENV)
        #create_cubes(tm1, schema, _ENV)
        pass
    finally:
        tm1.logout()
