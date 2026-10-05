"""Build the analytics warehouse: load raw CSVs into DuckDB and model a
star schema (dim_customers, dim_products, dim_dates, fact_orders,
fact_order_items), then export marts as Parquet."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent


def build(raw_dir: Path | str = BASE_DIR / "data" / "raw",
          warehouse_path: Path | str = BASE_DIR / "data" / "warehouse" / "ecommerce.duckdb",
          marts_dir: Path | str = BASE_DIR / "data" / "marts") -> dict:
    raw_dir, marts_dir = Path(raw_dir), Path(marts_dir)
    warehouse_path = Path(warehouse_path)
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    marts_dir.mkdir(parents=True, exist_ok=True)
    if warehouse_path.exists():
        warehouse_path.unlink()

    con = duckdb.connect(str(warehouse_path))

    for table, csv in [("raw_customers", "customers.csv"),
                       ("raw_products", "products.csv"),
                       ("raw_orders", "orders.csv"),
                       ("raw_order_items", "order_items.csv")]:
        con.execute(
            f"CREATE TABLE {table} AS "
            f"SELECT * FROM read_csv('{raw_dir / csv}', header=true)"
        )

    con.execute("""
        CREATE TABLE dim_customers AS
        SELECT ROW_NUMBER() OVER (ORDER BY customer_id) AS customer_key,
               customer_id, full_name, email, city, state,
               CAST(signup_date AS DATE) AS signup_date
        FROM raw_customers
    """)
    con.execute("""
        CREATE TABLE dim_products AS
        SELECT ROW_NUMBER() OVER (ORDER BY product_id) AS product_key,
               product_id, product_name, category, unit_price, unit_cost
        FROM raw_products
    """)

    min_d, max_d = con.execute(
        "SELECT MIN(CAST(order_date AS DATE)), MAX(CAST(order_date AS DATE)) "
        "FROM raw_orders"
    ).fetchone()
    dates = pd.DataFrame({"full_date": pd.date_range(min_d, max_d, freq="D")})
    dates["date_key"] = dates["full_date"].dt.date
    dates["year"] = dates["full_date"].dt.year
    dates["month"] = dates["full_date"].dt.month
    dates["quarter"] = dates["full_date"].dt.quarter
    dates["day_of_week"] = dates["full_date"].dt.dayofweek
    dates["year_month"] = dates["full_date"].dt.strftime("%Y-%m")
    con.register("dates_df", dates)
    con.execute("CREATE TABLE dim_dates AS SELECT * FROM dates_df")

    con.execute("""
        CREATE TABLE fact_order_items AS
        SELECT oi.order_id,
               p.product_key,
               oi.quantity,
               oi.unit_price,
               oi.discount,
               oi.quantity * oi.unit_price * (1 - oi.discount) AS line_revenue,
               oi.quantity * p.unit_cost AS line_cost
        FROM raw_order_items oi
        JOIN dim_products p ON p.product_id = oi.product_id
    """)
    con.execute("""
        CREATE TABLE fact_orders AS
        SELECT o.order_id,
               c.customer_key,
               CAST(o.order_date AS DATE) AS date_key,
               o.status,
               o.payment_method,
               COUNT(*) AS item_count,
               SUM(foi.line_revenue) AS revenue,
               SUM(foi.line_cost) AS cost,
               SUM(foi.line_revenue - foi.line_cost) AS profit
        FROM raw_orders o
        JOIN dim_customers c ON c.customer_id = o.customer_id
        JOIN fact_order_items foi ON foi.order_id = o.order_id
        GROUP BY o.order_id, c.customer_key, CAST(o.order_date AS DATE),
                 o.status, o.payment_method
    """)
    con.execute("""
        CREATE VIEW mart_monthly_kpis AS
        SELECT d.year_month,
               COUNT(DISTINCT fo.order_id) AS orders,
               COUNT(DISTINCT fo.customer_key) AS customers,
               SUM(fo.revenue) AS revenue,
               SUM(fo.profit) AS profit,
               SUM(fo.revenue) / NULLIF(COUNT(DISTINCT fo.order_id), 0) AS aov
        FROM fact_orders fo
        JOIN dim_dates d ON d.date_key = fo.date_key
        WHERE fo.status != 'Cancelled'
        GROUP BY d.year_month
        ORDER BY d.year_month
    """)

    tables = ["dim_customers", "dim_products", "dim_dates",
              "fact_orders", "fact_order_items"]
    for table in tables:
        con.execute(
            f"COPY (SELECT * FROM {table}) "
            f"TO '{marts_dir / (table + '.parquet')}' (FORMAT PARQUET)"
        )

    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in tables}
    con.close()
    return counts


if __name__ == "__main__":
    print("built:", build())
