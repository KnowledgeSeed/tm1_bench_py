from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar
import random
import string
import pandas as pd
from TM1py import TM1Service

def tm1_connection():
    """Creates a TM1 connection before tests and closes it after all tests."""
    config = configparser.ConfigParser()
    config.read(Path(__file__).parent.joinpath('config.ini'))

    tm1 = TM1Service(**config['testbench'])
    return tm1

def generate_time_dimension(year_start, year_end, monthly=0, daily=0, quarterly=0,
                            start_month_of_the_year=1, YTD=0, YTG=0, attributes=None):
    """
    Generate a time dimension DataFrame with specified attributes and time periods.

    Parameters:
    -----------
    year_start : int
        Start year of the time dimension
    year_end : int
        End year of the time dimension
    monthly : int
        Flag to generate monthly periods (1 for yes, 0 for no)
    daily : int
        Flag to generate daily periods (1 for yes, 0 for no)
    quarterly : int
        Flag to generate quarterly periods (1 for yes, 0 for no)
    start_month_of_the_year : int
        Starting month of the fiscal/business year (1-12)
    YTD : int
        Flag to add Year-to-Date calculations (1 for yes, 0 for no)
    YTG : int
        Flag to add Year-to-Go calculations (1 for yes, 0 for no)
    attributes : list
        List of dictionaries defining additional attributes to calculate

    Returns:
    --------
    pandas.DataFrame
        Time dimension DataFrame with all requested periods and attributes
    """
    print("Generating time dimension")

    # Initialize empty list to store date records
    records = []

    # Define the first and last date based on inputs
    start_date = datetime(year_start, start_month_of_the_year, 1)
    end_date = datetime(year_end, 12, 31)

    # Generate date ranges based on specified granularity
    dates = []

    # Generate daily dates if requested
    if daily:
        daily_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        key_format = '%Y-%m-%d'
        for date in daily_dates:
            dates.append({"date": date, "period_type": "DAY"})

    # Generate monthly dates if requested
    if monthly:
        monthly_dates = pd.date_range(start=start_date, end=end_date, freq='MS')  # Month Start
        key_format = '%Y-%m'
        for date in monthly_dates:
            dates.append({"date": date, "period_type": "MONTH"})

    # Generate quarterly dates if requested
    if quarterly:
        # Define custom quarters based on start_month_of_the_year
        current_date = start_date
        key_format = '%Y-%m-%d'
        while current_date <= end_date:
            # First day of each quarter
            for i in range(4):
                quarter_start = current_date + relativedelta(months=i * 3)
                if quarter_start <= end_date:
                    dates.append({"date": quarter_start, "period_type": "QUARTER"})
            current_date = current_date + relativedelta(years=1)

    # Create the base DataFrame
    df = pd.DataFrame(dates)

    if df.empty:
        raise ValueError("No dates generated. Please set at least one period type (daily, monthly, quarterly) to 1.")

    # Add basic time attributes
    df['date_key'] = df['date'].apply(lambda x: x.strftime(key_format))
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    df['month_name'] = df['date'].dt.month_name()
    df['month_short_name'] = df['date'].dt.strftime('%b')
    if daily:
        df['day'] = df['date'].dt.day
        df['day_of_week'] = df['date'].dt.dayofweek + 1  # 1-7 instead of 0-6
        df['day_name'] = df['date'].dt.day_name()
        # Add is_weekend
        df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x >= 6 else 0)
    # Add quarter information
    # This adjusts for fiscal year start month
    df['quarter'] = df.apply(
        lambda row: ((row['month'] - start_month_of_the_year) % 12) // 3 + 1,
        axis=1
    )

    # Add fiscal year
    df['fiscal_year'] = df.apply(
        lambda row: row['year'] if row['month'] >= start_month_of_the_year else row['year'] - 1,
        axis=1
    )

    # Generate period keys based on period_type
    df['period_key'] = df.apply(
        lambda row: _generate_period_key(row, start_month_of_the_year),
        axis=1
    )

    # Add last day of month
    df['last_day_of_month'] = df.apply(
        lambda row: calendar.monthrange(row['year'], row['month'])[1],
        axis=1
    )

    print(df)
    df.to_csv('output.csv', index=False, mode='w')

    # Add YTD (Year-to-Date) flags if requested
    if YTD:
        df = _add_ytd_attributes(df, start_month_of_the_year)

    # Add YTG (Year-to-Go) flags if requested
    if YTG:
        df = _add_ytg_attributes(df, start_month_of_the_year)

    # Process custom attributes if provided
    if attributes:
        df = _process_custom_attributes(df, attributes, start_month_of_the_year)

    return df


