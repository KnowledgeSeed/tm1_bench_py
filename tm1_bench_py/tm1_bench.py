from pathlib import Path
import configparser
from TM1py.Exceptions import TM1pyRestException
import pandas as pd
from TM1py import TM1Service
from TM1py.Objects import Dimension, Element, ElementAttribute, Hierarchy, Cube
import utility as utility
import pytest
import parametrize_from_file

def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1

# generate from Tm1 element, Hierarchy and Dimension Object a dimension
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
def create_dimension_from_dataframe_template(tm1,df_template,dimension_name):
    # Generate hierarchy based on template
    hierarchy_dict = utility.generate_hierarchy_dictionary(df_template)
    print("\nGenerated Hierarchy Preview:")
    utility._print_limited_nested_dictionary(hierarchy_dict)

    total_elements = utility._count_nested_dictionary_elements(hierarchy_dict)
    print(f"\nTotal elements in hierarchy: {total_elements}")

    # Create the DataFrame
    result_df = utility.hierarchy_to_dataframe(df_template,hierarchy_dict)

    # Display the result
    print(result_df)
    tm1.hierarchies.update_or_create_hierarchy_from_dataframe(
        dimension_name=dimension_name,hierarchy_name=dimension_name,df=result_df,
        element_column="element_id",element_type_column="element_type",verify_unique_elements=True,verify_edges=True,
        unwind_all=True,update_attribute_types=True)

@parametrize_from_file
def create_dimensions(tm1: TM1Service):
    for i in range(len(_BENCH_DIMENSIONS_TEMPLATE)):
        dimension_name = _BENCH_DIMENSIONS_TEMPLATE[i].get("dimension_name")
        template_type = _BENCH_DIMENSIONS_TEMPLATE[i].get("template_type")
        match template_type:
            case "ElementList":
                create_dimension_from_elementlist (
                    dimension_name = dimension_name,
                    tm1 = tm1,
                    elements_dic = _BENCH_DIMENSIONS_TEMPLATE[i].get("elements"),
                    edges = _BENCH_DIMENSIONS_TEMPLATE[i].get("edges"),
                    element_attributes_dic = _BENCH_DIMENSIONS_TEMPLATE[i].get("element_attributes"),
                )
            case "df":
                create_dimension_from_dataframe_template(
                dimension_name=dimension_name,
                tm1=tm1,
                df_template = _BENCH_DIMENSIONS_TEMPLATE[i].get("df_template")
                )
            case "function":
                func = _BENCH_DIMENSIONS_TEMPLATE[i].get("callable")
                kwargs = _BENCH_DIMENSIONS_TEMPLATE[i].get("kwargs")
                time_dim = func(**kwargs)
                print(f"Generated time dimension with {len(time_dim)} rows.")
                print(time_dim.head())

if __name__ == '__main__':
    tm1 = tm1_connection()
    create_dimensions(tm1)

