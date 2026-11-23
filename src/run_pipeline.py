import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from extract_one import Order, extract_order
from sheets import write_tab
from validate import load_catalog, validate

EMAIL_DIR = Path("emails")
CACHE_DIR = Path("output/json")
COLUMNS = [
    "source_file", "sender_company", "sender_email", "order_reference", "order_date",
    "product", "catalog_product", "quantity", "unit_price", "currency", "line_total",
    "issues", "notes",
]


def get_order(email_path: Path) -> Order:
    cache_path = CACHE_DIR / f"{email_path.stem}.json"
    if cache_path.exists():
        return Order.model_validate_json(cache_path.read_text(encoding="utf-8"))

    order = extract_order(email_path.read_text(encoding="utf-8"))
    cache_path.write_text(order.model_dump_json(indent=2), encoding="utf-8")
    time.sleep(2)
    return order


def order_to_rows(order: Order, source_file: str) -> list[dict]:
    base = {
        "source_file": source_file,
        "sender_company": order.sender_company,
        "sender_email": order.sender_email,
        "order_reference": order.order_reference,
        "order_date": order.order_date,
        "notes": order.notes,
        "is_order": order.is_order,
    }
    if not order.lines:
        return [{**base, "product": None, "quantity": None, "unit_price": None, "currency": None}]
    return [{**base, **line.model_dump()} for line in order.lines]


def main():
    load_dotenv()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = []
    failed = []
    for email_path in sorted(EMAIL_DIR.glob("*.txt")):
        print(f"Processing {email_path.name}...")
        try:
            order = get_order(email_path)
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append(email_path.name)
            continue
        all_rows.extend(order_to_rows(order, email_path.name))

    df = pd.DataFrame(all_rows)
    df = validate(df, load_catalog("data/catalog.csv"))
    df = df[COLUMNS]
    df.to_csv("output/orders.csv", index=False)

    clean = df[df["issues"] == ""]
    review = df[df["issues"] != ""]

    sheet_id = os.environ["SHEET_ID"]
    write_tab(sheet_id, "Clean", clean)
    write_tab(sheet_id, "Review", review)

    print(f"\nDone: {len(clean)} clean rows, {len(review)} rows to review, {len(failed)} emails failed {failed}")


if __name__ == "__main__":
    main()