from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
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
# Uploaded reference photos live next to the DB (on Render: the persistent disk).
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DB_PATH.parent / "uploads")))
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
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

# --- Dish categories ---

DISH_CATEGORIES = ["主食", "荤菜", "素菜", "汤", "其他"]
CUSTOM_DISH_CATEGORY = "其他"
PRESET_DISH_CATEGORY = {
    "白饭": "主食", "面": "主食", "粥": "主食",
    "鸡肉": "荤菜", "鱼": "荤菜", "蒸鱼": "荤菜",
    "青菜": "素菜", "番茄炒蛋": "素菜",
    "汤": "汤", "排骨汤": "汤",
}
PRESET_DISH_INGREDIENTS = {
    "白饭": "米", "粥": "米", "面": "面条",
    "鸡肉": "鸡肉", "鱼": "鱼", "蒸鱼": "鱼",
    "青菜": "青菜", "番茄炒蛋": "番茄,鸡蛋",
    "排骨汤": "排骨",
}

# Basic seasonings/staples we never put on the shopping list.
SHOPPING_STAPLES = {"盐", "油", "食用油", "酱油", "生抽", "老抽", "糖", "醋", "料酒", "水", "味精", "蚝油"}


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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_column_exists(conn, "planned_orders", "meal_time", "TEXT")
    ensure_column_exists(conn, "dishes", "order_count", "INTEGER DEFAULT 0")
    ensure_column_exists(conn, "dishes", "category", "TEXT DEFAULT '其他'")
    ensure_column_exists(conn, "dishes", "ref_link", "TEXT")
    ensure_column_exists(conn, "dishes", "ref_image", "TEXT")
    ensure_column_exists(conn, "dishes", "ingredients", "TEXT")

    for dish_zh in PRESET_DISHES_ZH:
        dish_en = translate_to_english(dish_zh)
        cur.execute(
            "INSERT OR IGNORE INTO dishes (name_zh, name_en, category, ingredients) VALUES (?, ?, ?, ?)",
            (dish_zh, dish_en, PRESET_DISH_CATEGORY.get(dish_zh, CUSTOM_DISH_CATEGORY),
             PRESET_DISH_INGREDIENTS.get(dish_zh)),
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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_past_plans():
    today_str = today_local().isoformat()
    conn = get_conn()
    conn.execute("DELETE FROM planned_orders WHERE meal_date < ?", (today_str,))
    conn.commit()
    conn.close()


def _guess_dish_category(name_zh: str) -> str:
    """Cheap offline guess from keywords. Returns '' if unsure."""
    name = name_zh or ""
    if "汤" in name:
        return "汤"
    if any(k in name for k in ["饭", "面", "粥", "馒头", "包子", "饺", "饼", "年糕", "粉"]):
        return "主食"
    if any(k in name for k in ["肉", "鸡", "鸭", "鱼", "虾", "蟹", "牛", "猪", "排骨", "蛋", "肠"]):
        return "荤菜"
    if any(k in name for k in ["菜", "西兰花", "土豆", "豆腐", "茄", "瓜", "菇", "笋", "萝卜", "豆", "菌"]):
        return "素菜"
    return ""


def classify_dish(dish_zh: str) -> str:
    """Pick a category for a dish: preset -> keyword rules -> AI -> 其他."""
    if dish_zh in PRESET_DISH_CATEGORY:
        return PRESET_DISH_CATEGORY[dish_zh]

    guess = _guess_dish_category(dish_zh)
    if guess:
        return guess

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=(
                "Classify this Chinese dish into exactly ONE category and reply with only "
                "that Chinese word: 主食 (staple/rice/noodles), 荤菜 (meat/egg/seafood dish), "
                "素菜 (vegetable/tofu dish), 汤 (soup), 其他 (other). "
                f"Dish: {dish_zh}"
            ),
        )
        out = (response.output_text or "").strip()
        for c in DISH_CATEGORIES:
            if c in out:
                return c
    except Exception:
        pass
    return CUSTOM_DISH_CATEGORY


def get_dish_ingredients(dish_zh: str) -> str:
    """Main ingredients of a dish as a comma-separated zh string.
    Preset map first, then AI. Returns '' on failure."""
    if dish_zh in PRESET_DISH_INGREDIENTS:
        return PRESET_DISH_INGREDIENTS[dish_zh]
    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=(
                "List ONLY the 1-4 main ingredients needed to cook this Chinese dish "
                "(skip basic seasonings like salt, oil, soy sauce, sugar). "
                "Reply with just the ingredient names in Simplified Chinese, comma-separated, nothing else. "
                f"Dish: {dish_zh}"
            ),
        )
        text = (response.output_text or "").strip()
        parts = [p.strip() for p in text.replace("，", ",").replace("、", ",").split(",")]
        parts = [p for p in parts if p and len(p) <= 8][:5]
        return ",".join(parts)
    except Exception:
        return ""


