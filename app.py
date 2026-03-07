from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path
from openai import OpenAI
import os

app = Flask(__name__)
DB_PATH = Path(os.getenv("DB_PATH", "orders.db"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 常见菜中英对照，优先用本地字典，快且稳定
TRANSLATIONS = {
    "白饭": "Rice",
    "米饭": "Rice",
    "鸡肉": "Chicken",
    "鱼": "Fish",
    "青菜": "Vegetables",
    "汤": "Soup",
    "面": "Noodles",
    "粥": "Porridge",
    "番茄炒蛋": "Tomato Egg Stir-fry",
    "蒸鱼": "Steamed Fish",
    "排骨汤": "Pork Rib Soup",
    "炒饭": "Fried Rice",
    "炒面": "Fried Noodles",
    "牛肉": "Beef",
    "猪肉": "Pork",
    "鸡蛋": "Egg",
    "豆腐": "Tofu",
    "白菜": "Chinese Cabbage",
    "西兰花": "Broccoli",
    "土豆": "Potato",
    "虾": "Shrimp",
    "鸡汤": "Chicken Soup",
    "牛肉汤": "Beef Soup",
    "青菜汤": "Vegetable Soup",
    "蒸蛋": "Steamed Egg",
    "红烧肉": "Braised Pork",
    "清蒸鸡": "Steamed Chicken",
}

PRESET_DISHES_ZH = [
    "白饭",
    "鸡肉",
    "鱼",
    "青菜",
    "汤",
    "面",
    "粥",
    "番茄炒蛋",
    "蒸鱼",
    "排骨汤",
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_zh TEXT NOT NULL UNIQUE,
            name_en TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS current_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_name_zh TEXT NOT NULL,
            dish_name_en TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for dish_zh in PRESET_DISHES_ZH:
        dish_en = translate_to_english(dish_zh)
        cur.execute(
            "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
            (dish_zh, dish_en),
        )

    conn.commit()
    conn.close()


def translate_to_english(name_zh: str) -> str:
    name_zh = name_zh.strip()

    if not name_zh:
        return ""

    if name_zh in TRANSLATIONS:
        return TRANSLATIONS[name_zh]

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=(
                "Translate this Chinese dish name into natural restaurant English. "
                "Return only the English dish name, with no explanation: "
                f"{name_zh}"
            ),
        )
        name_en = response.output_text.strip()

        if not name_en:
            return f"[Translate] {name_zh}"

        return name_en
    except Exception:
        return f"[Translate] {name_zh}"


def get_all_dishes():
    conn = get_conn()
    rows = conn.execute(
        "SELECT name_zh, name_en FROM dishes ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


def get_current_order():
    conn = get_conn()
    rows = conn.execute("""
        SELECT dish_name_zh, dish_name_en
        FROM current_order
        ORDER BY id ASC
    """).fetchall()
    conn.close()
    return rows


@app.route("/", methods=["GET"])
def index():
    dishes = get_all_dishes()
    current_order = get_current_order()
    return render_template("index.html", dishes=dishes, current_order=current_order)


@app.route("/order", methods=["POST"])
def order():
    selected_dishes_zh = request.form.getlist("dishes")
    custom_dish_zh = request.form.get("custom_dish", "").strip()

    conn = get_conn()
    cur = conn.cursor()

    # 清空当前订单，重新生成这一次
    cur.execute("DELETE FROM current_order")

    final_dishes_zh = []

    for dish_zh in selected_dishes_zh:
        dish_zh = dish_zh.strip()
        if dish_zh:
            final_dishes_zh.append(dish_zh)

    if custom_dish_zh:
        final_dishes_zh.append(custom_dish_zh)
        custom_dish_en = translate_to_english(custom_dish_zh)
        cur.execute(
            "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
            (custom_dish_zh, custom_dish_en),
        )

    for dish_zh in final_dishes_zh:
        # 优先查 dishes 表，避免重复调用 API
        row = cur.execute(
            "SELECT name_en FROM dishes WHERE name_zh = ?",
            (dish_zh,),
        ).fetchone()

        if row:
            dish_en = row["name_en"]
        else:
            dish_en = translate_to_english(dish_zh)
            cur.execute(
                "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
                (dish_zh, dish_en),
            )

        cur.execute(
            "INSERT INTO current_order (dish_name_zh, dish_name_en) VALUES (?, ?)",
            (dish_zh, dish_en),
        )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset():
    conn = get_conn()
    conn.execute("DELETE FROM current_order")
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/dashboard", methods=["GET"])
def dashboard():
    current_order = get_current_order()
    return render_template("dashboard.html", current_order=current_order)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)