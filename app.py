from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY, dish TEXT)''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/select_dish', methods=['POST'])
def select_dish():
    dish = request.form['dish']
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (dish) VALUES (?)", (dish,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/maid')
def maid():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute("SELECT dish FROM orders ORDER BY id DESC LIMIT 1")
    order = c.fetchone()
    conn.close()
    return render_template('maid.html', dish=order[0] if order else 'No order yet')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
