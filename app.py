from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import json
from pathlib import Path
from openai import OpenAI
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Load a local .env file if present (keeps OPENAI_API_KEY out of the code).
# Optional: if python-dotenv isn't installed, just rely on real env vars.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "orders.db"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

APP_TIMEZONE = ZoneInfo("Asia/Hong_Kong")

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
    "番茄": "Tomato",
    "胡萝卜": "Carrot",
    "洋葱": "Onion",
    "青椒": "Green Pepper",
    "蘑菇": "Mushroom",
    "玉米": "Corn",
    "菠菜": "Spinach",
    "葱": "Green Onion",
    "姜": "Ginger",
    "蒜": "Garlic",
    "米": "Rice",
    "面条": "Noodles",
    "馒头": "Steamed Bun",
    "酱油": "Soy Sauce",
    "盐": "Salt",
    "食用油": "Cooking Oil",
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

# --- Fridge / inventory ---

FRIDGE_STATUSES = ["有", "不多", "没有"]
FRIDGE_STATUS_EN = {
    "有": "Have",
    "不多": "Low",
    "没有": "None",
}
DEFAULT_FRIDGE_STATUS = "没有"

FRIDGE_CATEGORIES = ["蔬菜", "肉蛋", "主食", "调味", "其他"]
FRIDGE_CATEGORY_EN = {
    "蔬菜": "Vegetables",
    "肉蛋": "Meat & Egg",
    "主食": "Staples",
    "调味": "Seasoning",
    "其他": "Other",
}
CUSTOM_FRIDGE_CATEGORY = "其他"

# Seed ingredients grouped by category. All seed names exist in TRANSLATIONS,
# so init_db can store English names without calling the translation API.
PRESET_INGREDIENTS = {
    "蔬菜": ["青菜", "白菜", "西兰花", "土豆", "番茄", "胡萝卜", "洋葱", "蘑菇", "菠菜"],
    "肉蛋": ["鸡肉", "猪肉", "牛肉", "鱼", "虾", "鸡蛋", "豆腐"],
    "主食": ["米", "面条", "馒头"],
    "调味": ["酱油", "盐", "食用油", "葱", "姜", "蒜"],
}


def now_local():
    return datetime.now(APP_TIMEZONE)


def today_local():
    return now_local().date()


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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fridge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_zh TEXT NOT NULL UNIQUE,
            name_en TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '没有',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_column_exists(conn, "planned_orders", "meal_time", "TEXT")
    ensure_column_exists(conn, "dishes", "order_count", "INTEGER DEFAULT 0")

    for dish_zh in PRESET_DISHES_ZH:
        dish_en = translate_to_english(dish_zh)
        cur.execute(
            "INSERT OR IGNORE INTO dishes (name_zh, name_en) VALUES (?, ?)",
            (dish_zh, dish_en),
        )

    for category, ingredients in PRESET_INGREDIENTS.items():
        for name_zh in ingredients:
            name_en = TRANSLATIONS.get(name_zh, name_zh)
            cur.execute(
                "INSERT OR IGNORE INTO fridge_items (name_zh, name_en, category, status) VALUES (?, ?, ?, ?)",
                (name_zh, name_en, category, DEFAULT_FRIDGE_STATUS),
            )

    conn.commit()
    conn.close()


def cleanup_past_plans():
    today_str = today_local().isoformat()
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

    if chosen_date < today_local():
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
        # bump preference counter (survives daily cleanup of past plans)
        cur.execute("UPDATE dishes SET order_count = order_count + 1 WHERE name_zh = ?", (dish_zh,))

    conn.commit()
    conn.close()


# --- Fridge data helpers ---

def get_fridge_items():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name_zh, name_en, category, status FROM fridge_items ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


def build_fridge_groups(rows, lang="zh"):
    """Group fridge rows by category, preserving FRIDGE_CATEGORIES order."""
    groups = {cat: [] for cat in FRIDGE_CATEGORIES}
    for row in rows:
        category = row["category"] if row["category"] in groups else CUSTOM_FRIDGE_CATEGORY
        groups[category].append(row)

    ordered = []
    for cat in FRIDGE_CATEGORIES:
        if not groups[cat]:
            continue
        label = cat if lang == "zh" else FRIDGE_CATEGORY_EN[cat]
        ordered.append({"category_zh": cat, "label": label, "items": groups[cat]})
    return ordered


def set_fridge_status(item_id: str, status: str):
    if status not in FRIDGE_STATUSES:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE fridge_items SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, item_id),
    )
    conn.commit()
    conn.close()


def add_fridge_items(raw_text: str):
    names = split_custom_dishes(raw_text)
    if not names:
        return
    conn = get_conn()
    cur = conn.cursor()
    for name_zh in names:
        name_en = TRANSLATIONS.get(name_zh) or translate_to_english(name_zh)
        cur.execute(
            "INSERT OR IGNORE INTO fridge_items (name_zh, name_en, category, status) VALUES (?, ?, ?, ?)",
            (name_zh, name_en, CUSTOM_FRIDGE_CATEGORY, "有"),
        )
    conn.commit()
    conn.close()


