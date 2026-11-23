import pandas as pd

from validate import match_product, validate

CATALOG = ["Oud Royale 100ml EDP", "Rose Musk Body Mist 250ml"]


def make_row(**changes):
    row = {
        "product": "Oud Royale 100ml EDP",
        "quantity": 10,
        "unit_price": 185.0,
        "currency": "AED",
        "is_order": True,
    }
    row.update(changes)
    return row


def run(row):
    return validate(pd.DataFrame([row]), CATALOG).loc[0]


def test_clean_row_has_no_issues():
    assert run(make_row())["issues"] == ""


def test_missing_price_is_flagged():
    assert "missing_price" in run(make_row(unit_price=None))["issues"]


def test_zero_quantity_is_flagged():
    assert "bad_quantity" in run(make_row(quantity=0))["issues"]


def test_unknown_product_is_flagged():
    assert "unknown_product" in run(make_row(product="Travel Atomizer Set"))["issues"]


def test_not_an_order_gets_only_one_flag():
    result = run(make_row(is_order=False, product=None, quantity=None, unit_price=None))
    assert result["issues"] == "not_an_order;"


def test_close_name_matches_catalog():
    assert match_product("  oud royale 100ml edp ", CATALOG) == "Oud Royale 100ml EDP"


def test_line_total():
    assert run(make_row(quantity=2, unit_price=10.0))["line_total"] == 20.0