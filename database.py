import random
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
SAMPLE_DB = BASE_DIR / "shop.db"
CUSTOM_DB = BASE_DIR / "custom.db"  # rebuilt from uploaded files

MAX_ROWS = 500       # most rows we load into a DataFrame
QUERY_TIMEOUT = 10   # seconds

SAMPLE_SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    city TEXT,
    created_at TIMESTAMP
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    price REAL,
    category TEXT,
    stock INTEGER
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    order_date TIMESTAMP,
    status TEXT
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER
);
"""

CITIES = ["Metropolis", "Gotham", "Star City"]
FIRST_NAMES = ["Arun", "Priya", "Karthik", "Divya", "Sanjay", "Meena", "Rahul", "Anitha",
               "Vikram", "Lakshmi", "Suresh", "Kavya", "Naveen", "Deepa", "Ganesh"]
LAST_NAMES = ["Kumar", "Raj", "Selvam", "Nair", "Iyer", "Pillai", "Reddy", "Sharma"]
PRODUCTS = [
    ("Wireless Mouse", 799, "Electronics"), ("Mechanical Keyboard", 3499, "Electronics"),
    ("USB-C Hub", 1899, "Electronics"), ("Bluetooth Speaker", 2499, "Electronics"),
    ("Running Shoes", 2999, "Apparel"), ("Hoodie", 1499, "Apparel"),
    ("T-Shirt", 599, "Apparel"), ("Denim Jacket", 2199, "Apparel"),
    ("Desk Lamp", 999, "Home Decor"), ("Wall Clock", 1299, "Home Decor"),
    ("Cushion Set", 899, "Home Decor"), ("Table Plant Pot", 449, "Home Decor"),
    ("Yoga Mat", 1099, "Fitness"), ("Dumbbell Pair", 1999, "Fitness"),
    ("Resistance Bands", 599, "Fitness"), ("Skipping Rope", 299, "Fitness"),
]
# most orders are delivered, a few are still shipped or cancelled
STATUSES = ["delivered"] * 7 + ["shipped"] * 2 + ["cancelled"]


class QueryError(Exception):
    """A query could not be run (bad SQL, not allowed, or too slow)."""


def create_sample_db(db_path=SAMPLE_DB):
    """Create the sample shop database with random data, if it doesn't exist yet."""
    if Path(db_path).exists():
        return

    random.seed(42)
    now = datetime.now().replace(microsecond=0)

    customers = []
    for customer_id in range(1, 61):
        created_at = now - timedelta(days=random.randint(200, 700))
        customers.append((
            customer_id,
            random.choice(FIRST_NAMES),
            random.choice(LAST_NAMES),
            f"user{1000 + customer_id}@example.mock",
            random.choice(CITIES),
            created_at.isoformat(sep=" "),
        ))

    products = []
    for product_id, (name, price, category) in enumerate(PRODUCTS, start=1):
        products.append((product_id, name, price, category, random.randint(0, 200)))

    orders = []
    order_items = []
    for order_id in range(1, 401):
        order_date = now - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))
        orders.append((order_id, random.randint(1, 60), order_date.isoformat(sep=" "),
                       random.choice(STATUSES)))
        for product_id in random.sample(range(1, len(PRODUCTS) + 1), random.randint(1, 4)):
            order_items.append((len(order_items) + 1, order_id, product_id, random.randint(1, 3)))

    conn = sqlite3.connect(db_path)
    conn.executescript(SAMPLE_SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers)
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", products)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)", order_items)
    conn.commit()
    conn.close()


def connect_read_only(db_path):
    """Open the database in read-only mode."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def allow_read_only(action, arg1, arg2, db_name, source):
    """SQLite authorizer: allow reading normal tables and nothing else.

    SQLite calls this while it prepares a statement. Anything that isn't a
    SELECT/read/function call (PRAGMA, writes, ATTACH, ...) is rejected.
    """
    if action == sqlite3.SQLITE_READ:
        table = (arg1 or "").lower()
        if table.startswith("sqlite_") or table.startswith("pragma_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, 33):  # 33 = recursive CTE
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def list_tables(db_path):
    conn = connect_read_only(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_schema(db_path):
    """Return the CREATE TABLE statements. This text is what the model sees."""
    conn = connect_read_only(db_path)
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    conn.close()
    return "\n\n".join(row[0] + ";" for row in rows)


def run_query(db_path, sql):
    """Run a query and return the result as a DataFrame (at most MAX_ROWS rows)."""
    conn = connect_read_only(db_path)
    conn.set_authorizer(allow_read_only)

    # stop queries that run too long (for example an accidental huge join)
    start = time.time()
    conn.set_progress_handler(lambda: time.time() - start > QUERY_TIMEOUT, 10000)

    try:
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS)
    except sqlite3.Error as e:
        message = str(e)
        if "interrupted" in message:
            message = f"The query ran for more than {QUERY_TIMEOUT} seconds and was stopped."
        elif "not authorized" in message:
            message = "The query uses something that is not allowed."
        raise QueryError(message) from e
    finally:
        conn.close()

    return pd.DataFrame(rows, columns=columns)