def upsert_dish(cur, dish_zh: str) -> str:
    row = cur.execute(
        "SELECT name_en FROM dishes WHERE name_zh = ?",
        (dish_zh,),
    ).fetchone()

    if row:
        return row["name_en"]

    dish_en = translate_to_english(dish_zh)
    category = classify_dish(dish_zh)
    ingredients = get_dish_ingredients(dish_zh)
    cur.execute(
        "INSERT OR IGNORE INTO dishes (name_zh, name_en, category, ingredients) VALUES (?, ?, ?, ?)",
        (dish_zh, dish_en, category, ingredients or None),
    )
    return dish_en


def get_all_dishes():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name_zh, name_en, category, ref_link, ref_image FROM dishes ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


def get_dish_ref_map():
    """Map dish name (zh and en) -> {link, image} for dishes that have a reference."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT name_zh, name_en, ref_link, ref_image FROM dishes "
        "WHERE ref_link IS NOT NULL OR ref_image IS NOT NULL"
    ).fetchall()
    conn.close()
    ref_map = {}
    for r in rows:
        ref = {"link": r["ref_link"], "image": r["ref_image"]}
        ref_map[r["name_zh"]] = ref
        if r["name_en"]:
            ref_map[r["name_en"]] = ref
    return ref_map


def build_dish_groups(dishes):
    """Group dishes by category, preserving DISH_CATEGORIES order."""
    groups = {c: [] for c in DISH_CATEGORIES}
    for d in dishes:
        cat = d["category"] if d["category"] in groups else CUSTOM_DISH_CATEGORY
        groups[cat].append(d)
    return [{"label": c, "items": groups[c]} for c in DISH_CATEGORIES if groups[c]]


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


def append_dishes_to_meal(meal_date: str, meal_type_zh: str, dishes_zh: list[str], meal_time: str = ""):
    """Add dishes to a meal WITHOUT removing what's already there (skip duplicates).

    Used for the AI 'add one by one' flow so each tap accumulates instead of
    overwriting the meal.
    """
    if meal_type_zh not in MEAL_TYPES:
        return
    try:
        chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
    except ValueError:
        return
    if chosen_date < today_local():
        return

    meal_type_en = MEAL_TYPE_EN[meal_type_zh]
    meal_time = (meal_time or "").strip()

    conn = get_conn()
    cur = conn.cursor()

    existing = {
        row["dish_name_zh"]
        for row in cur.execute(
            "SELECT dish_name_zh FROM planned_orders WHERE meal_date = ? AND meal_type_zh = ?",
            (meal_date, meal_type_zh),
        )
    }

    for dish_zh in dishes_zh:
        dish_zh = dish_zh.strip()
        if not dish_zh or dish_zh in existing:
            continue
        dish_en = upsert_dish(cur, dish_zh)
        cur.execute("""
            INSERT INTO planned_orders
            (meal_date, meal_type_zh, meal_type_en, dish_name_zh, dish_name_en, meal_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (meal_date, meal_type_zh, meal_type_en, dish_zh, dish_en, meal_time or None))
        cur.execute("UPDATE dishes SET order_count = order_count + 1 WHERE name_zh = ?", (dish_zh,))
        existing.add(dish_zh)

    # if a time was given, apply it to the whole meal (existing rows included)
    if meal_time:
        cur.execute(
            "UPDATE planned_orders SET meal_time = ? WHERE meal_date = ? AND meal_type_zh = ?",
            (meal_time, meal_date, meal_type_zh),
        )

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


