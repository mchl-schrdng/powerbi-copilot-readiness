from copilot_readiness.tmdl_parser import parse_model


def test_parses_good_star_tables_and_columns(good_star_path):
    model = parse_model(good_star_path)
    assert model.name == "good_star"
    table_names = {t.name for t in model.tables}
    assert {"Sales", "Customer", "Product", "Date", "Geography"} <= table_names

    sales = model.table_by_name("Sales")
    customer_key = sales.column_by_name("CustomerKey")
    assert customer_key.is_hidden is True
    assert customer_key.data_type == "int64"
    assert customer_key.summarize_by == "none"
    assert any(m.name == "Total Revenue" for m in sales.measures)


def test_parses_descriptions(good_star_path):
    model = parse_model(good_star_path)
    sales = model.table_by_name("Sales")
    assert sales.description and "Sales transactions" in sales.description
    name_col = model.table_by_name("Customer").column_by_name("CustomerName")
    assert name_col.description and "business" in name_col.description


def test_parses_relationships_with_defaults(good_star_path):
    model = parse_model(good_star_path)
    assert len(model.relationships) == 4
    rel = next(r for r in model.relationships if r.name == "Sales_Customer")
    assert rel.from_table == "Sales"
    assert rel.from_column == "CustomerKey"
    assert rel.to_table == "Customer"
    assert rel.is_active is True
    assert rel.is_many_to_many is False
    assert rel.is_bidirectional is False


def test_parses_relationship_overrides(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    bidi = next(r for r in model.relationships if r.name == "f_Product")
    assert bidi.is_bidirectional is True

    inactive = next(r for r in model.relationships if r.name == "f_ShipDate")
    assert inactive.is_active is False

    m2m = next(r for r in model.relationships if r.name == "f_Promotion")
    assert m2m.is_many_to_many is True


def test_geo_data_category_parsed(good_star_path):
    model = parse_model(good_star_path)
    country = model.table_by_name("Geography").column_by_name("Country")
    assert country.data_category == "Country"