def _generate_period_key(row, start_month_of_the_year):
    """Generate a unique period key based on period type."""
    date = row['date']
    period_type = row['period_type']

    # Determine fiscal year
    fiscal_year = date.year if date.month >= start_month_of_the_year else date.year - 1

    # Calculate fiscal period based on period type
    result = ""

    switch_dict = {
        "DAY": f"D{fiscal_year}{date.strftime('%m%d')}",
        "MONTH": f"M{fiscal_year}{date.strftime('%m')}",
        "QUARTER": f"Q{fiscal_year}Q{((date.month - start_month_of_the_year) % 12) // 3 + 1}"
    }

    return switch_dict.get(period_type, f"Unknown-{date.strftime('%Y%m%d')}")


def _add_ytd_attributes(df, start_month_of_the_year):
    """Add Year-to-Date related attributes to the DataFrame."""

    # Group by fiscal year and period type
    grouped = df.groupby(['fiscal_year', 'period_type'])

    # Initialize YTD columns
    df['ytd_sequence'] = 0
    df['is_ytd'] = 0

    # Process each fiscal year and period type group
    for (fy, pt), group_df in grouped:
        # Sort by date within each group
        sorted_group = group_df.sort_values('date')

        # Assign sequence numbers
        sequence = range(1, len(sorted_group) + 1)
        df.loc[sorted_group.index, 'ytd_sequence'] = list(sequence)

        # Current month in fiscal year
        current_month = datetime.now().month
        current_year = datetime.now().year

        # Calculate fiscal year for current date
        current_fiscal_year = current_year
        if current_month < start_month_of_the_year:
            current_fiscal_year -= 1

        # If we're processing the current fiscal year, mark YTD periods
        if fy == current_fiscal_year:
            # All periods up to current date are YTD
            df.loc[sorted_group[sorted_group['date'] <= datetime.now()].index, 'is_ytd'] = 1

    return df


def _add_ytg_attributes(df, start_month_of_the_year):
    """Add Year-to-Go related attributes to the DataFrame."""

    # Group by fiscal year and period type
    grouped = df.groupby(['fiscal_year', 'period_type'])

    # Initialize YTG columns
    df['ytg_sequence'] = 0
    df['is_ytg'] = 0

    # Process each fiscal year and period type group
    for (fy, pt), group_df in grouped:
        # Sort by date within each group
        sorted_group = group_df.sort_values('date', ascending=False)

        # Assign sequence numbers (reverse order for YTG)
        sequence = range(1, len(sorted_group) + 1)
        df.loc[sorted_group.index, 'ytg_sequence'] = list(sequence)

        # Current month in fiscal year
        current_month = datetime.now().month
        current_year = datetime.now().year

        # Calculate fiscal year for current date
        current_fiscal_year = current_year
        if current_month < start_month_of_the_year:
            current_fiscal_year -= 1

        # If we're processing the current fiscal year, mark YTG periods
        if fy == current_fiscal_year:
            # All periods from current date forward are YTG
            df.loc[sorted_group[sorted_group['date'] >= datetime.now()].index, 'is_ytg'] = 1

    return df


