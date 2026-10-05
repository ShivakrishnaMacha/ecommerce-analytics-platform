"""Synthetic e-commerce dataset generator (seeded, reproducible).

Produces four CSV tables under data/raw/:
    customers.csv, products.csv, orders.csv, order_items.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
rng = np.random.default_rng(42)

BASE_DIR = Path(__file__).resolve().parent.parent

PRODUCT_TYPES = {
    "Electronics": ["Wireless Headphones", "Smart Watch", "Bluetooth Speaker",
                    "Laptop Stand", "USB-C Hub", "Mechanical Keyboard"],
    "Fashion": ["Denim Jacket", "Running Shoes", "Cotton T-Shirt",
                "Wool Sweater", "Leather Wallet", "Sunglasses"],
    "Home & Kitchen": ["Air Fryer", "Ceramic Cookware Set", "Robot Vacuum",
                       "Blender", "Dining Table Set", "Bedding Set"],
    "Sports": ["Yoga Mat", "Dumbbell Set", "Camping Tent",
               "Road Bicycle", "Tennis Racket", "Fitness Tracker"],
    "Beauty": ["Vitamin C Serum", "Moisturizer", "Hair Dryer",
               "Makeup Kit", "Face Wash", "Eau de Parfum"],
    "Books": ["Mystery Novel", "Self-Help Book", "Cookbook",
              "Sci-Fi Trilogy", "Biography", "Children's Picture Book"],
    "Toys": ["Building Blocks Set", "Remote Control Car", "Doll House",
             "Puzzle 1000pc", "Board Game", "Plush Toy"],
    "Grocery": ["Organic Coffee Beans", "Protein Powder", "Olive Oil",
                "Granola Bars Pack", "Green Tea Box", "Almonds 1kg"],
}
BRANDS = ["Nova", "VoltEdge", "UrbanThread", "CasaHome", "FlexPro", "GlowLab",
          "PageTurner", "PlayZone", "FarmFresh", "TechNest", "ModaFit", "DuraCook"]
PRICE_RANGE = {
    "Electronics": (25, 400), "Fashion": (15, 150), "Home & Kitchen": (20, 250),
    "Sports": (20, 200), "Beauty": (10, 80), "Books": (8, 40),
    "Toys": (12, 90), "Grocery": (5, 60),
}
STATUSES = ["Delivered", "Returned", "Cancelled"]
STATUS_PROBS = [0.92, 0.05, 0.03]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "UPI", "PayPal", "Net Banking"]
PAYMENT_PROBS = [0.45, 0.25, 0.15, 0.10, 0.05]


def _gen_customers(n: int) -> pd.DataFrame:
    signup_start = pd.Timestamp("2022-06-01")
    signup_end = pd.Timestamp("2025-06-30")
    span = (signup_end - signup_start).days
    return pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(1, n + 1)],
        "full_name": [fake.name() for _ in range(n)],
        "email": [fake.email() for _ in range(n)],
        "city": [fake.city() for _ in range(n)],
        "state": [fake.state_abbr() for _ in range(n)],
        "signup_date": [
            (signup_start + pd.Timedelta(days=int(d))).date()
            for d in rng.integers(0, span + 1, n)
        ],
    })


def _gen_products() -> pd.DataFrame:
    rows = []
    pid = 1
    for category, types in PRODUCT_TYPES.items():
        lo, hi = PRICE_RANGE[category]
        for ptype in types:
            price = round(float(rng.uniform(lo, hi)), 2)
            rows.append({
                "product_id": f"P{pid:04d}",
                "product_name": f"{rng.choice(BRANDS)} {ptype}",
                "category": category,
                "unit_price": price,
                "unit_cost": round(price * float(rng.uniform(0.55, 0.70)), 2),
            })
            pid += 1
    return pd.DataFrame(rows)


def _gen_orders(n: int, customers: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp("2024-07-01")
    end = pd.Timestamp("2025-12-31")
    days = (end - start).days
    probs = 1 + np.arange(days + 1) / (days + 1)
    probs /= probs.sum()
    day_offsets = rng.choice(days + 1, size=n, p=probs)
    cust_weights = rng.exponential(1.0, len(customers))
    cust_weights /= cust_weights.sum()
    cust_idx = rng.choice(len(customers), size=n, p=cust_weights)
    return pd.DataFrame({
        "order_id": [f"O{i:06d}" for i in range(1, n + 1)],
        "customer_id": customers.iloc[cust_idx]["customer_id"].to_numpy(),
        "order_date": [(start + pd.Timedelta(days=int(d))).date()
                       for d in day_offsets],
        "status": rng.choice(STATUSES, size=n, p=STATUS_PROBS),
        "payment_method": rng.choice(PAYMENT_METHODS, size=n, p=PAYMENT_PROBS),
    })


def _gen_order_items(orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    n_items = rng.choice([1, 2, 3, 4], size=len(orders),
                         p=[0.55, 0.25, 0.13, 0.07])
    order_ids = np.repeat(orders["order_id"].to_numpy(), n_items)
    product_ids = rng.choice(products["product_id"].to_numpy(), size=len(order_ids))
    price_map = dict(zip(products["product_id"], products["unit_price"]))
    quantities = rng.choice([1, 2, 3], size=len(order_ids), p=[0.75, 0.18, 0.07])
    discounts = rng.choice([0.0, 0.10, 0.15, 0.20], size=len(order_ids),
                           p=[0.70, 0.15, 0.10, 0.05])
    unit_prices = np.array([
        round(price_map[pid] * (1 + rng.normal(0, 0.02)), 2)
        for pid in product_ids
    ])
    return pd.DataFrame({
        "order_id": order_ids,
        "product_id": product_ids,
        "quantity": quantities,
        "unit_price": unit_prices,
        "discount": discounts,
    })


def generate(raw_dir: Path | str = BASE_DIR / "data" / "raw",
             n_customers: int = 5000, n_orders: int = 60000) -> dict:
    """Generate all raw tables and write them as CSV. Returns row counts."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    customers = _gen_customers(n_customers)
    products = _gen_products()
    orders = _gen_orders(n_orders, customers)
    order_items = _gen_order_items(orders, products)

    customers.to_csv(raw_dir / "customers.csv", index=False)
    products.to_csv(raw_dir / "products.csv", index=False)
    orders.to_csv(raw_dir / "orders.csv", index=False)
    order_items.to_csv(raw_dir / "order_items.csv", index=False)

    return {t: len(df) for t, df in
            [("customers", customers), ("products", products),
             ("orders", orders), ("order_items", order_items)]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=5000)
    parser.add_argument("--orders", type=int, default=60000)
    parser.add_argument("--out", type=str, default=str(BASE_DIR / "data" / "raw"))
    args = parser.parse_args()
    counts = generate(args.out, args.customers, args.orders)
    print("generated:", counts)
