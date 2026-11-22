import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import discord
from aiohttp import web
from discord.ext import commands

# ==============================================================================
# CONFIGURATION (Set these in Render Environment Variables)
# ==============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "1542941315933667348"))
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "1540575139538796634"))
INVITE_URL = os.getenv("INVITE_URL", "https://discord.gg/3JPatMmyF")
STORE_URL = os.getenv("STORE_URL", "https://vortexshop.onrender.com")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vortex-admin-2026")
PORT = int(os.getenv("PORT", "10000"))

HTML_PATH = Path(os.getenv("HTML_PATH", "index.html"))
DB_PATH = Path(os.getenv("DB_PATH", "vortexshop.db"))

# Tracked Role IDs referenced in your showcase
TRACKED_ROLES = [
    {
        "id": "1568386943945801839",
        "label": "Founder / Owner",
        "short_label": "Owner",
        "icon_url": "",
    },
    {
        "id": "1568387066709024788",
        "label": "Head Middleman",
        "short_label": "Head MM",
        "icon_url": "",
    },
    {
        "id": "1568387138322694268",
        "label": "Trusted Middleman",
        "short_label": "Trusted MM",
        "icon_url": "",
    },
    {
        "id": "1568387457752371270",
        "label": "Staff / Moderator",
        "short_label": "Staff",
        "icon_url": "",
    },
]
TRACKED_ROLE_IDS = {int(r["id"]) for r in TRACKED_ROLES}

# ==============================================================================
# DISCORD BOT SETUP
# ==============================================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)
user_profile_cache: dict[int, dict[str, Any]] = {}


