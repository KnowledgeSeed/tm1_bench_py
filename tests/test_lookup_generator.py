from tm1_bench_py.df_generator_for_dataset import _look_up_based_on_column_value, LOOKUP_CACHE


def _setup_schema():
    return {
        "variables": {
            "pnl_account_type": {
                "Expense": {"sign": "-"},
                "Revenue": {"sign": "+"},
                "Equity": {"sign": "="},
            }
        }
    }


def _setup_row_data():
    return [
        {"Account": "A1", "Attr": "Type", "Value": "Expense"},
        {"Account": "A2", "Attr": "Type", "Value": "Revenue"},
    ]


def test_cached_lookup_returns_expected_value():
    row_data = _setup_row_data()
    cur_row_data = {"Account": "A1", "Attr": "Sign"}
    params = {
        "referred_column": "Type",
        "variable_path": "variables.pnl_account_type",
        "variable_key": "sign",
    }
    schema = _setup_schema()
    LOOKUP_CACHE.clear()

    result = _look_up_based_on_column_value(row_data, cur_row_data, params, schema)
    assert result == "-"
    cache_key = id(row_data)
    series_before = LOOKUP_CACHE[cache_key][0]

    # second call should reuse cached series
    result_again = _look_up_based_on_column_value(row_data, cur_row_data, params, schema)
    series_after = LOOKUP_CACHE[cache_key][0]
    assert result_again == "-"
    assert series_before is series_after


def test_cache_refresh_and_default():
    row_data = _setup_row_data()
    schema = _setup_schema()
    params = {
        "referred_column": "Type",
        "variable_path": "variables.pnl_account_type",
        "variable_key": "sign",
        "default": "N/A",
    }
    LOOKUP_CACHE.clear()
    cache_key = id(row_data)

    # lookup for non-existent account returns default
    result_default = _look_up_based_on_column_value(
        row_data, {"Account": "A3", "Attr": "Sign"}, params, schema
    )
    assert result_default == "N/A"
    assert len(LOOKUP_CACHE[cache_key][0]) == 2

    # append new data and ensure cache refreshes
    row_data.append({"Account": "A3", "Attr": "Type", "Value": "Equity"})
    result = _look_up_based_on_column_value(row_data, {"Account": "A3", "Attr": "Sign"}, params, schema)
    assert result == "="
    assert len(LOOKUP_CACHE[cache_key][0]) == 3
