from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path
from openai import OpenAI
import os
from datetime import date, datetime, timedelta

app = Flask(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "orders.db"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

MEAL_TYPES = ["早餐", "午餐", "晚餐"]
MEAL_TYPE_EN = {
    "早餐": "Breakfast",
    "午餐": "Lunch",
    "晚餐": "Dinner",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column_exists(conn, table_name, column_name, column_sql):
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    col_names = [col["name"] for col in cols]
    if column_name not in col_names:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
        conn.commit()


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
        return name_en if name_en else f"[Translate] {name_zh}"
    except Exception:
        return f"[Translate] {name_zh}"


def split_custom_dishes(raw_text: str) -> list[str]:
    if not raw_text:
        return []

    normalized = raw_text
    separators = ["/", "，", "、", "\n"]
    for sep in separators:
        normalized = normalized.replace(sep, ",")

    parts = [part.strip() for part in normalized.split(",")]

    seen = set()
    result = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            result.append(part)

    return result


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
        CREATE TABLE IF NOT EXISTS planned_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_date TEXT NOT NULL,
            meal_type_zh TEXT NOT NULL,
            meal_type_en TEXT NOT NULL,
            dish_name_zh TEXT NOT NULL,
            dish_name_en TEXT NOT NULL,
            meal_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_column_exists(conn, "planned_orders", "meal_time", "TEXT")

    for dish_zh in PRESET_DISHES_ZH:
        dish_en = translate_to_english(dish_zh)
        cur.execute(
            "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
            (dish_zh, dish_en),
        )

    conn.commit()
    conn.close()


def cleanup_past_plans():
    today_str = date.today().isoformat()
    conn = get_conn()
    conn.execute("DELETE FROM planned_orders WHERE meal_date < ?", (today_str,))
    conn.commit()
    conn.close()


def upsert_dish(cur, dish_zh: str) -> str:
    row = cur.execute(
        "SELECT name_en FROM dishes WHERE name_zh = ?",
        (dish_zh,),
    ).fetchone()

    if row:
        return row["name_en"]

    dish_en = translate_to_english(dish_zh)
    cur.execute(
        "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
        (dish_zh, dish_en),
    )
    return dish_en


def get_all_dishes():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name_zh, name_en FROM dishes ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


def get_planned_orders_between(start_date: str, end_date: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, meal_date, meal_type_zh, meal_type_en, dish_name_zh, dish_name_en, meal_time
        FROM planned_orders
        WHERE meal_date >= ? AND meal_date <= ?
        ORDER BY meal_date ASC,
                 CASE meal_type_zh
                    WHEN '早餐' THEN 1
                    WHEN '午餐' THEN 2
                    WHEN '晚餐' THEN 3
                    ELSE 4
                 END,
                 id ASC
    """, (start_date, end_date)).fetchall()
    conn.close()
    return rows


def get_planned_orders_from(start_date: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, meal_date, meal_type_zh, meal_type_en, dish_name_zh, dish_name_en, meal_time
        FROM planned_orders
        WHERE meal_date >= ?
        ORDER BY meal_date ASC,
                 CASE meal_type_zh
                    WHEN '早餐' THEN 1
                    WHEN '午餐' THEN 2
                    WHEN '晚餐' THEN 3
                    ELSE 4
                 END,
                 id ASC
    """, (start_date,)).fetchall()
    conn.close()
    return rows


def build_day_meals_map(rows, target_date: str, lang="zh"):
    result = {}
    for meal_type_zh in MEAL_TYPES:
        key = meal_type_zh if lang == "zh" else MEAL_TYPE_EN[meal_type_zh]
        result[key] = {
            "dishes": [],
            "meal_time": ""
        }

    for row in rows:
        if row["meal_date"] != target_date:
            continue

        key = row["meal_type_zh"] if lang == "zh" else row["meal_type_en"]
        dish_name = row["dish_name_zh"] if lang == "zh" else row["dish_name_en"]

        result[key]["dishes"].append(dish_name)

        if row["meal_time"]:
            result[key]["meal_time"] = row["meal_time"]

    return result


def group_planned_orders(rows, lang="zh"):
    grouped = {}
    for row in rows:
        date_key = row["meal_date"]
        meal_key = row["meal_type_zh"] if lang == "zh" else row["meal_type_en"]
        dish_name = row["dish_name_zh"] if lang == "zh" else row["dish_name_en"]

        if date_key not in grouped:
            grouped[date_key] = {}

        if meal_key not in grouped[date_key]:
            grouped[date_key][meal_key] = {
                "dishes": [],
                "meal_time": ""
            }

        grouped[date_key][meal_key]["dishes"].append(dish_name)

        if row["meal_time"]:
            grouped[date_key][meal_key]["meal_time"] = row["meal_time"]

    return grouped


def save_meal(meal_date: str, meal_type_zh: str, selected_dishes_zh: list[str], custom_dish_raw: str, meal_time: str = ""):
    if meal_type_zh not in MEAL_TYPES:
        return

    try:
        chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
    except ValueError:
        return

    if chosen_date < date.today():
        return

    meal_type_en = MEAL_TYPE_EN[meal_type_zh]
    meal_time = meal_time.strip()

    conn = get_conn()
    cur = conn.cursor()

    final_dishes_zh = []

    for dish_zh in selected_dishes_zh:
        dish_zh = dish_zh.strip()
        if dish_zh and dish_zh not in final_dishes_zh:
            final_dishes_zh.append(dish_zh)

    custom_dishes = split_custom_dishes(custom_dish_raw)
    for custom_dish_zh in custom_dishes:
        if custom_dish_zh not in final_dishes_zh:
            final_dishes_zh.append(custom_dish_zh)

    cur.execute(
        "DELETE FROM planned_orders WHERE meal_date = ? AND meal_type_zh = ?",
        (meal_date, meal_type_zh),
    )

    for dish_zh in final_dishes_zh:
        dish_en = upsert_dish(cur, dish_zh)
        cur.execute("""
            INSERT INTO planned_orders
            (meal_date, meal_type_zh, meal_type_en, dish_name_zh, dish_name_en, meal_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (meal_date, meal_type_zh, meal_type_en, dish_zh, dish_en, meal_time or None))

    conn.commit()
    conn.close()


@app.route("/", methods=["GET"])
def index():
    cleanup_past_plans()

    dishes = get_all_dishes()
    search_query = request.args.get("search", "").strip()

    if search_query:
        filtered_dishes = [
            dish for dish in dishes
            if search_query in dish["name_zh"] or search_query.lower() in dish["name_en"].lower()
        ]
    else:
        filtered_dishes = dishes

    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    rows = get_planned_orders_between(today.isoformat(), day_after.isoformat())

    today_meals = build_day_meals_map(rows, today.isoformat(), lang="zh")
    tomorrow_meals = build_day_meals_map(rows, tomorrow.isoformat(), lang="zh")
    day_after_meals = build_day_meals_map(rows, day_after.isoformat(), lang="zh")

    return render_template(
        "index.html",
        dishes=dishes,
        search_query=search_query,
        filtered_dishes=filtered_dishes,
        today_str=today.isoformat(),
        tomorrow_str=tomorrow.isoformat(),
        day_after_str=day_after.isoformat(),
        today_meals=today_meals,
        tomorrow_meals=tomorrow_meals,
        day_after_meals=day_after_meals,
        meal_types=MEAL_TYPES,
    )


@app.route("/today_order", methods=["POST"])
def today_order():
    cleanup_past_plans()

    meal_date = request.form.get("meal_date", "").strip()
    meal_type_zh = request.form.get("meal_type", "").strip()
    selected_dishes_zh = request.form.getlist("today_dishes")
    custom_dish_raw = request.form.get("today_custom_dish", "").strip()
    meal_time = request.form.get("meal_time", "").strip()

    save_meal(meal_date, meal_type_zh, selected_dishes_zh, custom_dish_raw, meal_time)
    return redirect(url_for("index") + "#order-section")


@app.route("/plans", methods=["GET"])
def plans():
    cleanup_past_plans()

    dishes = get_all_dishes()
    today = date.today().isoformat()
    future_rows = get_planned_orders_from(today)
    grouped_plans = group_planned_orders(future_rows, lang="zh")

    return render_template(
        "plans.html",
        dishes=dishes,
        meal_types=MEAL_TYPES,
        default_plan_date=today,
        grouped_plans=grouped_plans,
    )


@app.route("/plan_order", methods=["POST"])
def plan_order():
    cleanup_past_plans()

    meal_date = request.form.get("meal_date", "").strip()
    meal_type_zh = request.form.get("meal_type", "").strip()
    selected_dishes_zh = request.form.getlist("planned_dishes")
    custom_dish_raw = request.form.get("planned_custom_dish", "").strip()
    meal_time = request.form.get("meal_time", "").strip()

    save_meal(meal_date, meal_type_zh, selected_dishes_zh, custom_dish_raw, meal_time)
    return redirect(url_for("plans") + "#plans-list")


@app.route("/delete_plan", methods=["POST"])
def delete_plan():
    meal_date = request.form.get("meal_date", "").strip()
    meal_type_zh = request.form.get("meal_type_zh", "").strip()

    if meal_date and meal_type_zh in MEAL_TYPES:
        conn = get_conn()
        conn.execute(
            "DELETE FROM planned_orders WHERE meal_date = ? AND meal_type_zh = ?",
            (meal_date, meal_type_zh),
        )
        conn.commit()
        conn.close()

    return redirect(url_for("plans") + "#plans-list")


@app.route("/delete_dish", methods=["POST"])
def delete_dish():
    dish_id = request.form.get("dish_id", "").strip()
    search_query = request.form.get("search", "").strip()

    if dish_id:
        conn = get_conn()
        cur = conn.cursor()

        row = cur.execute(
            "SELECT name_zh FROM dishes WHERE id = ?",
            (dish_id,),
        ).fetchone()

        if row:
            dish_name_zh = row["name_zh"]
            cur.execute("DELETE FROM dishes WHERE id = ?", (dish_id,))
            cur.execute("DELETE FROM planned_orders WHERE dish_name_zh = ?", (dish_name_zh,))
            conn.commit()

        conn.close()

    return redirect(url_for("index", search=search_query) + "#delete-section")


@app.route("/dashboard", methods=["GET"])
def dashboard():
    cleanup_past_plans()

    lang = request.args.get("lang", "en").strip().lower()
    if lang not in ["zh", "en"]:
        lang = "en"

    today = date.today()
    today_rows = get_planned_orders_between(today.isoformat(), today.isoformat())
    today_meals = build_day_meals_map(today_rows, today.isoformat(), lang=lang)

    future_start = today + timedelta(days=1)
    future_end = today + timedelta(days=7)
    future_rows = get_planned_orders_between(future_start.isoformat(), future_end.isoformat())
    grouped_plans = group_planned_orders(future_rows, lang=lang)

    return render_template(
        "dashboard.html",
        lang=lang,
        today_str=today.isoformat(),
        today_meals=today_meals,
        grouped_plans=grouped_plans,
        meal_types=MEAL_TYPES,
        meal_type_en=MEAL_TYPE_EN,
    )


init_db()
cleanup_past_plans()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)