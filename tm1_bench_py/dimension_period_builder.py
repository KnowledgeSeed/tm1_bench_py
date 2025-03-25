from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar
import pandas as pd
from tm1_bench_py import exec_metrics_logger, basic_logger

# ------------------------------------------------------------------------------------------------------------
# Utility: CUSTOM PERIOD DIMENSION GENERATOR FOR GENERAL PURPOSES
# ------------------------------------------------------------------------------------------------------------
DTYPE_MAPPING = {
    'date:s': 'string',
    'period_type:s': 'string',
    'date_key:a': 'string',
    'year:s': 'float32',
    'month:s': 'float32',
    'month_name:s': 'string',
    'month_short_name:s': 'string',
    'quarter:s': 'float32',
    'fiscal_year:s': 'float32',
    'period_key:a': 'string',
    'last_day_of_month:s': 'float32'
}


def generate_time_dimension(year_start, year_end, monthly=0, daily=0, quarterly=0,
                            start_month_of_the_year=1, ytd=0, ytg=0, attributes=None):
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
    basic_logger.info("Generating time dimension")

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

    # Add YTD (Year-to-Date) flags if requested
    if ytd:
        df = _add_ytd_attributes(df, start_month_of_the_year)

    # Add YTG (Year-to-Go) flags if requested
    if ytg:
        df = _add_ytg_attributes(df, start_month_of_the_year)

    # Process custom attributes if provided
    if attributes:
        df = _process_custom_attributes(df, attributes)

    # turn col names into tm1py comply with format
    dataframe = pd.DataFrame()
    dataframe = dataframe.assign(
        element_id=df['period_key'].astype(str).str[1:],
        element_type="numeric")
    dataframe = pd.concat([dataframe, _rename_columns(df)], axis=1)
    # add columns for tm1py comform dataframe structures
    dataframe['level000'] = 'All Periods'
    dataframe['level000_weight'] = 0
    dataframe['level001'] = df['year']
    dataframe['level001_weight'] = 1
    dataframe['level002'] = df['year'].astype(str) + 'Q' + df['quarter'].astype(str)
    dataframe['level002_weight'] = 1
    if daily:
        dataframe['level003'] = df['month_name']
        dataframe['level003_weight'] = 1
    # change data col into string
    # Define column types

    dataframe = _create_typed_dimension_dataframe(dataframe, DTYPE_MAPPING)

    basic_logger.info("Generating time dimension finished.")
    print(dataframe)
    return dataframe


def _generate_period_key(row, start_month_of_the_year):
    """Generate a unique period key based on period type."""
    date = row['date']
    period_type = row['period_type']

    # Determine fiscal year
    fiscal_year = date.year if date.month >= start_month_of_the_year else date.year - 1

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


def _process_custom_attributes(df, attributes):
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
                lambda row: _get_reference_period(df, row, referenced_distance),
                axis=1
            )

        elif attr_method == 'format':
            format_pattern = attr.get('format', '')
            df[attr_name] = df.apply(
                lambda row: _format_date(row, format_pattern),
                axis=1
            )

    return df


def _rename_columns(df):
    # Get current column names
    columns = df.columns.tolist()

    # Columns to exclude from renaming
    exclude_columns = [col for col in columns if col.startswith('level') or ':' in col]

    # Create a new dictionary of column names
    new_columns = {}
    for col in columns:
        # Skip columns that are already in the desired format or start with 'level'
        if col in exclude_columns:
            continue

        # Rename to column_name:s format
        if 'key' in col:
            new_columns[col] = f"{col}:a"
        else:
            new_columns[col] = f"{col}:s"

    # Rename the columns
    df = df.rename(columns=new_columns)

    return df


def _create_typed_dimension_dataframe(df, dtype_mapping):
    columns = df.columns.tolist()
    # Convert to appropriate types
    for col in columns:
        if col in dtype_mapping:
            df[col] = df[col].fillna('').astype(dtype_mapping[col])
        elif ':n' in col or 'weight' in col:
            df[col] = df[col].fillna(0).astype('float32')
        elif ':s' in col or ':a' in col or 'level' in col:
            df[col] = df[col].fillna('').astype('string')

    return df


def _get_reference_period(df, row, distance):
    """Get a referenced period based on the current period and distance."""
    period_type = row['period_type']
    date = row['date']

    # For monthly references
    if period_type == 'MONTH':
        reference_date = date + relativedelta(months=distance)
        # Find matching row in DataFrame
        matching_rows = df[(df['period_type'] == period_type) &
                           (df['date'] == reference_date.replace(day=1))]

    # For quarterly references
    elif period_type == 'QUARTER':
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
