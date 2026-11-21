import os
import json
import time
import asyncio
import datetime
import threading
import urllib.request
import urllib.error
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

# Webhooks for Shop & Ticket Logs (Optional - set in env vars)
WEBHOOK_ITEM_ADDED = os.getenv("WEBHOOK_ITEM_ADDED", "").strip()
WEBHOOK_ITEM_SOLD = os.getenv("WEBHOOK_ITEM_SOLD", "").strip()
WEBHOOK_TICKET_CLOSED = os.getenv("WEBHOOK_TICKET_CLOSED", "").strip()

STATE_FILE = "vortex_state.json"
HTML_FILE = "index-v2.html"

# =========================================================
# PERSISTENT JSON STATE (Shop Items & Closed Tickets)
# =========================================================
DEFAULT_STATE = {
    "items": [],
    "closed_tickets": [],
}

state_lock = threading.Lock()


def load_state():
    if not os.path.exists(STATE_FILE):
        save_state(DEFAULT_STATE)
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "items" not in data:
                data["items"] = DEFAULT_STATE["items"]
            if "closed_tickets" not in data:
                data["closed_tickets"] = []
            return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


store_state = load_state()

# Live Discord Showcase Cache updated by background bot task
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
        "footer": {"text": "VortexShop Live Sync"},
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
    return jsonify({"status": "ok", "service": "VortexShop", "bot_ready": bot.is_ready()})


@app.route("/api/showcase", methods=["GET"])
def api_showcase():
    return jsonify(showcase_cache)


@app.route("/api/state", methods=["GET"])
def api_state():
    with state_lock:
        return jsonify(store_state)


@app.route("/api/shop/items", methods=["POST"])
def api_add_shop_item():
    data = request.get_json(silent=True) or {}
    if data.get("admin_password") != ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin password."}), 403

    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "General")).strip()
    if not name:
        return jsonify({"ok": False, "error": "Item name is required."}), 400

    stock = max(1, int(data.get("stock", 1)))
    price = str(data.get("price", "0.00")).strip()
    currency = str(data.get("currency", "USD")).strip().upper()
    posted_by = str(data.get("posted_by", "@mvn412.")).strip()
    if not posted_by.startswith("@"):
        posted_by = f"@{posted_by}"
    description = str(data.get("description", "")).strip()
    image_url = str(data.get("image_url", "")).strip()

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
        "status": "AVAILABLE",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    with state_lock:
        store_state["items"].insert(0, item)
        save_state(store_state)

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


@app.route("/api/shop/items/<item_id>/sold", methods=["POST"])
def api_mark_item_sold(item_id):
    data = request.get_json(silent=True) or {}
    buyer = str(data.get("buyer", "@buyer")).strip()

    updated_item = None
    with state_lock:
        for it in store_state["items"]:
            if it.get("id") == item_id:
                next_stock = max(0, int(it.get("stock", 1)) - 1)
                it["stock"] = next_stock
                it["status"] = "SOLD" if next_stock <= 0 else "AVAILABLE"
                updated_item = dict(it)
                break
        if updated_item:
            save_state(store_state)

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


@app.route("/api/tickets/closed", methods=["POST"])
def api_ticket_closed():
    rec = request.get_json(silent=True) or {}
    if not rec.get("ticket_id"):
        rec["ticket_id"] = f"VX-{int(time.time()) % 10000}"
    rec["status"] = "CLOSED"
    rec["synced_to_website"] = True
    rec.setdefault("closed_at", datetime.datetime.now(datetime.timezone.utc).isoformat())

    with state_lock:
        store_state["closed_tickets"].insert(0, rec)
        store_state["closed_tickets"] = store_state["closed_tickets"][:50]
        save_state(store_state)

    t1 = rec.get("trader_1", {})
    t2 = rec.get("trader_2", {})
    threading.Thread(
        target=post_discord_webhook,
        args=(
            WEBHOOK_TICKET_CLOSED,
            f"🔒 Closed Trade Ticket: {rec['ticket_id']}",
            [
                {"name": "Game / Category", "value": f"{rec.get('game', 'N/A')} ({rec.get('ticket_type', 'Escrow')})", "inline": True},
                {"name": "Claimed By", "value": rec.get("claimed_by", "@staff"), "inline": True},
                {"name": f"Trader 1: {t1.get('name', 'Trader 1')}", "value": f"Gave: {t1.get('giving_items', '-')}", "inline": False},
                {"name": f"Trader 2: {t2.get('name', 'Trader 2')}", "value": f"Gave: {t2.get('giving_items', '-')}", "inline": False},
            ],
            0xA855F7,
        ),
        daemon=True,
    ).start()

    return jsonify({"ok": True, "ticket": rec})


# =========================================================
# DISCORD BOT (Live Guild & Staff Sync + Slash/Prefix Cmds)
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

    # Track non-bot members with elevated / staff / MM roles
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
    print(f"[VortexShop Web] Serving {HTML_FILE} on http://0.0.0.0:{PORT}")

    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("[Warning] DISCORD_TOKEN not set. Running web storefront & Shop API in standalone mode.")
        while True:
            time.sleep(60)