def add_fridge_items(raw_text: str, category: str = CUSTOM_FRIDGE_CATEGORY):
    names = split_custom_dishes(raw_text)
    if not names:
        return
    if category not in FRIDGE_CATEGORIES:
        category = CUSTOM_FRIDGE_CATEGORY
    conn = get_conn()
    cur = conn.cursor()
    for name_zh in names:
        name_en = TRANSLATIONS.get(name_zh) or translate_to_english(name_zh)
        cur.execute(
            "INSERT OR IGNORE INTO fridge_items (name_zh, name_en, category, status) VALUES (?, ?, ?, ?)",
            (name_zh, name_en, category, "有"),
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


# --- Shopping list ---

def get_shopping_list():
    conn = get_conn()
    rows = conn.execute("SELECT id, item FROM shopping_list ORDER BY id ASC").fetchall()
    conn.close()
    return rows


def add_shopping_items(raw_text: str):
    items = split_custom_dishes(raw_text)
    if not items:
        return
    conn = get_conn()
    for item in items:
        conn.execute("INSERT OR IGNORE INTO shopping_list (item) VALUES (?)", (item,))
    conn.commit()
    conn.close()


def delete_shopping_item(item_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM shopping_list WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def get_upcoming_dish_names(days: int = 7):
    start = today_local().isoformat()
    end = (today_local() + timedelta(days=days)).isoformat()
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT dish_name_zh FROM planned_orders WHERE meal_date >= ? AND meal_date <= ?",
        (start, end),
    ).fetchall()
    conn.close()
    return [row["dish_name_zh"] for row in rows]


def generate_shopping_from_menu():
    """Ask AI which ingredients the planned dishes need that the fridge lacks,
    and add them to the shopping list. Returns True if anything was added."""
    dishes = get_upcoming_dish_names()
    if not dishes:
        return False

    fridge_rows = get_fridge_items()
    have = [r["name_zh"] for r in fridge_rows if r["status"] == "有"]

    prompt = (
        "You are helping a Chinese family plan grocery shopping. "
        "Given the dishes they plan to cook and what the fridge already has, "
        "list the common ingredients they still need to BUY (skip things already in the fridge "
        "and basic staples like water). Keep names short and in Simplified Chinese.\n\n"
        f"Planned dishes: {', '.join(dishes)}\n"
        f"Already in fridge: {', '.join(have) or 'nothing marked'}\n\n"
        'Reply with ONLY valid JSON: {"to_buy": ["item1", "item2"]}'
    )
    try:
        response = client.responses.create(model="gpt-4o-mini", input=prompt)
        data = _parse_ai_json(response.output_text)
    except Exception:
        return False

    if not data:
        return False
    items = [str(x).strip() for x in data.get("to_buy", []) if str(x).strip()]
    if not items:
        return False
    conn = get_conn()
    for item in items:
        conn.execute("INSERT OR IGNORE INTO shopping_list (item) VALUES (?)", (item,))
    conn.commit()
    conn.close()
    return True


def fridge_available_names():
    rows = get_fridge_items()
    return [r["name_zh"] for r in rows if r["status"] in ("有", "不多")]


def sync_shopping_from_plans():
    """For every upcoming planned dish, add any main ingredient the fridge lacks
    to the shopping list. Deterministic (no AI here); ingredients are looked up
    from the dishes table and lazily filled in via AI the first time a dish is seen."""
    planned = get_upcoming_dish_names()
    if not planned:
        return

    conn = get_conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(planned))
    rows = cur.execute(
        f"SELECT id, name_zh, ingredients FROM dishes WHERE name_zh IN ({placeholders})",
        planned,
    ).fetchall()

    # lazily backfill ingredients for dishes that don't have them yet
    dish_ingredients = []
    for r in rows:
        ing = r["ingredients"]
        if ing is None or ing == "":
            ing = get_dish_ingredients(r["name_zh"])
            cur.execute("UPDATE dishes SET ingredients = ? WHERE id = ?", (ing or None, r["id"]))
        dish_ingredients.append(ing or "")
    conn.commit()
    conn.close()

    avail = fridge_available_names()

    def available(ing):
        return any(ing == a or ing in a or a in ing for a in avail)

    needed = []
    for ing_str in dish_ingredients:
        for ing in ing_str.split(","):
            ing = ing.strip()
            if not ing or ing in SHOPPING_STAPLES or available(ing) or ing in needed:
                continue
            needed.append(ing)

    if needed:
        conn = get_conn()
        for item in needed:
            conn.execute("INSERT OR IGNORE INTO shopping_list (item) VALUES (?)", (item,))
        conn.commit()
        conn.close()


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
        "Prefer dishes that can be made from what is in stock; staples like rice/oil/salt may be assumed."
        if has_stock else
        "The fridge stock is unknown, so suggest easy everyday dishes that fit the family's tastes."
    )
    prompt = (
        "You are a practical home cooking assistant for a Chinese family. "
        "Recommend 5 to 6 INDIVIDUAL Chinese home-style dishes for the given meal. "
        "Each must be a real, common dish that people actually cook and order by its usual name "
        "(for example: 番茄炒蛋, 青椒土豆丝, 红烧排骨, 蒜蓉西兰花, 清炒时蔬, 紫菜蛋花汤, 麻婆豆腐). "
        "Keep it plain, everyday family home cooking — nothing fancy, gourmet, or restaurant-style, "
        "no rare ingredients or complicated techniques. "
        "Do NOT invent unusual ingredient mash-ups, and do NOT bundle them into a fixed set menu — "
        "list each dish on its own so the user can pick a few. "
        f"{stock_rule} "
        "Lean toward the family's favorite flavors, and keep the overall list balanced "
        "(a mix of meat and vegetable dishes, and a soup if it fits — not all fried or heavy). "
        "Avoid dishes that are already on the menu soon. "
        "Also list a few common ingredients worth buying (especially if low or out of stock).\n\n"
        f"Meal: {MEAL_TYPE_EN[meal_type_zh]} ({meal_type_zh})\n"
        f"In stock (有): {', '.join(have) or 'unknown'}\n"
        f"Running low (不多): {', '.join(low) or 'none'}\n"
        f"Family favorites (most ordered): {', '.join(favorites) or 'none yet'}\n"
        f"Already on the menu soon (avoid repeating): {', '.join(recent) or 'none'}\n\n"
        f"Write all dish names, reasons and shopping items in {out_lang}. "
        "Keep each reason to a few words.\n"
        "Reply with ONLY valid JSON in this exact shape, no markdown:\n"
        '{"dishes": [{"name": "dish name", "reason": "short reason"}], '
        '"to_buy": ["item1", "item2"]}'
    )

    try:
        response = client.responses.create(model="gpt-4o-mini", input=prompt)
        data = _parse_ai_json(response.output_text)
    except Exception:
        return {"error": "ai_failed"}

    if not data or "dishes" not in data:
        return {"error": "ai_failed"}

    dishes = []
    seen = set()
    for d in data.get("dishes", []):
        name = (d.get("name") if isinstance(d, dict) else str(d)).strip()
        if name and name not in seen:
            seen.add(name)
            reason = d.get("reason", "") if isinstance(d, dict) else ""
            dishes.append({"name": name, "reason": reason})

    return {"dishes": dishes, "to_buy": data.get("to_buy", []), "note": note}


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
        dish_groups=build_dish_groups(dishes),
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
        shopping_list=get_shopping_list(),
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
    custom_dishes = split_custom_dishes(request.form.get("today_custom_dish", "").strip())
    meal_time = request.form.get("meal_time", "").strip()

    dishes = []
    for d in list(selected_dishes_zh) + custom_dishes:
        d = d.strip()
        if d and d not in dishes:
            dishes.append(d)

    # append (don't overwrite) so manual orders and AI-added dishes coexist
    append_dishes_to_meal(meal_date, meal_type_zh, dishes, meal_time)
    sync_shopping_from_plans()
    return redirect(url_for("order") + "#today-menu")


