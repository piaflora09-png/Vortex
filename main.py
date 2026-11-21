import os
import json
import time
import asyncio
import sqlite3
import datetime
import threading
import urllib.request
from flask import Flask, request, jsonify, send_from_directory
import discord
from discord.ext import commands

# =========================================================
# CONFIGURATION (Set via Render / Hosting Environment Vars)
# =========================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "1542941315933667348"))
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "1540575139538796634"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vortexadmin2026")
PORT = int(os.getenv("PORT", "10000"))

WEBHOOK_ITEM_ADDED = os.getenv("WEBHOOK_ITEM_ADDED", "").strip()
WEBHOOK_ITEM_SOLD = os.getenv("WEBHOOK_ITEM_SOLD", "").strip()
WEBHOOK_TICKET_CLOSED = os.getenv("WEBHOOK_TICKET_CLOSED", "").strip()

DB_PATH = os.getenv("DB_PATH", "vortexshop.db").strip()
LEGACY_JSON_FILE = "vortex_state.json"
HTML_FILE = "index-v2.html"

DEFAULT_SEED_ITEMS = [
    {
        "id": "vx-seed-1",
        "name": "Harvester + Icepiercer Bundle",
        "category": "Murder Mystery 2",
        "stock": 3,
        "price": "24.00",
        "currency": "USD",
        "posted_by": "@mvn412.",
        "description": "High-tier MM2 bundle. Verified official ticket & MM escrow only.",
        "image_url": "",
        "status": "AVAILABLE",
    },
    {
        "id": "vx-seed-2",
        "name": "Raccoon + Dragonfly Pack",
        "category": "Grow a Garden 2",
        "stock": 5,
        "price": "12.50",
        "currency": "USD",
        "posted_by": "@mvn412.",
        "description": "Grow a Garden 2 pets stock ready for fast ticket delivery.",
        "image_url": "",
        "status": "AVAILABLE",
    },
]

db_lock = threading.Lock()


def get_db_connection():
    parent_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_item(row):
    stock = max(0, int(row["stock"] if row["stock"] is not None else 0))
    status = "SOLD" if stock <= 0 else (row["status"] or "AVAILABLE")
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "stock": stock,
        "price": row["price"],
        "currency": row["currency"],
        "posted_by": row["posted_by"],
        "description": row["description"] or "",
        "image_url": row["image_url"] or "",
        "status": status,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_ticket(row):
    try:
        t1 = json.loads(row["trader_1_json"] or "{}")
    except Exception:
        t1 = {}
    try:
        t2 = json.loads(row["trader_2_json"] or "{}")
    except Exception:
        t2 = {}
    return {
        "ticket_id": row["ticket_id"],
        "status": row["status"] or "CLOSED",
        "ticket_type": row["ticket_type"] or "Middleman Escrow",
        "game": row["game"] or "Any Game",
        "trade_value": row["trade_value"] or "Standard",
        "trader_1": t1,
        "trader_2": t2,
        "claimed_by": row["claimed_by"] or "@mvn412.",
        "notes": row["notes"] or "",
        "server_id": row["server_id"] or "",
        "synced_to_website": bool(row["synced_to_website"]),
        "closed_at": row["closed_at"],
    }


