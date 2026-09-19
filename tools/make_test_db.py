#!/usr/bin/env python3
"""
Generate test.db, the sample database shipped with OJDB Viewer.

The data is a small fictional shop. It is deliberately awkward in places so
every viewer feature has something to show: a table named after an SQL
keyword, a column name with a space, foreign keys, views, indexes, NULLs,
JSON, long text and image BLOBs. Output is deterministic.

Usage: python tools/make_test_db.py [output_path]
"""

import json
import os
import random
import sqlite3
import struct
import sys
import zlib

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email VARCHAR(120) NOT NULL,
    country TEXT,
    preferences TEXT,          -- JSON
    notes TEXT
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    description TEXT,
    image BLOB                 -- small PNG swatch
);

-- "order" is an SQL keyword and "shipping address" contains a space
CREATE TABLE "order" (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    placed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    "shipping address" TEXT
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES "order",
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);

CREATE UNIQUE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_order_customer ON "order"(customer_id);
CREATE INDEX idx_order_status_date ON "order"(status, placed_at);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_products_name_lower ON products(lower(name));

CREATE VIEW order_totals AS
    SELECT o.id AS order_id, c.name AS customer, o.placed_at, o.status,
           COUNT(i.id) AS lines, ROUND(SUM(i.quantity * i.unit_price), 2) AS total
    FROM "order" o
    JOIN customers c ON c.id = o.customer_id
    LEFT JOIN order_items i ON i.order_id = o.id
    GROUP BY o.id;

CREATE VIEW customer_summary AS
    SELECT c.id AS customer_id, c.name, c.country, COUNT(DISTINCT o.id) AS orders,
           ROUND(COALESCE(SUM(i.quantity * i.unit_price), 0), 2) AS spent
    FROM customers c
    LEFT JOIN "order" o ON o.customer_id = c.id
    LEFT JOIN order_items i ON i.order_id = o.id
    GROUP BY c.id;
"""

FIRST_NAMES = ["Ada", "Bruno", "Chen", "Dalia", "Emeka", "Freya", "Goran", "Hana", "Ivo", "Jun",
               "Kiri", "Lars", "Mina", "Noor", "Otto", "Priya", "Quinn", "Rosa", "Sven", "Tala"]
LAST_NAMES = ["Abara", "Berg", "Costa", "Dunn", "Eze", "Fujita", "Garcia", "Haddad", "Ito",
              "Jensen", "Kaur", "Lindqvist", "Moreau", "Ngata", "O'Brien", "Petrov"]
COUNTRIES = ["Australia", "New Zealand", "Japan", "Germany", "Brazil", "Nigeria", "Canada", None]
STREETS = ["Wattle St", "Harbour Rd", "Kauri Ave", "Station Ln", "Mill Rd", "Ocean Pde"]
CATEGORIES = {
    "Tools": ["Claw Hammer", "Spirit Level", "Hex Key Set", "Tape Measure", "Wood Chisel"],
    "Garden": ["Hand Trowel", "Pruning Shears", "Watering Can", "Seed Tray", "Garden Twine"],
    "Kitchen": ["Cast Iron Pan", "Bread Knife", "Mixing Bowl", "Dough Scraper", "Pepper Mill"],
    "Stationery": ["Dot Grid Notebook", "Fountain Pen", "Brass Ruler", "Ink Bottle", "Desk Tray"],
    "Outdoors": ["Enamel Mug", "Head Torch", "Dry Bag", "Tent Pegs", "Camp Stool"],
}
STATUSES = ["pending", "paid", "shipped", "delivered", "delivered", "delivered", "refunded"]
NOTES = [None, None, None, "Prefers email contact.", "Wholesale account.",
         "Asked about gift wrapping.", "Delivery gate code on file.", ""]


def png_swatch(red, green, blue, size=16):
    """A valid solid-colour PNG, built by hand so there are no dependencies"""
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes([red, green, blue]) * size
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size, 9))
            + chunk(b"IEND", b""))


def build(path):
    rng = random.Random(42)
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)

    customers = []
    for customer_id in range(1, 61):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{first}.{last}{customer_id}@example.com".lower().replace("'", "")
        preferences = None
        if rng.random() < 0.7:
            preferences = json.dumps({
                "newsletter": rng.random() < 0.5,
                "currency": rng.choice(["AUD", "NZD", "JPY", "EUR"]),
                "favourites": rng.sample(list(CATEGORIES), rng.randint(0, 3)),
            })
        customers.append((customer_id, f"{first} {last}", email, rng.choice(COUNTRIES),
                          preferences, rng.choice(NOTES)))
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers)

    products = []
    for category, names in CATEGORIES.items():
        for name in names:
            product_id = len(products) + 1
            description = (f"{name} from our {category.lower()} range. "
                           + " ".join(rng.choice([
                               "Made to be repaired rather than replaced.",
                               "Finished by hand in small batches.",
                               "Comes with a five year guarantee.",
                               "Packed without plastic.",
                               "A customer favourite since we opened.",
                           ]) for _ in range(rng.randint(2, 6))))
            # A few products have no photo yet
            image = None if product_id % 7 == 0 else png_swatch(
                rng.randrange(256), rng.randrange(256), rng.randrange(256))
            products.append((product_id, f"{category[:3].upper()}-{product_id:03d}", name, category,
                             round(rng.uniform(4, 180), 2), description, image))
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", products)

    orders, items = [], []
    for order_id in range(1, 401):
        customer = rng.choice(customers)
        placed_at = (f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} "
                     f"{rng.randint(7, 21):02d}:{rng.randint(0, 59):02d}")
        # Pickup orders have no address
        address = None if rng.random() < 0.15 else (
            f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {customer[3] or 'Unknown'}")
        orders.append((order_id, customer[0], placed_at, rng.choice(STATUSES), address))
        for product in rng.sample(products, rng.randint(1, 5)):
            items.append((len(items) + 1, order_id, product[0], rng.randint(1, 4), product[4]))
    conn.executemany('INSERT INTO "order" VALUES (?, ?, ?, ?, ?)', orders)
    conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", items)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    return len(customers), len(products), len(orders), len(items)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "test.db")
    counts = build(output)
    print("Wrote %s: %d customers, %d products, %d orders, %d order items" % ((output,) + counts))
