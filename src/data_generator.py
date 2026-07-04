import pandas as pd
import numpy as np
from faker import Faker
import os
import random
from datetime import datetime

fake = Faker('en_IN')
np.random.seed(42)
random.seed(42)

OUTPUT_DIR = 'data/monthly_drops'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Fixed reference data (consistent across all 36 files) ---

REGIONS = ['North', 'South', 'East', 'West']
REGION_WEIGHTS = [0.35, 0.30, 0.20, 0.15]

REGION_SALESPERSON_MAP = {
    'North': [f'SP-{str(i).zfill(3)}' for i in range(1, 19)],
    'South': [f'SP-{str(i).zfill(3)}' for i in range(19, 34)],
    'East':  [f'SP-{str(i).zfill(3)}' for i in range(34, 45)],
    'West':  [f'SP-{str(i).zfill(3)}' for i in range(45, 51)],
}

# Same name for same SP-ID across all 36 files
SALESPERSON_NAMES = {
    f'SP-{str(i).zfill(3)}': fake.name() for i in range(1, 51)
}

REGION_BASE_TARGETS = {
    'North': 500000,
    'South': 450000,
    'East':  350000,
    'West':  280000
}

# (product_name, base_price_INR, cost_ratio)
PRODUCTS = {
    'Electronics': [
        ('Laptop Pro X1', 65000, 0.62),
        ('Wireless Earbuds', 3500, 0.58),
        ('Smart TV 43 inch', 32000, 0.65),
        ('Smartphone Y7', 18000, 0.60),
        ('Bluetooth Speaker', 2800, 0.55),
        ('Tablet Air', 25000, 0.63),
        ('Smart Watch', 8500, 0.58),
        ('Gaming Console', 45000, 0.68),
    ],
    'Clothing': [
        ('Formal Shirt', 1200, 0.45),
        ('Denim Jeans', 2200, 0.42),
        ('Ethnic Kurta', 1800, 0.40),
        ('Sports T-Shirt', 800, 0.38),
        ('Winter Jacket', 4500, 0.48),
        ('Saree Silk', 3500, 0.43),
        ('Casual Sneakers', 2800, 0.46),
        ('Formal Trousers', 1600, 0.44),
    ],
    'Home Goods': [
        ('Pressure Cooker 5L', 2200, 0.55),
        ('Bed Sheet Set', 1800, 0.50),
        ('Dinner Set 24pc', 3200, 0.52),
        ('Air Purifier', 12000, 0.60),
        ('Mixer Grinder', 4500, 0.58),
        ('Sofa 3-Seater', 28000, 0.62),
        ('Curtain Pair', 1200, 0.48),
        ('Wall Clock', 850, 0.45),
    ],
    'Sports': [
        ('Cricket Bat', 3500, 0.55),
        ('Yoga Mat', 1200, 0.48),
        ('Badminton Set', 2200, 0.50),
        ('Running Shoes', 3800, 0.52),
        ('Fitness Band', 2500, 0.55),
        ('Cycling Helmet', 1800, 0.50),
        ('Swimming Goggles', 950, 0.45),
        ('Gym Dumbbells 5kg', 1500, 0.52),
    ],
    'Beauty': [
        ('Face Serum 30ml', 1200, 0.40),
        ('Hair Dryer Pro', 2800, 0.55),
        ('Perfume Set', 2200, 0.42),
        ('Sunscreen SPF50', 650, 0.38),
        ('Lipstick Collection', 1800, 0.40),
        ('Electric Shaver', 3500, 0.58),
        ('Moisturizer 100ml', 950, 0.42),
        ('Makeup Brush Set', 1500, 0.40),
    ],
    'Automotive': [
        ('Car Seat Cover Set', 4500, 0.58),
        ('Dashboard Camera', 8500, 0.62),
        ('Tyre Inflator', 3200, 0.55),
        ('Car Vacuum Cleaner', 2800, 0.52),
        ('Steering Wheel Cover', 1200, 0.48),
        ('Car Perfume Set', 650, 0.40),
        ('Jump Starter Pack', 6500, 0.60),
        ('Parking Sensor Kit', 5500, 0.58),
    ],
}

CATEGORY_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.07, 0.03]


def get_business_days(year, month):
    """Returns all weekday dates in a given month."""
    import calendar
    days = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        d = datetime(year, month, day)
        if d.weekday() < 5:  # 0=Monday, 4=Friday
            days.append(d.date())
    return days


