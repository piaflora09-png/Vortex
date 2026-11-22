import asyncio
import base64
from io import BytesIO
import json
import os
import re
import uuid
from datetime import datetime, timezone

import aiohttp
import aiosqlite
import discord
from aiohttp import web

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()

GUILD_ID = int(os.getenv("GUILD_ID", "1542941315933667348"))
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "1540575139538796634"))
INVITE_URL = os.getenv("INVITE_URL", "https://discord.gg/3JPatMmyF").strip()
STORE_URL = os.getenv("STORE_URL", "https://vortexshop.onrender.com").strip()
DB_PATH = os.getenv("DB_PATH", "vortexshop.db").strip()
PORT = int(os.getenv("PORT", "10000"))

TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0") or "0")
TICKET_STAFF_ROLE_ID = int(os.getenv("TICKET_STAFF_ROLE_ID", "0") or "0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.guilds = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _now_short() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _slugify_channel_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:24] or "buyer"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                stock INTEGER NOT NULL DEFAULT 0,
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
                id TEXT PRIMARY KEY,
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
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_orders (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                buyer_discord TEXT NOT NULL,
                buyer_notes TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL DEFAULT '',
                channel_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def get_all_items() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_items ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_recent_sales(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sales_log ORDER BY sold_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_recent_tickets(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ticket_orders ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def send_sold_webhook(sale: dict) -> None:
    if not WEBHOOK_URL:
        return
    embed = {
        "title": "Item Marked Sold (-1)",
        "color": 0xF59E0B,
        "fields": [
            {"name": "Item", "value": str(sale["item_name"]), "inline": True},
            {"name": "Category", "value": str(sale["category"]), "inline": True},
            {
                "name": "Price",
                "value": f"{float(sale['price']):.2f} {sale['currency']}",
                "inline": True,
            },
            {
                "name": "Remaining Stock",
                "value": str(sale["remaining_stock"]),
                "inline": True,
            },
            {"name": "Sold At", "value": str(sale["sold_at"]), "inline": False},
        ],
    }
    payload = {"content": None, "embeds": [embed]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    print(f"[Webhook] Discord returned {resp.status}: {body}")
    except Exception as exc:
        print(f"[Webhook] Failed to send webhook: {exc}")


class CloseTicketView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="vortex_close_ticket_btn",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This button only works inside a ticket channel.", ephemeral=True
            )
            return
        await interaction.response.send_message("Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await channel.delete(reason=f"Closed by {interaction.user}")
        except Exception as exc:
            print(f"[Ticket] Failed to delete channel: {exc}")


def _resolve_buyer_member(
    guild: discord.Guild, buyer_input: str
) -> discord.Member | None:
    raw = buyer_input.strip()
    digits = re.sub(r"\D", "", raw)
    if digits.isdigit():
        member = guild.get_member(int(digits))
        if member:
            return member

    lowered = raw.lstrip("@").lower()
    for m in guild.members:
        if m.name.lower() == lowered or (
            m.global_name and m.global_name.lower() == lowered
        ):
            return m
    return None


def _build_image_file(image_url: str) -> discord.File | None:
    if not image_url or not image_url.startswith("data:image/"):
        return None
    try:
        header, b64_data = image_url.split(",", 1)
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "webp" in header:
            ext = "webp"
        elif "gif" in header:
            ext = "gif"
        raw_bytes = base64.b64decode(b64_data)
        return discord.File(BytesIO(raw_bytes), filename=f"item_preview.{ext}")
    except Exception as exc:
        print(f"[Ticket] Failed decoding image data URL: {exc}")
        return None


async def create_order_ticket_channel(order: dict) -> tuple[str, str]:
    if not bot.is_ready():
        return "", ""

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return "", ""

    category: discord.CategoryChannel | None = None
    if TICKET_CATEGORY_ID:
        cat_obj = guild.get_channel(TICKET_CATEGORY_ID)
        if isinstance(cat_obj, discord.CategoryChannel):
            category = cat_obj

    if category is None:
        for c in guild.categories:
            if c.name.lower() in ("tickets", "orders", "vortex tickets"):
                category = c
                break

    buyer_member = _resolve_buyer_member(guild, order["buyer_discord"])
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            embed_links=True,
            attach_files=True,
        ),
    }

    if buyer_member is not None:
        overwrites[buyer_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        )

    if TICKET_STAFF_ROLE_ID:
        staff_role = guild.get_role(TICKET_STAFF_ROLE_ID)
        if staff_role is not None:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            )

    owner_member = guild.get_member(OWNER_USER_ID)
    if owner_member is not None:
        overwrites[owner_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        )

    slug = _slugify_channel_name(order["buyer_discord"])
    short_id = order["id"][:6]
    channel_name = f"ticket-{slug}-{short_id}"[:95]

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Shop ticket order {order['id']} for {order['buyer_discord']}",
        )
    except Exception as exc:
        print(f"[Ticket] Error creating ticket channel: {exc}")
        return "", ""

    desc_text = (order.get("description") or "").strip() or "No description provided."
    if order.get("buyer_notes"):
        desc_text = f"{desc_text}\n\n**Buyer Note:** {order['buyer_notes'].strip()}"

    embed = discord.Embed(
        title=f"New Order Ticket — {order['item_name']}",
        description=desc_text,
        color=0x8B5CF6,
    )
    embed.add_field(
        name="Buyer Discord", value=str(order["buyer_discord"]), inline=True
    )
    embed.add_field(name="Item", value=str(order["item_name"]), inline=True)
    embed.add_field(name="Category", value=str(order["category"]), inline=True)
    embed.add_field(
        name="Price",
        value=f"{float(order['price']):.2f} {order['currency']}",
        inline=True,
    )
    embed.add_field(name="Order ID", value=f"`{order['id']}`", inline=True)
    embed.set_footer(text="VortexShop Live Ticket System")

    file_obj = _build_image_file(order.get("image_url", ""))
    mention_text = (
        buyer_member.mention if buyer_member else f"**{order['buyer_discord']}**"
    )
    if file_obj is not None:
        embed.set_image(url=f"attachment://{file_obj.filename}")
        await channel.send(
            content=f"{mention_text} — Ticket opened for your order.",
            embed=embed,
            file=file_obj,
            view=CloseTicketView(),
        )
    else:
        if order.get("image_url") and order["image_url"].startswith(
            ("http://", "https://")
        ):
            embed.set_image(url=order["image_url"])
        await channel.send(
            content=f"{mention_text} — Ticket opened for your order.",
            embed=embed,
            view=CloseTicketView(),
        )

    return str(channel.id), channel.name


def _map_status(status: discord.Status | None) -> str:
    if status == discord.Status.online:
        return "online"
    if status == discord.Status.idle:
        return "idle"
    if status in (discord.Status.dnd, discord.Status.do_not_disturb):
        return "dnd"
    return "offline"


def build_showcase_payload() -> dict:
    guild = bot.get_guild(GUILD_ID)
    server_info = {
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
    role_catalog: list[dict] = []
    staff_members: list[dict] = []

    if guild is not None:
        server_info["name"] = guild.name
        server_info["member_count"] = guild.member_count or len(guild.members)
        server_info["boost_count"] = guild.premium_subscription_count or 0
        if guild.icon:
            server_info["icon_url"] = guild.icon.url
        if guild.banner:
            server_info["banner_url"] = guild.banner.url

        online_cnt = 0
        for m in guild.members:
            if not m.bot and m.status != discord.Status.offline:
                online_cnt += 1
        server_info["online_count"] = online_cnt
        server_info["offline_count"] = max(
            0, server_info["member_count"] - online_cnt
        )

        owner_member = guild.get_member(OWNER_USER_ID)

        for r in reversed(guild.roles):
            if r.is_default() or r.managed:
                continue
            if len(r.members) > 0:
                role_catalog.append(
                    {
                        "id": str(r.id),
                        "role_key": str(r.id),
                        "label": r.name,
                        "short_label": r.name,
                    }
                )

        tracked_role_ids = {item["id"] for item in role_catalog}
        for m in guild.members:
            if m.bot:
                continue
            m_roles = [
                {"id": str(r.id), "role_key": str(r.id), "name": r.name}
                for r in reversed(m.roles)
                if not r.is_default() and str(r.id) in tracked_role_ids
            ]
            if m_roles:
                staff_members.append(
                    {
                        "id": str(m.id),
                        "username": m.name,
                        "display_name": m.display_name,
                        "avatar_url": m.display_avatar.url,
                        "banner_url": m.banner.url if m.banner else "",
                        "status": _map_status(m.status),
                        "roles": m_roles,
                    }
                )

    owner_user = owner_member or bot.get_user(OWNER_USER_ID)
    custom_emoji = ""
    custom_text = "Very nice day"
    if owner_member and owner_member.activities:
        for act in owner_member.activities:
            if isinstance(act, discord.CustomActivity):
                if act.emoji:
                    custom_emoji = str(act.emoji)
                if act.name:
                    custom_text = act.name
                break

    profile_info = {
        "id": str(OWNER_USER_ID),
        "username": owner_user.name if owner_user else "mvn412.",
        "display_name": (
            owner_member.display_name
            if owner_member
            else (owner_user.display_name if owner_user else "VortexShop")
        ),
        "avatar_url": (
            owner_user.display_avatar.url
            if owner_user
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
        "banner_url": (
            owner_user.banner.url
            if (owner_user and owner_user.banner)
            else ""
        ),
        "avatar_decoration_url": (
            owner_user.avatar_decoration.url
            if (owner_user and owner_user.avatar_decoration)
            else ""
        ),
        "status": _map_status(owner_member.status) if owner_member else "online",
        "custom_status": {"emoji": custom_emoji, "text": custom_text},
        "store_url": STORE_URL,
        "bio_link_text": f"Check out {STORE_URL.replace('https://', '').replace('http://', '')}",
        "clan_emoji": "🍃",
        "clan_tag": "VEM",
        "role_badge_text": "Founder • VortexShop",
        "owner_line": "Owner of this server-",
        "invite_url": INVITE_URL,
        "full_bio": "Official VortexShop & Vortex Exchange & MM hub. Always open a verified ticket inside the server before trading.",
        "member_since": (
            owner_member.joined_at.strftime("%b %d, %Y")
            if (owner_member and owner_member.joined_at)
            else "Aug 22, 2026"
        ),
        "mutual_servers_count": len(bot.guilds),
        "vouches_count": 120,
        "badges": [
            {"id": "verified", "label": "Verified Hub", "fallback_icon": "✦"},
            {"id": "mm", "label": "Verified Middleman", "fallback_icon": "🛡️"},
            {"id": "fast", "label": "Fast Ticket Support", "fallback_icon": "⚡"},
            {"id": "vouched", "label": "Trusted Vouches", "fallback_icon": "★"},
        ],
        "mm_rules": [
            "Open an official ticket inside Vortex Exchange & MM before any trade.",
            "Double-check the Middleman's Discord User ID directly in the ticket.",
            "Never accept DMs claiming to be staff outside an open server ticket.",
            "Confirm all item names, quantities, and terms before handing over items.",
        ],
    }

    return {
        "last_synced": _now_short(),
        "profile": profile_info,
        "server": server_info,
        "role_catalog": role_catalog,
        "staff_members": staff_members,
    }


def _check_admin_password(request: web.Request, body: dict | None = None) -> bool:
    if not ADMIN_PASSWORD:
        return False
    header_pw = request.headers.get("X-Admin-Password", "")
    body_pw = (body or {}).get("password", "") if isinstance(body, dict) else ""
    return header_pw == ADMIN_PASSWORD or body_pw == ADMIN_PASSWORD


async def handle_index(request: web.Request) -> web.Response:
    if not os.path.exists(INDEX_HTML_PATH):
        return web.Response(text="index.html not found.", status=404)
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    return web.Response(text=html, content_type="text/html")


async def handle_api_showcase(request: web.Request) -> web.Response:
    return web.json_response(build_showcase_payload())


async def handle_api_shop(request: web.Request) -> web.Response:
    items = await get_all_items()
    data: dict = {"ok": True, "items": items}
    if _check_admin_password(request):
        data["sales"] = await get_recent_sales()
        data["tickets"] = await get_recent_tickets()
    return web.json_response(data)


async def handle_admin_login(request: web.Request) -> web.Response:
    if not ADMIN_PASSWORD:
        return web.json_response(
            {"ok": False, "error": "ADMIN_PASSWORD is not set in environment variables."},
            status=500,
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    pw = str((body or {}).get("password", ""))
    if pw != ADMIN_PASSWORD:
        return web.json_response(
            {"ok": False, "error": "Incorrect password."},
            status=401,
        )
    items = await get_all_items()
    sales = await get_recent_sales()
    tickets = await get_recent_tickets()
    return web.json_response(
        {"ok": True, "items": items, "sales": sales, "tickets": tickets}
    )


async def handle_create_item(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON."}, status=400)
    if not _check_admin_password(request, body):
        return web.json_response({"ok": False, "error": "Unauthorized."}, status=401)

    name = str(body.get("name", "")).strip()
    if not name:
        return web.json_response({"ok": False, "error": "Item name is required."}, status=400)

    category = str(body.get("category", "General")).strip() or "General"
    stock = max(0, int(body.get("stock", 0) or 0))
    price = max(0.0, float(body.get("price", 0.0) or 0.0))
    currency = str(body.get("currency", "USD")).strip() or "USD"
    description = str(body.get("description", "")).strip()
    image_url = str(body.get("image_url", "")).strip()

    item_id = str(uuid.uuid4())
    created_at = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO shop_items
                (id, name, category, stock, price, currency, description, image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                name,
                category,
                stock,
                price,
                currency,
                description,
                image_url,
                created_at,
            ),
        )
        await db.commit()

    items = await get_all_items()
    sales = await get_recent_sales()
    return web.json_response({"ok": True, "id": item_id, "items": items, "sales": sales})


async def handle_update_item(request: web.Request) -> web.Response:
    item_id = request.match_info["item_id"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON."}, status=400)
    if not _check_admin_password(request, body):
        return web.json_response({"ok": False, "error": "Unauthorized."}, status=401)

    name = str(body.get("name", "")).strip()
    if not name:
        return web.json_response({"ok": False, "error": "Item name is required."}, status=400)

    category = str(body.get("category", "General")).strip() or "General"
    stock = max(0, int(body.get("stock", 0) or 0))
    price = max(0.0, float(body.get("price", 0.0) or 0.0))
    currency = str(body.get("currency", "USD")).strip() or "USD"
    description = str(body.get("description", "")).strip()
    image_url = str(body.get("image_url", "")).strip()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE shop_items
            SET name = ?, category = ?, stock = ?, price = ?, currency = ?, description = ?, image_url = ?
            WHERE id = ?
            """,
            (name, category, stock, price, currency, description, image_url, item_id),
        )
        await db.commit()
        if cur.rowcount == 0:
            return web.json_response({"ok": False, "error": "Item not found."}, status=404)

    items = await get_all_items()
    sales = await get_recent_sales()
    return web.json_response({"ok": True, "items": items, "sales": sales})


async def handle_minus_one_sold(request: web.Request) -> web.Response:
    item_id = request.match_info["item_id"]
    if not _check_admin_password(request):
        return web.json_response({"ok": False, "error": "Unauthorized."}, status=401)

    sold_record: dict | None = None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_items WHERE id = ?", (item_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return web.json_response({"ok": False, "error": "Item not found."}, status=404)
            item = dict(row)

        current_stock = int(item["stock"])
        if current_stock <= 0:
            return web.json_response(
                {"ok": False, "error": "Stock is already 0."}, status=400
            )

        new_stock = current_stock - 1
        sold_at = _now_iso()
        sale_id = str(uuid.uuid4())

        await db.execute(
            "UPDATE shop_items SET stock = ? WHERE id = ?",
            (new_stock, item_id),
        )
        await db.execute(
            """
            INSERT INTO sales_log
                (id, item_id, item_name, category, price, currency, remaining_stock, sold_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_id,
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

        sold_record = {
            "id": sale_id,
            "item_id": item["id"],
            "item_name": item["name"],
            "category": item["category"],
            "price": float(item["price"]),
            "currency": item["currency"],
            "remaining_stock": new_stock,
            "sold_at": sold_at,
        }

    if sold_record is not None:
        await send_sold_webhook(sold_record)

    items = await get_all_items()
    sales = await get_recent_sales()
    return web.json_response(
        {"ok": True, "sale": sold_record, "items": items, "sales": sales}
    )


async def handle_delete_item(request: web.Request) -> web.Response:
    item_id = request.match_info["item_id"]
    if not _check_admin_password(request):
        return web.json_response({"ok": False, "error": "Unauthorized."}, status=401)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM shop_items WHERE id = ?", (item_id,))
        await db.commit()
        if cur.rowcount == 0:
            return web.json_response({"ok": False, "error": "Item not found."}, status=404)

    items = await get_all_items()
    sales = await get_recent_sales()
    return web.json_response({"ok": True, "items": items, "sales": sales})


async def handle_create_ticket_order(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON."}, status=400)

    buyer_discord = str(body.get("buyer_discord", "")).strip()
    if not buyer_discord:
        return web.json_response(
            {"ok": False, "error": "Discord ID or Username is required."}, status=400
        )

    item_name = str(body.get("item_name", "")).strip()
    if not item_name:
        return web.json_response(
            {"ok": False, "error": "Item name is required."}, status=400
        )

    order = {
        "id": str(uuid.uuid4()),
        "item_id": str(body.get("item_id", "")).strip(),
        "item_name": item_name,
        "category": str(body.get("category", "General")).strip() or "General",
        "price": max(0.0, float(body.get("price", 0.0) or 0.0)),
        "currency": str(body.get("currency", "USD")).strip() or "USD",
        "description": str(body.get("description", "")).strip(),
        "image_url": str(body.get("image_url", "")).strip(),
        "buyer_discord": buyer_discord,
        "buyer_notes": str(body.get("buyer_notes", "")).strip(),
        "channel_id": "",
        "channel_name": "",
        "status": "open",
        "created_at": _now_iso(),
    }

    channel_id, channel_name = await create_order_ticket_channel(order)
    order["channel_id"] = channel_id
    order["channel_name"] = channel_name

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO ticket_orders
                (id, item_id, item_name, category, price, currency, description,
                 image_url, buyer_discord, buyer_notes, channel_id, channel_name,
                 status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["id"],
                order["item_id"],
                order["item_name"],
                order["category"],
                order["price"],
                order["currency"],
                order["description"],
                order["image_url"],
                order["buyer_discord"],
                order["buyer_notes"],
                order["channel_id"],
                order["channel_name"],
                order["status"],
                order["created_at"],
            ),
        )
        await db.commit()

    return web.json_response(
        {
            "ok": True,
            "ticket": {
                "id": order["id"],
                "channel_id": order["channel_id"],
                "channel_name": order["channel_name"],
                "buyer_discord": order["buyer_discord"],
                "item_name": order["item_name"],
            },
        }
    )


@tree.command(name="ticketpanel", description="Post the VortexShop order ticket panel.")
async def cmd_ticket_panel(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="VortexShop Order Tickets",
        description="Browse the live shop on the website, click **Ticket Order**, enter your Discord ID or Username, and a private ticket channel will be created here automatically.",
        color=0xF59E0B,
    )
    await interaction.response.send_message(embed=embed)


async def start_web_server() -> web.AppRunner:
    app = web.Application(client_max_size=15 * 1024 * 1024)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/showcase", handle_api_showcase)
    app.router.add_get("/api/shop", handle_api_shop)
    app.router.add_post("/api/admin/login", handle_admin_login)
    app.router.add_post("/api/shop/items", handle_create_item)
    app.router.add_put("/api/shop/items/{item_id}", handle_update_item)
    app.router.add_post("/api/shop/items/{item_id}/minus-one", handle_minus_one_sold)
    app.router.add_delete("/api/shop/items/{item_id}", handle_delete_item)
    app.router.add_post("/api/tickets/create", handle_create_ticket_order)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[Web] Server listening on 0.0.0.0:{PORT}")
    return runner


@bot.event
async def on_ready() -> None:
    bot.add_view(CloseTicketView())
    try:
        await tree.sync()
    except Exception as exc:
        print(f"[Bot] Slash sync error: {exc}")
    print(f"[Bot] Logged in as {bot.user} (ID: {bot.user.id})")


async def main() -> None:
    await init_db()
    runner = await start_web_server()
    try:
        if DISCORD_TOKEN:
            await bot.start(DISCORD_TOKEN)
        else:
            print("[Bot] DISCORD_TOKEN not set; running web server only.")
            while True:
                await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
