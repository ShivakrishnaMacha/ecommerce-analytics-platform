"""Streamlit BI dashboard for the e-commerce analytics platform."""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
WAREHOUSE = BASE_DIR / "data" / "warehouse" / "ecommerce.duckdb"

st.set_page_config(page_title="E-commerce Analytics", layout="wide",
                   page_icon="🛒")


@st.cache_resource(show_spinner="Building warehouse (first run only)...")
def load_data():
    if not WAREHOUSE.exists():
        sys.path.insert(0, str(BASE_DIR))
        from pipeline.run_pipeline import run
        run(scale="full")
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    orders = con.execute("""
        SELECT fo.*, d.full_date::DATE AS order_date, d.year_month,
               c.signup_date::DATE AS signup_date, c.state
        FROM fact_orders fo
        JOIN dim_dates d ON d.date_key = fo.date_key
        JOIN dim_customers c ON c.customer_key = fo.customer_key
    """).df()
    items = con.execute("""
        SELECT foi.order_id, foi.quantity, foi.line_revenue,
               p.product_name, p.category
        FROM fact_order_items foi
        JOIN dim_products p ON p.product_key = foi.product_key
    """).df()
    con.close()
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["signup_date"] = pd.to_datetime(orders["signup_date"])
    return orders, items


orders, items = load_data()

st.title("🛒 E-commerce Analytics Platform")
st.caption("End-to-end data engineering: synthetic orders → validated pipeline → "
           "DuckDB star schema → this dashboard")

# ---- filters ----
st.sidebar.header("Filters")
min_d, max_d = orders["order_date"].min().date(), orders["order_date"].max().date()
date_range = st.sidebar.slider("Order date", min_d, max_d, (min_d, max_d))
categories = st.sidebar.multiselect("Category", sorted(items["category"].unique()),
                                    default=sorted(items["category"].unique()))
statuses = st.sidebar.multiselect("Status", ["Delivered", "Returned"],
                                  default=["Delivered", "Returned"])

mask = (
    orders["order_date"].dt.date.between(*date_range)
    & orders["status"].isin(statuses)
)
f_orders = orders.loc[mask]
f_items = items.loc[items["order_id"].isin(f_orders.loc[
    f_orders["status"] != "Cancelled", "order_id"]) & items["category"].isin(categories)]

# ---- KPIs ----
revenue = f_orders["revenue"].sum()
n_orders = f_orders["order_id"].nunique()
aov = revenue / n_orders if n_orders else 0
margin = f_orders["profit"].sum() / revenue if revenue else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Revenue", f"${revenue:,.0f}")
c2.metric("Orders", f"{n_orders:,}")
c3.metric("Avg order value", f"${aov:,.2f}")
c4.metric("Profit margin", f"{margin:.1%}")

# ---- trend + category ----
t1, t2 = st.columns(2)
with t1:
    monthly = (f_orders.groupby("year_month")
               .agg(revenue=("revenue", "sum")).reset_index())
    st.plotly_chart(px.line(monthly, x="year_month", y="revenue",
                            title="Monthly revenue trend",
                            markers=True), use_container_width=True)
with t2:
    cat = (f_items.groupby("category")
           .agg(revenue=("line_revenue", "sum")).reset_index()
           .sort_values("revenue", ascending=False))
    st.plotly_chart(px.bar(cat, x="category", y="revenue",
                           title="Revenue by category"), use_container_width=True)

# ---- top products + payment mix ----
p1, p2 = st.columns(2)
with p1:
    top = (f_items.groupby("product_name")
           .agg(revenue=("line_revenue", "sum")).reset_index()
           .sort_values("revenue", ascending=False).head(10))
    st.plotly_chart(px.bar(top, x="revenue", y="product_name",
                           orientation="h", title="Top 10 products"),
                    use_container_width=True)
with p2:
    pay = (f_orders.groupby("payment_method")
           .agg(revenue=("revenue", "sum")).reset_index())
    st.plotly_chart(px.pie(pay, names="payment_method", values="revenue",
                           title="Revenue by payment method", hole=0.4),
                    use_container_width=True)

# ---- cohort retention ----
st.subheader("Cohort retention (repeat purchase rate)")
coh = f_orders[["customer_key", "signup_date", "order_date"]].copy()
coh["cohort"] = coh["signup_date"].dt.to_period("M")
coh["order_period"] = coh["order_date"].dt.to_period("M")
coh["periods_since"] = ((coh["order_period"].dt.year - coh["cohort"].dt.year) * 12
                        + (coh["order_period"].dt.month - coh["cohort"].dt.month))
pivot = (coh.groupby(["cohort", "periods_since"])["customer_key"]
         .nunique().unstack(fill_value=0))
cohort_size = pivot[0].replace(0, pd.NA)
retention = (pivot.divide(cohort_size, axis=0).iloc[-12:] * 100).round(1)
retention.index = retention.index.astype(str)
st.plotly_chart(px.imshow(retention, text_auto=".0f", aspect="auto",
                          color_continuous_scale="Blues",
                          labels=dict(x="Months since signup",
                                      y="Signup cohort",
                                      color="Retention %"),
                          title="Retention by signup cohort"),
                use_container_width=True)

st.divider()
st.caption("Built with Python · DuckDB · Streamlit · Plotly — "
           "see README for the pipeline architecture.")
