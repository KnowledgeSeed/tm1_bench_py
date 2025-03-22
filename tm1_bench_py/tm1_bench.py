from pathlib import Path
import configparser
from TM1py.Exceptions import TM1pyRestException
import pandas as pd
from TM1py import TM1Service
from TM1py.Objects import Dimension, Element, ElementAttribute, Hierarchy, Cube
import utils.py


# generate df for the input https://github.com/cubewise-code/tm1py/blob/master/TM1py/Services/HierarchyService.py in update_or_create_hierarchy_from_dataframe
def create_diemnsion_from_dataframe_template(tm1,df_template,dimension_name):
    # Generate hierarchy based on template
    hierarchy_dict = generate_hierarchy_dictionary(df_template)
    print("\nGenerated Hierarchy Preview:")
    print_limited_hierarchy(hierarchy_dict)

    total_elements = count_elements(hierarchy_dict)
    print(f"\nTotal elements in hierarchy: {total_elements}")

    # Create the DataFrame
    result_df = hierarchy_to_dataframe(df_template,hierarchy_dict)

    # Display the result
    print(result_df)
    tm1.hierarchies.update_or_create_hierarchy_from_dataframe(
        dimension_name=dimension_name,hierarchy_name=dimension_name,df=result_df,
        element_column="element_id",element_type_column="element_type",verify_unique_elements=True,verify_edges=True,
        unwind_all=True,update_attribute_types=True)

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
                create_diemnsion_from_dataframe_template(
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
    pass



