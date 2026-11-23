import difflib
import pandas as pd 

def load_catalog(path: str) -> list[str]: 
    return pd.read_csv(path)["product"].tolist()

def match_product(name, catalog: list[str]):
    if pd.isna(name) or name == "":
        return None
    lookup = {c.lower() : c for c in catalog}
    matches = difflib.get_close_matches(name.strip().lower(), list(lookup.keys()), n=1, cutoff=0.8)
    if matches:
        return lookup[matches[0]]
    return None
    

def validate(df: pd.DataFrame, catalog: list[str]) -> pd.DataFrame:
    df = df.copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors= "coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors= "coerce")
    df["catalog_product"] = df["product"].apply(lambda name: match_product(name, catalog))
    df["line_total"] = df["unit_price"] * df["quantity"]

    
    is_order = df["is_order"] == True
    rules = {
        "not_an_order": ~is_order,
        "missing_price": is_order & df["unit_price"].isna(),
        "bad_quantity": is_order & (df["quantity"].isna() | (df["quantity"] <= 0)),
        "unknown_product": is_order & df["catalog_product"].isna(),
        "missing_currency": is_order & df["unit_price"].notna() & df["currency"].isna(),
    }

    df["issues"] = ""
    for label, mask in rules.items():
        df.loc[mask, "issues"] = df.loc[mask, "issues"] + label + ";"
    return df