@app.route("/remove_meal_dish", methods=["POST"])
def remove_meal_dish():
    meal_date = request.form.get("meal_date", "").strip()
    meal_type_zh = request.form.get("meal_type", "").strip()
    dish = request.form.get("dish", "").strip()
    if meal_date and meal_type_zh and dish:
        conn = get_conn()
        conn.execute(
            "DELETE FROM planned_orders WHERE meal_date = ? AND meal_type_zh = ? AND dish_name_zh = ?",
            (meal_date, meal_type_zh, dish),
        )
        conn.commit()
        conn.close()
    if _is_xhr():
        return ("", 204)
    return redirect(url_for("order") + "#today-menu")


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
    append_dishes_to_meal(today_local().isoformat(), meal_type_zh, selected)
    sync_shopping_from_plans()
    if _is_xhr():
        return ("", 204)
    return redirect(url_for("order") + "#today-menu")


@app.route("/shopping_add", methods=["POST"])
def shopping_add():
    add_shopping_items(request.form.get("item", "").strip())
    return redirect(url_for("order") + "#shopping")


@app.route("/shopping_generate", methods=["POST"])
def shopping_generate():
    generate_shopping_from_menu()
    return redirect(url_for("order") + "#shopping")


@app.route("/shopping_done", methods=["POST"])
def shopping_done():
    item_id = request.form.get("item_id", "").strip()
    if item_id:
        delete_shopping_item(item_id)
    if _is_xhr():
        return ("", 204)
    where = request.form.get("from", "order")
    if where == "cook":
        lang = _normalize_lang(request.form.get("lang"))
        return redirect(url_for("dashboard", lang=lang) + "#shopping")
    return redirect(url_for("order") + "#shopping")


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
        dish_groups=build_dish_groups(dishes),
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
    sync_shopping_from_plans()
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
    return render_template(
        "dishes.html",
        dish_groups=build_dish_groups(dishes),
        dish_categories=DISH_CATEGORIES,
    )