def init_database():
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db_lock:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                stock INTEGER NOT NULL DEFAULT 1,
                price TEXT NOT NULL DEFAULT '0.00',
                currency TEXT NOT NULL DEFAULT 'USD',
                posted_by TEXT NOT NULL DEFAULT '@mvn412.',
                description TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'AVAILABLE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS closed_tickets (
                ticket_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'CLOSED',
                ticket_type TEXT NOT NULL DEFAULT 'Middleman Escrow',
                game TEXT NOT NULL DEFAULT 'Any Game',
                trade_value TEXT NOT NULL DEFAULT 'Standard',
                trader_1_json TEXT NOT NULL DEFAULT '{}',
                trader_2_json TEXT NOT NULL DEFAULT '{}',
                claimed_by TEXT NOT NULL DEFAULT '@mvn412.',
                notes TEXT NOT NULL DEFAULT '',
                server_id TEXT NOT NULL DEFAULT '',
                synced_to_website INTEGER NOT NULL DEFAULT 1,
                closed_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                ref_id TEXT,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        cur.execute("SELECT COUNT(*) AS cnt FROM shop_items")
        item_count = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM closed_tickets")
        ticket_count = cur.fetchone()["cnt"]
        cur.execute("SELECT value FROM app_meta WHERE key = 'seeded_once'")
        seeded_row = cur.fetchone()
        already_seeded = bool(seeded_row and seeded_row["value"] == "1")

        if item_count == 0 and ticket_count == 0 and os.path.exists(LEGACY_JSON_FILE):
            try:
                with open(LEGACY_JSON_FILE, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
                for idx, it in enumerate(legacy.get("items", [])):
                    st = max(0, int(it.get("stock", 1)))
                    item_id = str(it.get("id") or f"vx-legacy-{int(time.time() * 1000)}-{idx}")
                    created = str(it.get("created_at") or now_iso)
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO shop_items (
                            id, name, category, stock, price, currency, posted_by,
                            description, image_url, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item_id,
                            str(it.get("name") or "Untitled Item"),
                            str(it.get("category") or "General"),
                            st,
                            str(it.get("price") or "0.00"),
                            str(it.get("currency") or "USD").upper(),
                            str(it.get("posted_by") or "@mvn412."),
                            str(it.get("description") or ""),
                            str(it.get("image_url") or ""),
                            "SOLD" if st <= 0 else str(it.get("status") or "AVAILABLE"),
                            created,
                            now_iso,
                        ),
                    )
                for idx, tk in enumerate(legacy.get("closed_tickets", [])):
                    tid = str(tk.get("ticket_id") or f"VX-LEG-{idx + 1}")
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO closed_tickets (
                            ticket_id, status, ticket_type, game, trade_value,
                            trader_1_json, trader_2_json, claimed_by, notes,
                            server_id, synced_to_website, closed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            tid,
                            str(tk.get("status") or "CLOSED"),
                            str(tk.get("ticket_type") or "Middleman Escrow"),
                            str(tk.get("game") or "Any Game"),
                            str(tk.get("trade_value") or "Standard"),
                            json.dumps(tk.get("trader_1") or {}, ensure_ascii=False),
                            json.dumps(tk.get("trader_2") or {}, ensure_ascii=False),
                            str(tk.get("claimed_by") or "@mvn412."),
                            str(tk.get("notes") or ""),
                            str(tk.get("server_id") or ""),
                            str(tk.get("closed_at") or now_iso),
                        ),
                    )
                already_seeded = True
            except Exception as exc:
                print(f"[DB Legacy Import Warning] {exc}")

        cur.execute("SELECT COUNT(*) AS cnt FROM shop_items")
        if cur.fetchone()["cnt"] == 0 and not already_seeded:
            for seed in DEFAULT_SEED_ITEMS:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO shop_items (
                        id, name, category, stock, price, currency, posted_by,
                        description, image_url, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seed["id"],
                        seed["name"],
                        seed["category"],
                        seed["stock"],
                        seed["price"],
                        seed["currency"],
                        seed["posted_by"],
                        seed["description"],
                        seed["image_url"],
                        seed["status"],
                        now_iso,
                        now_iso,
                    ),
                )

        cur.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('seeded_once', '1')"
        )
        conn.commit()
        conn.close()


def record_activity(event_type: str, ref_id: str, summary: str):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db_lock:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO activity_logs (event_type, ref_id, summary, created_at) VALUES (?, ?, ?, ?)",
            (event_type, ref_id, summary, now_iso),
        )
        conn.commit()
        conn.close()


