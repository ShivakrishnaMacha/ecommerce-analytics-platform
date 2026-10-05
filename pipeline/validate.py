"""Data quality checks on the raw CSV tables.

Each check returns a dict: {check, table, passed, details}.
Critical failures cause run_pipeline to abort before the warehouse build.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _load(raw_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.read_csv(raw_dir / "customers.csv",
                                 parse_dates=["signup_date"]),
        "products": pd.read_csv(raw_dir / "products.csv"),
        "orders": pd.read_csv(raw_dir / "orders.csv",
                              parse_dates=["order_date"]),
        "order_items": pd.read_csv(raw_dir / "order_items.csv"),
    }


def run_checks(raw_dir: Path | str = BASE_DIR / "data" / "raw") -> list[dict]:
    raw_dir = Path(raw_dir)
    tables = _load(raw_dir)
    customers, products = tables["customers"], tables["products"]
    orders, items = tables["orders"], tables["order_items"]
    checks: list[dict] = []

    def add(name: str, table: str, passed: bool, details: str = ""):
        checks.append({"check": name, "table": table,
                       "passed": bool(passed), "details": details})

    add("pk_not_null", "customers", customers["customer_id"].notna().all())
    add("pk_unique", "customers", customers["customer_id"].is_unique,
        f"{customers['customer_id'].duplicated().sum()} duplicates")
    bad_emails = (~customers["email"].str.match(EMAIL_RE, na=False)).sum()
    add("email_format", "customers", bad_emails == 0, f"{bad_emails} bad emails")

    add("pk_not_null", "products", products["product_id"].notna().all())
    add("pk_unique", "products", products["product_id"].is_unique)
    add("price_positive", "products", (products["unit_price"] > 0).all())
    add("cost_below_price", "products",
        (products["unit_cost"] < products["unit_price"]).all())

    add("pk_not_null", "orders", orders["order_id"].notna().all())
    add("pk_unique", "orders", orders["order_id"].is_unique)
    orphan_cust = (~orders["customer_id"].isin(customers["customer_id"])).sum()
    add("fk_customer", "orders", orphan_cust == 0,
        f"{orphan_cust} orphan customer_ids")
    in_range = orders["order_date"].between("2024-07-01", "2025-12-31").all()
    add("date_in_range", "orders", bool(in_range))
    add("status_valid", "orders",
        orders["status"].isin(["Delivered", "Returned", "Cancelled"]).all())

    add("fk_order", "order_items",
        items["order_id"].isin(orders["order_id"]).all(),
        f"{(~items['order_id'].isin(orders['order_id'])).sum()} orphans")
    add("fk_product", "order_items",
        items["product_id"].isin(products["product_id"]).all())
    add("quantity_positive", "order_items", (items["quantity"] >= 1).all())
    add("unit_price_positive", "order_items", (items["unit_price"] > 0).all())
    add("discount_in_range", "order_items",
        items["discount"].between(0, 1).all())

    return checks


def main() -> int:
    checks = run_checks()
    failed = [c for c in checks if not c["passed"]]
    for c in checks:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"[{mark}] {c['table']}.{c['check']} {c['details']}")
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