def generate_monthly_data(year, month, base_rows):
    """Generates one month of synthetic sales transactions."""
    categories = list(PRODUCTS.keys())
    business_days = get_business_days(year, month)
    
    # Q4 (Oct-Dec) = festival season = more discounts
    is_festival = month in [10, 11, 12]
    
    # Targets grow 10% each year from 2022 baseline
    year_multiplier = 1.0 + (year - 2022) * 0.10

    rows = []
    for i in range(base_rows):
        region = np.random.choice(REGIONS, p=REGION_WEIGHTS)
        sp_id = random.choice(REGION_SALESPERSON_MAP[region])
        sp_name = SALESPERSON_NAMES[sp_id]

        category = np.random.choice(categories, p=CATEGORY_WEIGHTS)
        product_name, base_price, cost_ratio = random.choice(PRODUCTS[category])

        # Small price variation month to month (±5%)
        unit_price = round(base_price * np.random.uniform(0.95, 1.05), 2)

        segment = np.random.choice(['B2B', 'B2C'], p=[0.35, 0.65])
        units = random.randint(5, 50) if segment == 'B2B' else random.randint(1, 5)

        # Festival season = more aggressive discounting
        discount_weights = (
            [0.10, 0.15, 0.30, 0.25, 0.20] if is_festival
            else [0.40, 0.25, 0.20, 0.10, 0.05]
        )
        discount_pct = np.random.choice([0, 5, 10, 15, 20], p=discount_weights)

        gross_rev = round(units * unit_price, 2)
        discount_amt = round(gross_rev * discount_pct / 100, 2)
        net_rev = round(gross_rev - discount_amt, 2)
        cost_per_unit = round(unit_price * cost_ratio, 2)
        total_cost = round(cost_per_unit * units, 2)
        gross_profit = round(net_rev - total_cost, 2)
        margin_pct = round((gross_profit / net_rev * 100) if net_rev > 0 else 0, 2)

        base_target = (
            REGION_BASE_TARGETS[region] /
            len(REGION_SALESPERSON_MAP[region])
        )
        monthly_target = round(base_target * year_multiplier, 2)

        # 3% of transactions are returns
        return_flag = random.random() < 0.03
        if return_flag:
            net_rev = -abs(net_rev)
            gross_profit = -abs(gross_profit)
            margin_pct = -abs(margin_pct)

        # B2B prefers Bank Transfer, B2C prefers UPI/Credit Card
        if segment == 'B2B':
            payment = np.random.choice(
                ['UPI', 'Credit Card', 'Cash', 'Bank Transfer'],
                p=[0.10, 0.20, 0.05, 0.65]
            )
        else:
            payment = np.random.choice(
                ['UPI', 'Credit Card', 'Cash', 'Bank Transfer'],
                p=[0.45, 0.35, 0.15, 0.05]
            )

        txn_date = random.choice(business_days)

        rows.append({
            'transaction_id': f'TXN-{year}-{str(month).zfill(2)}-{str(i+1).zfill(6)}',
            'date': txn_date.strftime('%d-%m-%Y'),  # INTENTIONAL: DD-MM-YYYY not ISO
            'month': month,
            'year': year,
            'region': region,
            'salesperson_id': sp_id,
            'salesperson_name': sp_name,
            'product_category': category,
            'product_name': product_name,
            'customer_segment': segment,
            'customer_id': f'CUST-{random.randint(100000, 999999)}',
            'units_sold': units,
            'unit_price': unit_price,
            'discount_pct': discount_pct,
            'gross_revenue': gross_rev,
            'discount_amount': discount_amt,
            'net_revenue': net_rev,
            'cost_per_unit': cost_per_unit,
            'total_cost': total_cost,
            'gross_profit': gross_profit,
            'profit_margin_pct': margin_pct,
            'monthly_target': monthly_target,
            'return_flag': return_flag,
            'payment_method': payment,
        })

    df = pd.DataFrame(rows)

    # --- INJECT INTENTIONAL DATA QUALITY ISSUES ---
    # These make the PySpark cleaning step demonstrate real value

    # Issue 1: 5% null product names
    null_idx = df.sample(frac=0.05, random_state=year*month).index
    df.loc[null_idx, 'product_name'] = None

    # Issue 2: 2% prices stored as strings with currency symbol
    df["unit_price"] = df["unit_price"].astype("object")

    str_idx = df.sample(frac=0.02, random_state=year + month).index

    df.loc[str_idx, "unit_price"] = (
    df.loc[str_idx, "unit_price"]
      .apply(lambda x: f"Rs.{x}")
    )

    # Issue 3: 3% inconsistent region casing (north, SOUTH, etc.)
    case_idx = df.sample(frac=0.03, random_state=year-month).index
    df.loc[case_idx, 'region'] = df.loc[case_idx, 'region'].apply(
        lambda x: x.lower() if random.random() > 0.5 else x.upper()
    )

    # Issue 4: 1% negative units_sold (data entry error)
    neg_idx = df.sample(frac=0.01, random_state=year*2).index
    df.loc[neg_idx, 'units_sold'] = df.loc[neg_idx, 'units_sold'].apply(
        lambda x: -abs(x)
    )

    # Issue 5: 1% exact duplicate rows
    dup_count = max(1, int(len(df) * 0.01))
    df = pd.concat([df, df.sample(n=dup_count, random_state=42)],
                   ignore_index=True)

    return df


def generate_all_months():
    """Generates all 36 monthly files (Jan 2022 to Dec 2024)."""
    # Growing volume: business grows each year
    rows_config = {2022: 1400, 2023: 1600, 2024: 1800}
    total = 0

    for year in [2022, 2023, 2024]:
        for month in range(1, 13):
            df = generate_monthly_data(year, month, rows_config[year])
            filename = f'{year}_{str(month).zfill(2)}_sales.csv'
            filepath = os.path.join(OUTPUT_DIR, filename)
            df.to_csv(filepath, index=False)
            total += len(df)
            print(f'Generated: {filename} — {len(df):,} rows')

    print(f'\nAll 36 files generated. Total rows: {total:,}')
    print(f'Location: {OUTPUT_DIR}/')


if __name__ == '__main__':
    generate_all_months()