def _process_custom_attributes(df, attributes, start_month_of_the_year):
    """Process custom attributes based on the provided specifications."""

    for attr in attributes:
        attr_name = attr.get('name')
        attr_type = attr.get('type')
        attr_method = attr.get('method')

        # Skip if required attributes are missing
        if not all([attr_name, attr_type, attr_method]):
            continue

        # Process based on method type
        if attr_method == 'time_reference':
            referenced_distance = attr.get('referenced_period_distance', 0)
            df[attr_name] = df.apply(
                lambda row: _get_reference_period(df, row, referenced_distance,start_month_of_the_year),
                axis=1
            )

        elif attr_method == 'format':
            format_pattern = attr.get('format', '')
            df[attr_name] = df.apply(
                lambda row: _format_date(row, format_pattern),
                axis=1
            )

    return df


def _get_reference_period(df, row, distance,start_month_of_the_year):
    """Get a referenced period based on the current period and distance."""
    period_key = row['period_key']
    period_type = row['period_type']
    date = row['date']

    # For monthly references
    if period_type == 'MONTH':
        reference_date = date + relativedelta(months=distance)
        gen_date = _generate_period_key(row,start_month_of_the_year)
        print(reference_date)
        # Find matching row in DataFrame
        matching_rows = df[(df['period_type'] == period_type) &
                           (df['date'] == reference_date.replace(day=1))]

    # For quarterly references
    elif period_type == 'QUARTER':
        reference_date = date + relativedelta(months=3 * distance)
        # Find matching row in DataFrame
        matching_rows = df[(df['period_type'] == period_type) &
                           (df['quarter'] == ((row['quarter'] + distance - 1) % 4) + 1) &
                           (df['fiscal_year'] == (row['fiscal_year'] + ((row['quarter'] + distance - 1) // 4)))]

    # For daily references
    else:  # period_type == 'DAY'
        reference_date = date + timedelta(days=distance)
        # Find matching row in DataFrame
        matching_rows = df[(df['period_type'] == period_type) &
                           (df['date'] == reference_date)]

    # Return the period key of the reference period if found
    if not matching_rows.empty:
        return matching_rows.iloc[0]['period_key']
    else:
        return None


def _format_date(row, format_pattern):
    """Format date according to specified pattern."""
    date = row['date']

    # Process pattern components
    result = format_pattern

    # Replace common format patterns
    format_dict = {
        'YYYY': str(date.year),
        'YY': str(date.year)[-2:],
        'MM': str(date.month).zfill(2),
        'M': str(date.month),
        'MMM': date.strftime('%b'),
        'MMMM': date.strftime('%B'),
        'DD': str(date.day).zfill(2),
        'D': str(date.day),
        'Q': str(row['quarter']),
        'FY': str(row['fiscal_year'])
    }

    # Apply replacements
    for key, value in format_dict.items():
        result = result.replace(key, value)

    return result




def traverse_hierarchy(node, path=None, weights=None, rows=None):
    """
    Recursive function to traverse the hierarchical tree structure.

    Parameters:
    node (dict): Current node in the hierarchy
    path (dict): Dictionary tracking the path from root to current node
    weights (dict): Dictionary tracking weights from root to current node
    rows (list): List to collect row data for the DataFrame

    Returns:
    list: Collected rows for the DataFrame
    """
    if path is None:
        path = {}
    if weights is None:
        weights = {}
    if rows is None:
        rows = []

    # Add current node to path
    current_level = node.get('level')
    if current_level != 'leaf':
        path[current_level] = node.get('element_name')
        weights[f"{current_level}_weight"] = node.get('weight')

    # If it's a leaf node, create a row
    if 'children' not in node or not node['children']:
        row = {
            'element_id': node.get('element_name'),
            'element_type': node.get('type')
        }

        # Add path information
        for level, name in path.items():
            row[level] = name

        # Add weight information
        for weight_key, weight_val in weights.items():
            row[weight_key] = weight_val

        rows.append(row)

    # Recursively process children
    if 'children' in node and node['children']:
        for child in node['children']:
            # Create copies of path and weights to avoid modifying the original
            child_path = path.copy()
            child_weights = weights.copy()
            traverse_hierarchy(child, child_path, child_weights, rows)

    return rows

def generate_element_attributes(attribute_info, num_elements):
    """
    Generate attributes for elements based on attribute info.

    Parameters:
    attribute_info (dict): Information about how to generate the attribute
    num_elements (int): Number of elements to generate attributes for

    Returns:
    list: List of attribute values
    """
    attribute_name = attribute_info["name"]
    attribute_type = attribute_name.split(":")[-1] if ":" in attribute_name else "s"  # Default to string

    # Initialize result list
    values = []

    if "constant_content" in attribute_info:
        # Same value for all elements
        constant_value = attribute_info["constant_content"]
        values = [constant_value] * num_elements

    elif "constant_list" in attribute_info:
        # Randomly select from list for each element
        options = attribute_info["constant_list"]
        values = [random.choice(options) for _ in range(num_elements)]

    elif "range" in attribute_info:
        # Generate values within a range
        min_val = attribute_info["range"]["min"]
        max_val = attribute_info["range"]["max"]
        if attribute_type == ("n"):  # Integer
            values = [random.randint(min_val, max_val) for _ in range(num_elements)]
        else:  # Default to string representation
            values = [str(random.uniform(min_val, max_val)) for _ in range(num_elements)]

    elif "template" in attribute_info:
        # Generate based on template
        template = attribute_info["template"]
        prefix = template.get("Prefix", "")
        length = template.get("Length", 5)

        if template.get("Method") == "random":
            # Random characters
            chars = string.ascii_uppercase + string.digits if attribute_type == "s" else string.digits
            values = [f"{prefix}{''.join(random.choices(chars, k=length))}" for _ in range(num_elements)]
        else:
            # Sequential
            values = [f"{prefix}{str(i + 1).zfill(length)}" for i in range(num_elements)]

    else:
        # Default: empty strings or zeros
        if attribute_type == "i":
            values = [0] * num_elements
        elif attribute_type == "f":
            values = [0.0] * num_elements
        else:
            values = [""] * num_elements

    return values

def hierarchy_to_dataframe(df_template, hierarchy_dict):
    """
    Convert a hierarchical tree structure (nested dictionary) to a pandas DataFrame.

    Parameters:
    data (dict): Nested dictionary representing a hierarchical tree structure

    Returns:
    pandas.DataFrame: Flattened representation of the hierarchy
    """
    # Traverse the hierarchy and collect rows
    rows = traverse_hierarchy(hierarchy_dict)

    # Create DataFrame from collected rows
    df = pd.DataFrame(rows)

    # Ensure all expected columns are present for hierarchy
    level_columns = [level_info["name"] for level_info in df_template["levels"]]
    level_weight_columns = [f"{level}_weight" for level in level_columns]

    expected_columns = ["element_id", "element_type"] + level_columns + level_weight_columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
        else:
            # Replace NaN values with 0
            df[col] = df[col].fillna(0)

    # Add attributes if specified in template
    if "attributes" in df_template:
        num_elements = len(df)
        for attribute_info in df_template["attributes"]:
            attribute_name = attribute_info["name"].split(":")[0] if ":" in attribute_info["name"] else attribute_info[
                "name"]
            attribute_values = generate_element_attributes(attribute_info, num_elements)
            df[attribute_name] = attribute_values

    # Reorder columns
    column_order = ["element_id", "element_type"] + level_columns + level_weight_columns
    if "attributes" in df_template:
        attribute_names = [attr_info["name"].split(":")[0] if ":" in attr_info["name"] else attr_info["name"]
                           for attr_info in df_template["attributes"]]
        column_order += attribute_names

    # Only include columns that exist in the dataframe
    column_order = [col for col in column_order if col in df.columns]
    df = df[column_order]

    return df

def generate_hierarchy_dictionary(df_template):
    """
    Generate a nested dictionary representing a hierarchical structure based on a template.

    Parameters:
    df_template (dict): Template containing instructions for generating the hierarchy

    Returns:
    dict: Generated hierarchical nested dictionary
    """
    # Extract template information
    elements_info = df_template["elements"]
    levels_info = df_template["levels"]

    # Generate leaf elements
    num_elements = elements_info["NumberOfElements"]
    element_prefix = elements_info["ElementPrefix"]
    element_length = elements_info["ElementLength"]

    elements = []
    for i in range(1, num_elements + 1):
        if elements_info["Method"] == "enumerate":
            # Generate element name with prefix and sequential number
            element_name = f"{element_prefix}{str(i).zfill(element_length - len(element_prefix))}"
        else:
            # For other methods, we could implement different generation logic
            # For now, default to random if not enumerate
            random_suffix = ''.join(random.choices(string.digits, k=element_length - len(element_prefix)))
            element_name = f"{element_prefix}{random_suffix}"

        elements.append({
            "type": "numeric",
            "level": "leaf",
            "element_name": element_name,
            "weight": 1
        })

    # Process levels from bottom to top (reverse order)
    levels_reversed = list(reversed(levels_info))

    # Start with leaf elements as current_nodes
    current_nodes = elements

    # Process each level to build the hierarchy
    for level_info in levels_reversed:
        level_name = level_info["name"]

        # Determine number of groups at this level
        if level_name == levels_info[0]["name"]:  # Top level (root)
            num_groups = 1
        elif "content_template" in level_info:
            # Determine a reasonable number of groups based on current nodes and level
            # A simple approach: we'll use approximately sqrt of the number of current nodes
            num_groups = max(1, int(len(current_nodes) ** 0.5))
        else:
            num_groups = 1

        # Create groups
        new_nodes = []
        nodes_per_group = len(current_nodes) // num_groups
        remainder = len(current_nodes) % num_groups

        start_idx = 0
        for i in range(num_groups):
            # Distribute nodes evenly accounting for remainder
            group_size = nodes_per_group + (1 if i < remainder else 0)
            group_nodes = current_nodes[start_idx:start_idx + group_size]
            start_idx += group_size

            # Generate group name
            if level_name == levels_info[0]["name"] and "constant_content" in level_info:
                # Use constant content for top level
                group_name = level_info["constant_content"]
            elif "content_template" in level_info:
                # Generate name based on template
                template = level_info["content_template"]
                prefix = template["Prefix"]
                length = template["Length"]

                if template["Method"] == "random":
                    # Generate random suffix
                    suffix = ''.join(random.choices(string.digits, k=length))
                    group_name = f"{prefix}{suffix}"
                else:
                    # Default to sequential numbering
                    group_name = f"{prefix}{str(i + 1).zfill(length)}"
            else:
                # Default name
                group_name = f"{level_name}_group_{i + 1}"

            # Create group node
            group_node = {
                "type": "consolidated",
                "level": level_name,
                "element_name": group_name,
                "weight": 1,
                "children": group_nodes
            }

            new_nodes.append(group_node)

        # Update current_nodes for next level processing
        current_nodes = new_nodes

    # Return the root node (should be only one node at the end)
    if current_nodes:
        return current_nodes[0]
    else:
        # Handle edge case of empty result
        return {
            "type": "consolidated",
            "level": levels_info[0]["name"],
            "element_name": "Empty Hierarchy",
            "weight": 1,
            "children": []
        }

# Print a limited version for demonstration
def print_limited_hierarchy(node, depth=0, max_children=2, max_depth=2):
    """Helper function to print a limited view of the hierarchy for demonstration"""
    indent = "  " * depth
    print(f"{indent}- {node['element_name']} ({node['level']})")

    if depth < max_depth and 'children' in node and node['children']:
        children_to_print = node['children'][:max_children]
        for child in children_to_print:
            print_limited_hierarchy(child, depth + 1, max_children, max_depth)
        if len(node['children']) > max_children:
            print(f"{indent}  ... and {len(node['children']) - max_children} more children")

# Count total elements
def count_elements(node):
    """Helper function to count total elements in the hierarchy"""
    if 'children' not in node or not node['children']:
        return 1
    return sum(count_elements(child) for child in node['children'])