def delete_fridge_item(item_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM fridge_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def get_recent_meal_names(days: int = 10):
    """Distinct dish names currently planned (today + upcoming), for AI variety.

    Note: past plans are cleaned up daily, so this is effectively "already on
    the menu soon" — used to avoid recommending the same thing again.
    """
    start = (today_local() - timedelta(days=days)).isoformat()
    end = (today_local() + timedelta(days=days)).isoformat()
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT dish_name_zh FROM planned_orders WHERE meal_date >= ? AND meal_date <= ?",
        (start, end),
    ).fetchall()
    conn.close()
    return [row["dish_name_zh"] for row in rows]


def get_favorite_dishes(limit: int = 8):
    """Most-ordered dishes — a lightweight taste/preference signal."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT name_zh FROM dishes WHERE order_count > 0 ORDER BY order_count DESC, id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [row["name_zh"] for row in rows]


def _parse_ai_json(raw_text: str):
    """Strip markdown fences and parse the model's JSON reply."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def get_ai_recommendation(meal_type_zh: str, lang: str = "zh"):
    """Ask the model for meal ideas.

    Uses what's in the fridge when marked, the family's most-ordered dishes
    (taste preference), and gently balances nutrition. Works even when the
    fridge isn't marked yet — it falls back to favorites + home cooking.

    Returns {"suggestions": [{"dishes": [...], "reason": str}], "to_buy": [...],
    "note": str} or {"error": str} on failure.
    """
    if meal_type_zh not in MEAL_TYPES:
        return {"error": "invalid meal type"}

    rows = get_fridge_items()
    have = [r["name_zh"] for r in rows if r["status"] == "有"]
    low = [r["name_zh"] for r in rows if r["status"] == "不多"]
    favorites = get_favorite_dishes()
    recent = get_recent_meal_names()
    has_stock = bool(have or low)

    note = ""
    if not has_stock:
        note = ("冰箱还没标记，这次按家里常点的菜和家常搭配来推荐。"
                if lang == "zh" else
                "Fridge not marked yet — suggesting from family favorites and balanced home cooking.")

    out_lang = "Chinese (Simplified)" if lang == "zh" else "English"
    stock_rule = (
        "Build the dishes mainly from what is in stock; staples like rice/oil/salt may be assumed."
        if has_stock else
        "The fridge stock is unknown, so suggest easy everyday dishes that fit the family's tastes."
    )
    prompt = (
        "You are a thoughtful home cooking assistant for a Chinese family. "
        "Suggest 2-3 simple, realistic home-style meal combinations for the given meal. "
        f"{stock_rule} "
        "Lean toward the family's favorite dishes/flavors, but keep each combo reasonably "
        "balanced and healthy (include a vegetable, avoid making every dish fried or heavy). "
        "Avoid repeating dishes that are already on the menu soon. "
        "List any common ingredients worth buying for your suggestions (especially if low or out of stock).\n\n"
        f"Meal: {MEAL_TYPE_EN[meal_type_zh]} ({meal_type_zh})\n"
        f"In stock (有): {', '.join(have) or 'unknown'}\n"
        f"Running low (不多): {', '.join(low) or 'none'}\n"
        f"Family favorites (most ordered): {', '.join(favorites) or 'none yet'}\n"
        f"Already on the menu soon (avoid repeating): {', '.join(recent) or 'none'}\n\n"
        f"Write all dish names, reasons and shopping items in {out_lang}. "
        "Keep each reason to a short phrase.\n"
        "Reply with ONLY valid JSON in this exact shape, no markdown:\n"
        '{"suggestions": [{"dishes": ["dish1", "dish2"], "reason": "short reason"}], '
        '"to_buy": ["item1", "item2"]}'
    )

    try:
        response = client.responses.create(model="gpt-4o-mini", input=prompt)
        data = _parse_ai_json(response.output_text)
    except Exception:
        return {"error": "ai_failed"}

    if not data or "suggestions" not in data:
        return {"error": "ai_failed"}

    suggestions = []
    for s in data.get("suggestions", []):
        dishes = [d for d in s.get("dishes", []) if isinstance(d, str) and d.strip()]
        if dishes:
            suggestions.append({"dishes": dishes, "reason": s.get("reason", "")})

    return {"suggestions": suggestions, "to_buy": data.get("to_buy", []), "note": note}


def _normalize_lang(raw):
    lang = (raw or "zh").strip().lower()
    return lang if lang in ("zh", "en") else "zh"


def _normalize_side(raw):
    side = (raw or "cook").strip().lower()
    return side if side in ("mom", "cook") else "cook"


# ===== Landing / role picker =====

@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")


# ===== Employer (Mom) side =====

