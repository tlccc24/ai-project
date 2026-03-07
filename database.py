import sqlite3

def init_db():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY, dish TEXT)''')
    conn.commit()
    conn.close()

def save_order(dish):
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (dish) VALUES (?)", (dish,))
    conn.commit()
    conn.close()

def get_latest_order():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute("SELECT dish FROM orders ORDER BY id DESC LIMIT 1")
    order = c.fetchone()
    conn.close()
    return order[0] if order else 'No order yet'
