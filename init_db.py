import sqlite3, os, sys

DB = "db/shop.db"
os.makedirs("db", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("invoices", exist_ok=True)

if os.path.exists(DB):
    print("Database already exists.")
    sys.exit(0)

conn = sqlite3.connect(DB)
c = conn.cursor()

c.executescript("""
CREATE TABLE users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email    TEXT,
    role     TEXT DEFAULT 'user',
    balance  REAL DEFAULT 0
);
CREATE TABLE products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    description TEXT,
    price       REAL,
    image       TEXT
);
CREATE TABLE orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    card_number TEXT,
    expiry      TEXT,
    cvv         TEXT,
    total       REAL,
    status      TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    user_id    INTEGER,
    content    TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT,
    token      TEXT,
    created_at INTEGER
);
""")

c.executemany("INSERT INTO users (username,password,email,role,balance) VALUES (?,?,?,?,?)", [
    ("admin",  "admin123",  "admin@faultshop.com", "admin", 0),
    ("carlos", "password1", "carlos@email.com",    "user",  200.00),
    ("ana",    "ana2024",   "ana@email.com",        "user",  150.00),
    ("pedro",  "123456",    "pedro@email.com",      "user",  50.00),
    ("maria",  "maria1234", "maria@email.com",      "user",  75.00),
])

c.executemany("INSERT INTO products (name,description,price,image) VALUES (?,?,?,?)", [
    ("ProX 15 Laptop",      "High-performance laptop, 16GB RAM, 512GB SSD",          1299.99, "laptop.jpg"),
    ("Wireless Mouse",      "Ergonomic mouse with rechargeable battery",                29.99, "mouse.jpg"),
    ("Mechanical Keyboard", "Backlit keyboard, blue switches",                          89.99, "keyboard.jpg"),
    ('27" Monitor',         "4K IPS panel, 144Hz, HDR",                               399.99, "monitor.jpg"),
    ("RGB Headset",         "7.1 surround sound, retractable microphone",               59.99, "headset.jpg"),
    ("1080p Webcam",        "Autofocus, noise reduction, OBS compatible",               49.99, "webcam.jpg"),
    ("1TB External SSD",    "USB-C, 1000MB/s read speed, Mac and PC compatible",       119.99, "ssd.jpg"),
    ("7-in-1 USB-C Hub",   "4K HDMI, USB 3.0, SD card reader, power delivery",         45.99, "hub.jpg"),
])

c.executemany("INSERT INTO orders (user_id,card_number,expiry,cvv,total,status) VALUES (?,?,?,?,?,?)", [
    (1, "4111111111111111", "12/26", "123", 1299.99, "Paid"),
    (2, "5500005555555559", "08/25", "456",   29.99, "Paid"),
    (3, "4111111111111111", "03/27", "789",  489.98, "Shipped"),
    (4, "3714496353984312", "11/25", "321",   59.99, "Paid"),
    (5, "4532015112830366", "06/26", "654",  119.99, "Shipped"),
])

conn.commit()
conn.close()
print("Database initialized successfully.")