@app.route("/set_dish_category", methods=["POST"])
def set_dish_category():
    dish_id = request.form.get("dish_id", "").strip()
    category = request.form.get("category", "").strip()
    search_query = request.form.get("search", "").strip()
    if dish_id and category in DISH_CATEGORIES:
        conn = get_conn()
        conn.execute("UPDATE dishes SET category = ? WHERE id = ?", (category, dish_id))
        conn.commit()
        conn.close()
    if _is_xhr():
        return ("", 204)
    return redirect(url_for("dishes_page", search=search_query) + "#manage")


@app.route("/set_dish_ref", methods=["POST"])
def set_dish_ref():
    dish_id = request.form.get("dish_id", "").strip()
    ref_link = request.form.get("ref_link", "").strip()
    if not dish_id:
        return redirect(url_for("dishes_page") + "#manage")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE dishes SET ref_link = ? WHERE id = ?", (ref_link or None, dish_id))

    file = request.files.get("image")
    if file and file.filename:
        ext = os.path.splitext(secure_filename(file.filename))[1].lower()
        if ext in ALLOWED_IMAGE_EXT:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"dish_{dish_id}{ext}"
            file.save(str(UPLOAD_DIR / fname))
            cur.execute("UPDATE dishes SET ref_image = ? WHERE id = ?", (fname, dish_id))

    conn.commit()
    conn.close()
    return redirect(url_for("dishes_page") + "#manage")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@app.route("/auto_categorize_dishes", methods=["POST"])
def auto_categorize_dishes():
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, name_zh FROM dishes WHERE category = ? OR category IS NULL",
        (CUSTOM_DISH_CATEGORY,),
    ).fetchall()
    for row in rows:
        category = classify_dish(row["name_zh"])
        if category != CUSTOM_DISH_CATEGORY:
            cur.execute("UPDATE dishes SET category = ? WHERE id = ?", (category, row["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("dishes_page") + "#manage")


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

    if _is_xhr():
        return ("", 204)
    return redirect(url_for("dishes_page", search=search_query) + "#manage")


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
        shopping_list=get_shopping_list(),
        dish_ref_map=get_dish_ref_map(),
    )


# ===== Fridge (shared inventory, both sides) =====

def render_fridge(lang, side):
    rows = get_fridge_items()
    fridge_groups = build_fridge_groups(rows, lang=lang)
    add_categories = [
        {"value": c, "label": c if lang == "zh" else FRIDGE_CATEGORY_EN[c]}
        for c in FRIDGE_CATEGORIES
    ]
    return render_template(
        "fridge.html",
        lang=lang,
        side=side,
        fridge_groups=fridge_groups,
        add_categories=add_categories,
        statuses=FRIDGE_STATUSES,
        status_en=FRIDGE_STATUS_EN,
    )


@app.route("/fridge", methods=["GET"])
def fridge():
    side = _normalize_side(request.args.get("side"))
    lang = "zh" if side == "mom" else _normalize_lang(request.args.get("lang"))
    return render_fridge(lang, side)


def _is_xhr():
    return request.headers.get("X-Requested-With") == "fetch"


@app.route("/fridge_update", methods=["POST"])
def fridge_update():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    item_id = request.form.get("item_id", "").strip()
    status = request.form.get("status", "").strip()
    if item_id and status:
        set_fridge_status(item_id, status)
    if _is_xhr():
        return ("", 204)
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


@app.route("/fridge_add", methods=["POST"])
def fridge_add():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    category = request.form.get("category", CUSTOM_FRIDGE_CATEGORY).strip()
    add_fridge_items(request.form.get("new_ingredient", "").strip(), category)
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


@app.route("/fridge_delete", methods=["POST"])
def fridge_delete():
    side = _normalize_side(request.form.get("side"))
    lang = _normalize_lang(request.form.get("lang"))
    item_id = request.form.get("item_id", "").strip()
    if item_id:
        delete_fridge_item(item_id)
    if _is_xhr():
        return ("", 204)
    return redirect(url_for("fridge", lang=lang, side=side) + "#fridge-list")


init_db()
cleanup_past_plans()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)