def render_order(recommendation=None, rec_meal_type=""):
    cleanup_past_plans()

    dishes = get_all_dishes()
    today = today_local()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    rows = get_planned_orders_between(today.isoformat(), day_after.isoformat())
    today_meals = build_day_meals_map(rows, today.isoformat(), lang="zh")
    tomorrow_meals = build_day_meals_map(rows, tomorrow.isoformat(), lang="zh")
    day_after_meals = build_day_meals_map(rows, day_after.isoformat(), lang="zh")

    # fridge glance for the order page
    fridge_rows = get_fridge_items()
    fridge_have = [r["name_zh"] for r in fridge_rows if r["status"] == "有"]
    fridge_low = [r["name_zh"] for r in fridge_rows if r["status"] == "不多"]

    return render_template(
        "order.html",
        dishes=dishes,
        today_str=today.isoformat(),
        tomorrow_str=tomorrow.isoformat(),
        day_after_str=day_after.isoformat(),
        today_meals=today_meals,
        tomorrow_meals=tomorrow_meals,
        day_after_meals=day_after_meals,
        meal_types=MEAL_TYPES,
        meal_type_en=MEAL_TYPE_EN,
        recommendation=recommendation,
        rec_meal_type=rec_meal_type,
        fridge_have=fridge_have,
        fridge_low=fridge_low,
    )


@app.route("/order", methods=["GET"])
def order():
    return render_order()


@app.route("/today_order", methods=["POST"])
def today_order():
    cleanup_past_plans()

    meal_date = request.form.get("meal_date", "").strip()
    meal_type_zh = request.form.get("meal_type", "").strip()
    selected_dishes_zh = request.form.getlist("today_dishes")
    custom_dish_raw = request.form.get("today_custom_dish", "").strip()
    meal_time = request.form.get("meal_time", "").strip()

    save_meal(meal_date, meal_type_zh, selected_dishes_zh, custom_dish_raw, meal_time)
    return redirect(url_for("order") + "#order-section")


@app.route("/recommend", methods=["POST"])
def recommend():
    meal_type_zh = request.form.get("meal_type", "").strip()
    recommendation = get_ai_recommendation(meal_type_zh, lang="zh")
    return render_order(recommendation=recommendation, rec_meal_type=meal_type_zh)


@app.route("/recommend_to_plan", methods=["POST"])
def recommend_to_plan():
    meal_type_zh = request.form.get("meal_type", "").strip()
    dishes_raw = request.form.get("dishes", "").strip()
    selected = split_custom_dishes(dishes_raw)
    save_meal(today_local().isoformat(), meal_type_zh, selected, "", "")
    return redirect(url_for("order") + "#today-menu")


@app.route("/plans", methods=["GET"])
def plans():
    cleanup_past_plans()

    dishes = get_all_dishes()
    today = today_local().isoformat()
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


@app.route("/dishes", methods=["GET"])
def dishes_page():
    dishes = get_all_dishes()
    search_query = request.args.get("search", "").strip()

    if search_query:
        filtered_dishes = [
            dish for dish in dishes
            if search_query in dish["name_zh"] or search_query.lower() in dish["name_en"].lower()
        ]
    else:
        filtered_dishes = dishes

    return render_template(
        "dishes.html",
        filtered_dishes=filtered_dishes,
        search_query=search_query,
    )


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

    return redirect(url_for("dishes_page", search=search_query) + "#delete-section")


# ===== Helper (Maid) side =====

@app.route("/dashboard", methods=["GET"])
def dashboard():
    cleanup_past_plans()

    lang = _normalize_lang(request.args.get("lang"))

    today = today_local()
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


# ===== Fridge (shared inventory, both sides) =====

def render_fridge(lang, side):
    rows = get_fridge_items()
    fridge_groups = build_fridge_groups(rows, lang=lang)
    return render_template(
        "fridge.html",
        lang=lang,
        side=side,
        fridge_groups=fridge_groups,
        statuses=FRIDGE_STATUSES,
        status_en=FRIDGE_STATUS_EN,
    )


@app.route("/fridge", methods=["GET"])
def fridge():
    side = _normalize_side(request.args.get("side"))
    lang = "zh" if side == "mom" else _normalize_lang(request.args.get("lang"))
    return render_fridge(lang, side)


@app.route("/fridge_update", methods=["POST"])
def fridge_update():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    item_id = request.form.get("item_id", "").strip()
    status = request.form.get("status", "").strip()
    if item_id and status:
        set_fridge_status(item_id, status)
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


@app.route("/fridge_add", methods=["POST"])
def fridge_add():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    add_fridge_items(request.form.get("new_ingredient", "").strip())
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


@app.route("/fridge_delete", methods=["POST"])
def fridge_delete():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    item_id = request.form.get("item_id", "").strip()
    if item_id:
        delete_fridge_item(item_id)
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


init_db()
cleanup_past_plans()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)