def is_admin_authorized(request: web.Request) -> bool:
    provided = request.headers.get("X-Admin-Password", "")
    return bool(ADMIN_PASSWORD) and provided == ADMIN_PASSWORD


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                stock INTEGER NOT NULL DEFAULT 1,
                price REAL NOT NULL DEFAULT 0.0,
                currency TEXT NOT NULL DEFAULT 'USD',
                description TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                remaining_stock INTEGER NOT NULL,
                sold_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def list_shop_items() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, category, stock, price, currency, description, image_url, created_at FROM shop_items ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def list_recent_sales(limit: int = 20) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, item_id, item_name, category, price, currency, remaining_stock, sold_at FROM sales_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def send_sold_webhook(item: dict[str, Any], remaining_stock: int) -> bool:
    if not WEBHOOK_URL:
        return False

    stock_label = "OUT OF STOCK (0 left)" if remaining_stock <= 0 else f"{remaining_stock} left in stock"
    price_str = f"{float(item['price']):.2f} {item['currency']}"
    payload = {
        "username": "VortexShop Stock & Sales",
        "embeds": [
            {
                "title": "💸 Item Marked Sold (-1)",
                "color": 0xF59E0B if remaining_stock > 0 else 0xEF4444,
                "fields": [
                    {"name": "Item", "value": str(item["name"]), "inline": True},
                    {"name": "Category", "value": str(item["category"]), "inline": True},
                    {"name": "Price", "value": price_str, "inline": True},
                    {"name": "Remaining Stock", "value": stock_label, "inline": False},
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBHOOK_URL, json=payload, timeout=10) as resp:
                return 200 <= resp.status < 300
    except Exception as exc:
        print(f"[WEBHOOK] Failed to send sold notification: {exc}")
        return False


def status_to_str(status: discord.Status | None) -> str:
    if status == discord.Status.online:
        return "online"
    if status == discord.Status.idle:
        return "idle"
    if status == discord.Status.dnd:
        return "dnd"
    return "offline"


def extract_custom_status(member: discord.Member | None) -> dict[str, str]:
    if not member or not member.activities:
        return {"emoji": "", "text": "Very nice day"}
    for act in member.activities:
        if isinstance(act, discord.CustomActivity):
            emoji_str = str(act.emoji) if act.emoji else ""
            return {"emoji": emoji_str, "text": act.name or ""}
    return {"emoji": "", "text": "Very nice day"}


async def get_enriched_user_data(user_id: int) -> dict[str, Any]:
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = user_profile_cache.get(user_id)
    if cached and (now_ts - cached["fetched_at"] < 120):
        return cached["data"]

    data: dict[str, Any] = {
        "banner_url": "",
        "avatar_url": "",
        "avatar_decoration_url": "",
        "display_name": "",
        "username": "",
        "created_at": "Aug 22, 2026",
    }
    try:
        user = await bot.fetch_user(user_id)
        data["banner_url"] = user.banner.url if user.banner else ""
        data["avatar_url"] = user.display_avatar.url if user.display_avatar else ""
        deco = getattr(user, "avatar_decoration", None)
        data["avatar_decoration_url"] = deco.url if deco else ""
        data["display_name"] = user.global_name or user.name
        data["username"] = user.name
        if user.created_at:
            data["created_at"] = user.created_at.strftime("%b %d, %Y")
    except Exception:
        pass

    user_profile_cache[user_id] = {"fetched_at": now_ts, "data": data}
    return data


def build_default_vouches() -> list[dict[str, Any]]:
    return [
        {
            "name": "TrustedTrader_PH",
            "trade_tag": "Verified Ticket Trade",
            "stars": 5,
            "avatar_url": "",
            "note": "Super fast MM service, zero hassle and smooth handoff inside ticket.",
        },
        {
            "name": "KiroVFX",
            "trade_tag": "Verified Ticket Trade",
            "stars": 5,
            "avatar_url": "",
            "note": "Legit middleman and active staff. Vouching 100%!",
        },
        {
            "name": "ZyroBlox",
            "trade_tag": "Verified Ticket Trade",
            "stars": 5,
            "avatar_url": "",
            "note": "Verified ID in ticket first and finished the trade in under 3 minutes.",
        },
    ]


def build_mm_rules() -> list[str]:
    return [
        "Always open an official Middleman ticket inside Vortex Exchange & MM before trading.",
        "Verify the Middleman's exact Discord User ID and staff role inside the ticket channel.",
        "Never trust DMs from lookalike accounts or off-server 'middlemen'.",
        "Confirm both sides' exact items, quantities, and tax/fee terms in chat prior to handoff.",
        "Record your trade screen from start to finish and leave a vouch once completed.",
    ]


async def build_showcase_payload() -> dict[str, Any]:
    guild = bot.get_guild(GUILD_ID)

    server_data: dict[str, Any] = {
        "id": str(GUILD_ID),
        "name": "Vortex Exchange & MM",
        "invite_url": INVITE_URL,
        "member_count": 0,
        "online_count": 0,
        "offline_count": 0,
        "boost_count": 0,
        "icon_url": "",
        "banner_url": "",
    }

    owner_member: discord.Member | None = None
    staff_members_list: list[dict[str, Any]] = []

    if guild:
        total_members = guild.member_count or len(guild.members)
        online_members = sum(
            1
            for m in guild.members
            if not m.bot and m.status in (discord.Status.online, discord.Status.idle, discord.Status.dnd)
        )
        offline_members = max(0, total_members - online_members)

        server_data.update(
            {
                "name": guild.name,
                "member_count": total_members,
                "online_count": online_members,
                "offline_count": offline_members,
                "boost_count": guild.premium_subscription_count or 0,
                "icon_url": guild.icon.url if guild.icon else "",
                "banner_url": guild.banner.url if guild.banner else "",
            }
        )

        owner_member = guild.get_member(OWNER_USER_ID)

        for member in guild.members:
            if member.bot:
                continue
            matched_roles = [r for r in member.roles if r.id in TRACKED_ROLE_IDS]
            if not matched_roles:
                continue

            matched_roles.sort(key=lambda r: r.position, reverse=True)
            enriched = await get_enriched_user_data(member.id)
            deco = getattr(member, "avatar_decoration", None)

            staff_members_list.append(
                {
                    "id": str(member.id),
                    "display_name": member.display_name,
                    "username": member.name,
                    "status": status_to_str(member.status),
                    "avatar_url": member.display_avatar.url if member.display_avatar else enriched["avatar_url"],
                    "banner_url": enriched["banner_url"],
                    "avatar_decoration_url": deco.url if deco else enriched["avatar_decoration_url"],
                    "profile_effect": {
                        "source": "VortexShop Showcase",
                        "name": "Cosmic Shimmer",
                        "asset_url": "",
                    },
                    "roles": [
                        {
                            "id": str(r.id),
                            "role_key": str(r.id),
                            "name": r.name,
                            "icon_url": r.icon.url if r.icon else "",
                        }
                        for r in matched_roles
                    ],
                }
            )

    status_rank = {"online": 0, "idle": 1, "dnd": 2, "offline": 3}
    staff_members_list.sort(key=lambda m: (status_rank.get(m["status"], 3), m["display_name"].lower()))

    owner_enriched = await get_enriched_user_data(OWNER_USER_ID)
    owner_deco = getattr(owner_member, "avatar_decoration", None) if owner_member else None

    profile_data = {
        "id": str(OWNER_USER_ID),
        "display_name": (owner_member.display_name if owner_member else owner_enriched["display_name"]) or "VortexShop",
        "username": (owner_member.name if owner_member else owner_enriched["username"]) or "mvn412.",
        "status": status_to_str(owner_member.status) if owner_member else "online",
        "custom_status": extract_custom_status(owner_member),
        "avatar_url": (
            owner_member.display_avatar.url
            if owner_member and owner_member.display_avatar
            else owner_enriched["avatar_url"] or "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
        "banner_url": owner_enriched["banner_url"],
        "banner_position": "center",
        "avatar_decoration_url": owner_deco.url if owner_deco else owner_enriched["avatar_decoration_url"],
        "profile_effect": {
            "source": "VortexShop",
            "name": "Nebula Sweep",
            "asset_url": "",
        },
        "bio_link_text": "Check out vortexshop.onrender.com",
        "store_url": STORE_URL,
        "clan_badge_url": "",
        "clan_emoji": "🍃",
        "clan_tag": "VEM",
        "mutual_servers_count": 4,
        "vouches_count": 120,
        "role_badge_icon_url": "",
        "role_badge_text": "Founder • VortexShop",
        "owner_line": "Owner of this server-",
        "invite_url": INVITE_URL,
        "full_bio": "Founder of Vortex Exchange & MM. Safe crosstrading, verified middleman tickets, and live shop stock.",
        "member_since": owner_enriched["created_at"] or "Aug 22, 2026",
        "custom_trade_note": "Browse live items in the Shop page and open an official ticket inside Vortex Exchange & MM to complete your order.",
        "badges": [
            {"id": "founder", "label": "Server Founder", "fallback_icon": "👑"},
            {"id": "verified_mm", "label": "Verified Middleman", "fallback_icon": "🛡️"},
            {"id": "booster", "label": "Nitro & Server Booster", "fallback_icon": "💎"},
        ],
        "games": [],
        "vouches": build_default_vouches(),
        "mm_rules": build_mm_rules(),
    }

    now_label = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return {
        "last_synced": now_label,
        "profile": profile_data,
        "server": server_data,
        "role_catalog": TRACKED_ROLES,
        "staff_members": staff_members_list,
    }


# ==============================================================================
# AIOHTTP WEB & ADMIN/SHOP API ROUTES
# ==============================================================================
async def handle_index(request: web.Request) -> web.Response:
    if HTML_PATH.exists():
        return web.FileResponse(HTML_PATH)
    return web.Response(
        text="HTML file not found. Place your HTML file at index.html or set HTML_PATH.",
        status=404,
    )


async def handle_showcase_api(request: web.Request) -> web.Response:
    payload = await build_showcase_payload()
    return web.json_response(payload)


async def handle_get_shop(request: web.Request) -> web.Response:
    items = await list_shop_items()
    include_sales = is_admin_authorized(request)
    sales = await list_recent_sales(25) if include_sales else []
    return web.json_response({"items": items, "sales": sales})


async def handle_admin_login(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    pw = str(body.get("password", ""))
    if not ADMIN_PASSWORD or pw != ADMIN_PASSWORD:
        return web.json_response({"ok": False, "error": "Invalid admin password."}, status=401)

    items = await list_shop_items()
    sales = await list_recent_sales(25)
    return web.json_response({"ok": True, "items": items, "sales": sales})


async def handle_create_shop_item(request: web.Request) -> web.Response:
    if not is_admin_authorized(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    name = str(body.get("name", "")).strip()
    category = str(body.get("category", "General")).strip() or "General"
    currency = str(body.get("currency", "USD")).strip() or "USD"
    description = str(body.get("description", "")).strip()
    image_url = str(body.get("image_url", "")).strip()

    if not name:
        return web.json_response({"error": "Item name is required."}, status=400)

    try:
        stock = max(0, int(body.get("stock", 1)))
    except (ValueError, TypeError):
        stock = 1

    try:
        price = max(0.0, float(body.get("price", 0.0)))
    except (ValueError, TypeError):
        price = 0.0

    item_id = f"item-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO shop_items (id, name, category, stock, price, currency, description, image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, name, category, stock, price, currency, description, image_url, created_at),
        )
        await db.commit()

    items = await list_shop_items()
    created = next((i for i in items if i["id"] == item_id), None)
    return web.json_response({"ok": True, "item": created, "items": items}, status=201)


async def handle_update_shop_item(request: web.Request) -> web.Response:
    if not is_admin_authorized(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    item_id = request.match_info["item_id"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return web.json_response({"error": "Item not found"}, status=404)

        current = dict(row)
        name = str(body.get("name", current["name"])).strip() or current["name"]
        category = str(body.get("category", current["category"])).strip() or current["category"]
        currency = str(body.get("currency", current["currency"])).strip() or current["currency"]
        description = str(body.get("description", current["description"])).strip()
        image_url = str(body.get("image_url", current["image_url"])).strip()

        try:
            stock = max(0, int(body.get("stock", current["stock"])))
        except (ValueError, TypeError):
            stock = current["stock"]

        try:
            price = max(0.0, float(body.get("price", current["price"])))
        except (ValueError, TypeError):
            price = current["price"]

        await db.execute(
            """
            UPDATE shop_items
            SET name = ?, category = ?, stock = ?, price = ?, currency = ?, description = ?, image_url = ?
            WHERE id = ?
            """,
            (name, category, stock, price, currency, description, image_url, item_id),
        )
        await db.commit()

    items = await list_shop_items()
    sales = await list_recent_sales(25)
    return web.json_response({"ok": True, "items": items, "sales": sales})


async def handle_minus_one_sold(request: web.Request) -> web.Response:
    if not is_admin_authorized(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    item_id = request.match_info["item_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return web.json_response({"error": "Item not found"}, status=404)

        item = dict(row)
        current_stock = int(item["stock"])
        if current_stock <= 0:
            return web.json_response({"error": "Item is already out of stock."}, status=400)

        new_stock = current_stock - 1
        sold_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        await db.execute("UPDATE shop_items SET stock = ? WHERE id = ?", (new_stock, item_id))
        await db.execute(
            """
            INSERT INTO sales_log (item_id, item_name, category, price, currency, remaining_stock, sold_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["category"],
                float(item["price"]),
                item["currency"],
                new_stock,
                sold_at,
            ),
        )
        await db.commit()

    webhook_sent = await send_sold_webhook(item, new_stock)
    items = await list_shop_items()
    sales = await list_recent_sales(25)
    return web.json_response(
        {
            "ok": True,
            "webhook_sent": webhook_sent,
            "remaining_stock": new_stock,
            "items": items,
            "sales": sales,
        }
    )


async def handle_delete_shop_item(request: web.Request) -> web.Response:
    if not is_admin_authorized(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    item_id = request.match_info["item_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM shop_items WHERE id = ?", (item_id,))
        await db.commit()

    items = await list_shop_items()
    sales = await list_recent_sales(25)
    return web.json_response({"ok": True, "items": items, "sales": sales})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "bot_ready": bot.is_ready()})


@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")


async def start_services():
    await init_db()

    app = web.Application(client_max_size=6 * 1024 * 1024)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/showcase", handle_showcase_api)
    app.router.add_get("/api/shop", handle_get_shop)
    app.router.add_post("/api/admin/login", handle_admin_login)
    app.router.add_post("/api/shop/items", handle_create_shop_item)
    app.router.add_put("/api/shop/items/{item_id}", handle_update_shop_item)
    app.router.add_post("/api/shop/items/{item_id}/minus-one", handle_minus_one_sold)
    app.router.add_delete("/api/shop/items/{item_id}", handle_delete_shop_item)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    print(f"[WEB] Serving showcase & SQLite shop on http://0.0.0.0:{PORT}")

    if DISCORD_TOKEN:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    else:
        print("[WARN] DISCORD_TOKEN not set — running web server in fallback mode.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start_services())