def get_store_state():
    with db_lock:
        conn = get_db_connection()
        item_rows = conn.execute("SELECT * FROM shop_items ORDER BY created_at DESC").fetchall()
        ticket_rows = conn.execute("SELECT * FROM closed_tickets ORDER BY closed_at DESC LIMIT 50").fetchall()
        conn.close()
    return {
        "items": [_row_to_item(r) for r in item_rows],
        "closed_tickets": [_row_to_ticket(r) for r in ticket_rows],
    }


def db_add_item(item: dict):
    with db_lock:
        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO shop_items (
                id, name, category, stock, price, currency, posted_by,
                description, image_url, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["category"],
                item["stock"],
                item["price"],
                item["currency"],
                item["posted_by"],
                item["description"],
                item["image_url"],
                item["status"],
                item["created_at"],
                item["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
    record_activity("ITEM_ADDED", item["id"], f"Added {item['name']} (stock={item['stock']}, {item['price']} {item['currency']})")


def db_update_item(item_id: str, fields: dict):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db_lock:
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.close()
            return None
        next_stock = max(0, int(fields.get("stock", row["stock"])))
        next_status = "SOLD" if next_stock <= 0 else str(fields.get("status") or "AVAILABLE")
        conn.execute(
            """
            UPDATE shop_items
            SET name = ?, category = ?, stock = ?, price = ?, currency = ?,
                image_url = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(fields.get("name", row["name"])),
                str(fields.get("category", row["category"])),
                next_stock,
                str(fields.get("price", row["price"])),
                str(fields.get("currency", row["currency"])).upper(),
                str(fields.get("image_url", row["image_url"] or "")),
                next_status,
                now_iso,
                item_id,
            ),
        )
        updated_row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        conn.close()
    updated = _row_to_item(updated_row)
    record_activity("ITEM_UPDATED", item_id, f"Updated {updated['name']} (stock={next_stock})")
    return updated


def db_adjust_stock(item_id: str, delta: int):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db_lock:
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.close()
            return None
        current_stock = max(0, int(row["stock"] if row["stock"] is not None else 0))
        next_stock = max(0, current_stock + int(delta))
        next_status = "SOLD" if next_stock <= 0 else "AVAILABLE"
        conn.execute(
            "UPDATE shop_items SET stock = ?, status = ?, updated_at = ? WHERE id = ?",
            (next_stock, next_status, now_iso, item_id),
        )
        updated_row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        conn.close()
    updated = _row_to_item(updated_row)
    record_activity("STOCK_ADJUSTED", item_id, f"{updated['name']} stock -> {next_stock} ({next_status})")
    return updated


def db_delete_item(item_id: str):
    with db_lock:
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.close()
            return None
        deleted = _row_to_item(row)
        conn.execute("DELETE FROM shop_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
    record_activity("ITEM_DELETED", item_id, f"Deleted {deleted['name']}")
    return deleted


def db_upsert_closed_ticket(rec: dict):
    with db_lock:
        conn = get_db_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO closed_tickets (
                ticket_id, status, ticket_type, game, trade_value,
                trader_1_json, trader_2_json, claimed_by, notes,
                server_id, synced_to_website, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                rec["ticket_id"],
                rec["status"],
                rec["ticket_type"],
                rec["game"],
                rec["trade_value"],
                json.dumps(rec.get("trader_1") or {}, ensure_ascii=False),
                json.dumps(rec.get("trader_2") or {}, ensure_ascii=False),
                rec["claimed_by"],
                rec["notes"],
                rec["server_id"],
                rec["closed_at"],
            ),
        )
        conn.commit()
        conn.close()
    record_activity("TICKET_CLOSED", rec["ticket_id"], f"Closed ticket {rec['ticket_id']} ({rec['game']})")


def get_db_stats():
    with db_lock:
        conn = get_db_connection()
        total_items = conn.execute("SELECT COUNT(*) AS c FROM shop_items").fetchone()["c"]
        available_items = conn.execute("SELECT COUNT(*) AS c FROM shop_items WHERE stock > 0").fetchone()["c"]
        total_tickets = conn.execute("SELECT COUNT(*) AS c FROM closed_tickets").fetchone()["c"]
        total_logs = conn.execute("SELECT COUNT(*) AS c FROM activity_logs").fetchone()["c"]
        conn.close()
    return {
        "db_path": os.path.abspath(DB_PATH),
        "shop_items_count": total_items,
        "available_items_count": available_items,
        "closed_tickets_count": total_tickets,
        "activity_logs_count": total_logs,
    }


init_database()

# =========================================================
# LIVE SHOWCASE CACHE & WEBHOOK HELPER
# =========================================================
showcase_cache = {
    "last_synced": "Starting...",
    "profile": {
        "id": str(OWNER_USER_ID),
        "display_name": "VortexShop",
        "username": "mvn412.",
        "bio_link_text": "Check out vortexshop.onrender.com",
        "store_url": "https://vortexshop.onrender.com",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
        "banner_url": "",
        "status": "online",
        "custom_status": {"emoji": "⚡", "text": "Open for MM & Crosstrades"},
        "clan_emoji": "🍃",
        "clan_tag": "VEM",
        "role_badge_text": "Founder • VortexShop",
        "owner_line": "Owner of this server-",
        "invite_url": "https://discord.gg/3JPatMmyF",
        "full_bio": "Official Vortex Exchange & MM Hub. Fast escrow across MM2, Grow a Garden 2, Adopt Me!, PS99, Blade Ball & any Roblox game.",
        "member_since": "Aug 22, 2026",
        "mutual_servers_count": 4,
        "vouches_count": 120,
        "custom_trade_note": "Verified Roblox crosstrading across any game via official server tickets.",
        "badges": [
            {"id": "staff", "label": "Vortex Founder", "fallback_icon": "👑"},
            {"id": "mm", "label": "Trusted Escrow", "fallback_icon": "🛡️"},
            {"id": "booster", "label": "Server Booster", "fallback_icon": "💎"},
        ],
        "games": [
            {"tag": "MM2", "title": "Murder Mystery 2", "tier": "Weapons & Sets", "note": "Harvester, Icepiercer, Gingerscope, Corrupt, Sakura & Dark Sets."},
            {"tag": "GaG 2", "title": "Grow a Garden 2", "tier": "Pets & Seeds", "note": "Raccoon, Dragonfly, Unicorn, Black Dragon & rare seeds."},
            {"tag": "AM", "title": "Adopt Me!", "tier": "High-Tier", "note": "Mega/Neon legs, Shadow/Bat Dragons & verified escrow."},
            {"tag": "ALL", "title": "Any Roblox Game", "tier": "Any Game", "note": "PS99, Blade Ball, Steal a Brainrot, Baddies & custom deals."},
        ],
        "vouches": [
            {"name": "Aurelia", "trade_tag": "MM2 Harvester Bundle", "stars": 5, "stamp": "Verified Escrow", "note": "Super fast middleman and smooth trade!"},
            {"name": "tefo900", "trade_tag": "Grow a Garden 2 Pets", "stars": 5, "stamp": "Verified Escrow", "note": "Legit seller, zero delays inside the ticket."},
        ],
        "mm_rules": [
            "Never trade directly in-game without an official ticket and verified Middleman.",
            "Always verify the Middleman's exact Discord User ID inside your ticket channel.",
            "No pre-payment is collected on the website—all payments happen inside your ticket.",
            "Confirm both sides' items before approving the final release.",
        ],
    },
    "server": {
        "id": str(GUILD_ID),
        "name": "Vortex Exchange & MM",
        "invite_url": "https://discord.gg/3JPatMmyF",
        "member_count": 420,
        "online_count": 118,
        "offline_count": 302,
        "boost_count": 14,
        "icon_url": "",
        "banner_url": "",
    },
    "role_catalog": [],
    "staff_members": [],
}


def post_discord_webhook(webhook_url: str, title: str, fields: list, color: int = 0xA855F7, image_url: str = ""):
    if not webhook_url:
        return
    embed = {
        "title": title,
        "color": color,
        "fields": fields,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "footer": {"text": "VortexShop SQLite Live Sync"},
    }
    if image_url and image_url.startswith("http"):
        embed["thumbnail"] = {"url": image_url}
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "VortexShopBot/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as exc:
        print(f"[Webhook Error] {exc}")


# =========================================================
# FLASK WEB SERVER & REST API
# =========================================================
app = Flask(__name__, static_folder=".")


@app.route("/")
def serve_index():
    target = HTML_FILE if os.path.exists(HTML_FILE) else "index.html"
    return send_from_directory(".", target)


@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "service": "VortexShop",
        "bot_ready": bot.is_ready(),
        "database": get_db_stats(),
    })


@app.route("/api/showcase", methods=["GET"])
def api_showcase():
    return jsonify(showcase_cache)


@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(get_store_state())


@app.route("/api/admin/verify", methods=["POST"])
def api_admin_verify():
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403
    return jsonify({"ok": True})


@app.route("/api/shop/webhook", methods=["POST"])
def api_shop_webhook():
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403
    event_name = str(data.get("event") or "shop_event")
    item = data.get("item") if isinstance(data.get("item"), dict) else {}
    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_ITEM_SOLD or WEBHOOK_ITEM_ADDED,
            f"🔔 VortexShop Event ({event_name}): {item.get('name', 'Item')}",
            [
                {"name": "Price", "value": f"{item.get('price', '0.00')} {item.get('currency', 'USD')}", "inline": True},
                {"name": "Stock", "value": str(item.get("stock", 0)), "inline": True},
                {"name": "Seller", "value": str(item.get("posted_by", "@mvn412.")), "inline": True},
            ],
            0xA855F7,
            str(item.get("image_url", "")),
        ),
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@app.route("/api/shop/items", methods=["POST"])
def api_add_shop_item():
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403

    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "General")).strip()
    if not name:
        return jsonify({"ok": False, "error": "Item name is required."}), 400

    stock = max(0, int(data.get("stock", 1)))
    price = str(data.get("price", "0.00")).strip()
    currency = str(data.get("currency", "USD")).strip().upper()
    posted_by = str(data.get("posted_by", "@mvn412.")).strip()
    if not posted_by.startswith("@"):
        posted_by = f"@{posted_by}"
    description = str(data.get("description", "")).strip()
    image_url = str(data.get("image_url", "")).strip()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    item = {
        "id": f"vx-{int(time.time() * 1000)}",
        "name": name,
        "category": category,
        "stock": stock,
        "price": price,
        "currency": currency,
        "posted_by": posted_by,
        "description": description,
        "image_url": image_url,
        "status": "SOLD" if stock <= 0 else "AVAILABLE",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    db_add_item(item)

    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_ITEM_ADDED,
            f"🛒 New VortexShop Listing: {name}",
            [
                {"name": "Category", "value": category, "inline": True},
                {"name": "Price", "value": f"{price} {currency}", "inline": True},
                {"name": "Stock", "value": str(stock), "inline": True},
                {"name": "Posted By", "value": posted_by, "inline": True},
            ],
            0x22C55E,
            image_url,
        ),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "item": item})


@app.route("/api/shop/items/<item_id>", methods=["PATCH"])
def api_patch_shop_item(item_id):
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403

    updated = db_update_item(item_id, data)
    if not updated:
        return jsonify({"ok": False, "error": "Item not found."}), 404

    return jsonify({"ok": True, "item": updated})


@app.route("/api/shop/items/<item_id>/minus", methods=["POST"])
def api_minus_shop_item(item_id):
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403

    delta = int(data.get("delta", -1))
    if delta >= 0:
        delta = -abs(delta)

    updated_item = db_adjust_stock(item_id, delta)
    if not updated_item:
        return jsonify({"ok": False, "error": "Item not found."}), 404

    return jsonify({"ok": True, "item": updated_item})


@app.route("/api/shop/items/<item_id>/sold", methods=["POST"])
def api_mark_item_sold(item_id):
    data = request.get_json(silent=True) or {}
    buyer = str(data.get("buyer", "@buyer")).strip()
    sold_qty = max(1, int(data.get("sold_qty", 1)))

    updated_item = db_adjust_stock(item_id, -sold_qty)
    if not updated_item:
        return jsonify({"ok": False, "error": "Item not found."}), 404

    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_ITEM_SOLD,
            f"✅ VortexShop Item Sold: {updated_item['name']}",
            [
                {"name": "Price", "value": f"{updated_item['price']} {updated_item['currency']}", "inline": True},
                {"name": "Seller", "value": updated_item["posted_by"], "inline": True},
                {"name": "Buyer", "value": buyer, "inline": True},
                {"name": "Remaining Stock", "value": str(updated_item["stock"]), "inline": True},
            ],
            0xF59E0B,
            updated_item.get("image_url", ""),
        ),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "item": updated_item})


@app.route("/api/shop/items/<item_id>", methods=["DELETE"])
def api_delete_shop_item(item_id):
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403

    deleted = db_delete_item(item_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Item not found."}), 404

    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_ITEM_SOLD or WEBHOOK_ITEM_ADDED,
            f"🗑️ VortexShop Item Deleted: {deleted['name']}",
            [
                {"name": "Item ID", "value": deleted["id"], "inline": True},
                {"name": "Seller", "value": deleted["posted_by"], "inline": True},
            ],
            0xE11D48,
            deleted.get("image_url", ""),
        ),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/tickets/closed", methods=["POST"])
def api_ticket_closed():
    rec = request.get_json(silent=True) or {}
    ticket_id = str(rec.get("ticket_id") or f"VX-{int(time.time()) % 10000}").strip()
    normalized = {
        "ticket_id": ticket_id,
        "status": "CLOSED",
        "ticket_type": str(rec.get("ticket_type") or "Middleman Escrow").strip(),
        "game": str(rec.get("game") or "Any Game").strip(),
        "trade_value": str(rec.get("trade_value") or "Standard").strip(),
        "trader_1": rec.get("trader_1") if isinstance(rec.get("trader_1"), dict) else {},
        "trader_2": rec.get("trader_2") if isinstance(rec.get("trader_2"), dict) else {},
        "claimed_by": str(rec.get("claimed_by") or "@mvn412.").strip(),
        "notes": str(rec.get("notes") or "").strip(),
        "server_id": str(rec.get("server_id") or GUILD_ID).strip(),
        "synced_to_website": True,
        "closed_at": str(rec.get("closed_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
    }

    db_upsert_closed_ticket(normalized)

    t1 = normalized.get("trader_1", {})
    t2 = normalized.get("trader_2", {})
    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_TICKET_CLOSED,
            f"🔒 Closed Trade Ticket: {normalized['ticket_id']}",
            [
                {"name": "Game / Category", "value": f"{normalized.get('game', 'N/A')} ({normalized.get('ticket_type', 'Escrow')})", "inline": True},
                {"name": "Claimed By", "value": normalized.get("claimed_by", "@staff"), "inline": True},
                {"name": f"Trader 1: {t1.get('name', 'Trader 1')}", "value": f"Gave: {t1.get('giving_items', '-')}", "inline": False},
                {"name": f"Trader 2: {t2.get('name', 'Trader 2')}", "value": f"Gave: {t2.get('giving_items', '-')}", "inline": False},
            ],
            0xA855F7,
        ),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "ticket": normalized})


# =========================================================
# DISCORD BOT (Live Guild & Staff Sync + Prefix Cmds)
# =========================================================
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def sync_discord_data_to_cache():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    online_statuses = {discord.Status.online, discord.Status.idle, discord.Status.dnd}
    online_count = sum(1 for m in guild.members if m.status in online_statuses)
    total_members = guild.member_count or len(guild.members)
    offline_count = max(0, total_members - online_count)

    showcase_cache["server"].update({
        "id": str(guild.id),
        "name": guild.name,
        "member_count": total_members,
        "online_count": online_count,
        "offline_count": offline_count,
        "boost_count": guild.premium_subscription_count or 0,
        "icon_url": guild.icon.url if guild.icon else "",
        "banner_url": guild.banner.url if guild.banner else "",
    })

    owner = guild.get_member(OWNER_USER_ID) or guild.owner
    if owner:
        custom_act = next((a for a in owner.activities if isinstance(a, discord.CustomActivity)), None)
        showcase_cache["profile"].update({
            "id": str(owner.id),
            "display_name": owner.display_name,
            "username": owner.name,
            "avatar_url": owner.display_avatar.url,
            "status": str(owner.status),
            "custom_status": {
                "emoji": str(custom_act.emoji) if custom_act and custom_act.emoji else "⚡",
                "text": custom_act.name if custom_act and custom_act.name else "Open for MM & Crosstrades",
            },
        })

    tracked_roles = [
        r for r in sorted(guild.roles, key=lambda x: x.position, reverse=True)
        if not r.is_default() and not r.managed and (
            r.permissions.administrator
            or r.permissions.manage_messages
            or any(k in r.name.lower() for k in ("owner", "founder", "admin", "mod", "staff", "mm", "middleman", "trusted"))
        )
    ]

    showcase_cache["role_catalog"] = [
        {
            "id": str(r.id),
            "label": r.name,
            "short_label": r.name[:18],
            "icon_url": r.display_icon.url if getattr(r, "display_icon", None) else "",
        }
        for r in tracked_roles[:8]
    ]

    tracked_role_ids = {r.id for r in tracked_roles}
    staff_list = []
    for member in guild.members:
        if member.bot:
            continue
        m_roles = [r for r in sorted(member.roles, key=lambda x: x.position, reverse=True) if r.id in tracked_role_ids]
        if not m_roles:
            continue
        top_color = str(m_roles[0].color) if m_roles[0].color.value else "#e879f9"
        staff_list.append({
            "id": str(member.id),
            "display_name": member.display_name,
            "username": member.name,
            "avatar_url": member.display_avatar.url,
            "banner_url": member.banner.url if getattr(member, "banner", None) else "",
            "avatar_decoration_url": member.avatar_decoration.url if getattr(member, "avatar_decoration", None) else "",
            "status": str(member.status),
            "role_color": top_color,
            "roles": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "color": str(r.color) if r.color.value else "#f59e0b",
                    "icon_url": r.display_icon.url if getattr(r, "display_icon", None) else "",
                }
                for r in m_roles
            ],
        })

    showcase_cache["staff_members"] = staff_list
    showcase_cache["last_synced"] = datetime.datetime.now().strftime("%I:%M:%S %p")


async def periodic_sync_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            sync_discord_data_to_cache()
        except Exception as exc:
            print(f"[Sync Loop Error] {exc}")
        await asyncio.sleep(12)


@bot.event
async def on_ready():
    print(f"[VortexShop Bot] Logged in as {bot.user} (ID: {bot.user.id})")
    sync_discord_data_to_cache()
    bot.loop.create_task(periodic_sync_loop())


@bot.command(name="syncshop")
@commands.has_permissions(manage_guild=True)
async def cmd_syncshop(ctx):
    sync_discord_data_to_cache()
    await ctx.send("✅ VortexShop website showcase synced with latest Discord roles, members & counts.")


def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"[VortexShop Web] Serving {HTML_FILE} on http://0.0.0.0:{PORT} | DB: {os.path.abspath(DB_PATH)}")

    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("[Warning] DISCORD_TOKEN not set. Running web storefront & Shop API in standalone mode.")
        while True:
            time.sleep(60)
