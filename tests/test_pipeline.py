"""End-to-end pipeline test on a tiny synthetic dataset."""
import duckdb

from pipeline.generate_data import generate
from pipeline.transform import build
from pipeline.validate import run_checks


def test_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    warehouse = tmp_path / "warehouse" / "ecommerce.duckdb"
    marts = tmp_path / "marts"

    counts = generate(raw, n_customers=200, n_orders=1000)
    assert counts["orders"] == 1000
    assert counts["order_items"] >= 1000

    checks = run_checks(raw)
    failed = [c for c in checks if not c["passed"]]
    assert not failed, failed

    built = build(raw, warehouse, marts)
    assert built["fact_orders"] > 0
    assert (marts / "fact_orders.parquet").exists()

    con = duckdb.connect(str(warehouse), read_only=True)
    nulls = con.execute(
        "SELECT COUNT(*) FROM fact_orders WHERE revenue IS NULL").fetchone()[0]
    assert nulls == 0
    total = con.execute(
        "SELECT SUM(revenue) FROM fact_orders WHERE status != 'Cancelled'"
    ).fetchone()[0]
    assert total > 0
    orphans = con.execute("""
        SELECT COUNT(*) FROM fact_order_items foi
        LEFT JOIN dim_products p ON p.product_key = foi.product_key
        WHERE p.product_key IS NULL
    """).fetchone()[0]
    assert orphans == 0
    con.close()
