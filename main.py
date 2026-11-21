import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web
import discord
from discord import app_commands, ui

# ==============================================================================
# CONFIGURATION (Set via environment variables or defaults)
# ==============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "1542941315933667348"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1572062945016414310"))  # Optional category ID
MM_ROLE_ID = int(os.getenv("MM_ROLE_ID", "0"))  # Optional Middleman/Staff role ID
TRANSCRIPT_CHANNEL_ID = int(os.getenv("TRANSCRIPT_CHANNEL_ID", "1569058957404803153"))  # Optional log channel ID

# Where closed tickets are sent (e.g., https://vortexshop.onrender.com/api/tickets/closed)
WEBSITE_TICKET_WEBHOOK_URL = os.getenv("WEBSITE_TICKET_WEBHOOK_URL", "").strip()
WEBSITE_WEBHOOK_SECRET = os.getenv("WEBSITE_WEBHOOK_SECRET", "").strip()

WEB_HOST = os.getenv("HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT", "8080"))
DATA_FILE = Path("closed_tickets_log.json")

# ==============================================================================
# STATE & PERSISTENCE
# ==============================================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Active tickets keyed by channel_id: dict
active_tickets: dict[int, dict] = {}
closed_tickets: list[dict] = []


def load_closed_tickets() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def save_closed_tickets() -> None:
    DATA_FILE.write_text(json.dumps(closed_tickets[:200], indent=2), encoding="utf-8")


def format_at_user(user: discord.abc.User | None, fallback: str = "@unknown") -> str:
    if not user:
        cleaned = fallback.strip()
        return cleaned if cleaned.startswith("@") else f"@{cleaned}"
    handle = user.name if user.discriminator in (None, "0", "") else f"{user.name}#{user.discriminator}"
    return f"@{handle}"


def get_avatar_url(user: discord.abc.User | None) -> str:
    if user and user.display_avatar:
        return user.display_avatar.url
    return "https://cdn.discordapp.com/embed/avatars/0.png"


async def resolve_member_or_user(guild: discord.Guild | None, raw_input: str) -> tuple[discord.abc.User | None, str]:
    """Resolve a user by mention (<@123>), numeric ID, or @username in the guild."""
    text = (raw_input or "").strip()
    if not text:
        return None, "@unknown"

    digits = "".join(ch for ch in text if ch.isdigit())
    if guild and digits and len(digits) >= 15:
        uid = int(digits)
        member = guild.get_member(uid)
        if member:
            return member, format_at_user(member)
        try:
            fetched = await bot.fetch_user(uid)
            if fetched:
                return fetched, format_at_user(fetched)
        except Exception:
            pass

    clean_name = text.lstrip("@").lower()
    if guild and clean_name:
        for m in guild.members:
            if m.name.lower() == clean_name or (m.display_name and m.display_name.lower() == clean_name):
                return m, format_at_user(m)

    normalized = text if text.startswith("@") else f"@{text}"
    return None, normalized


async def post_closed_ticket_to_website(record: dict) -> dict:
    """Send closed ticket payload (Trader 1, Trader 2, Claimed by @user) to the website."""
    delivery = {"attempted": False, "ok": False, "status": None, "error": None}
    if not WEBSITE_TICKET_WEBHOOK_URL:
        delivery["error"] = "WEBSITE_TICKET_WEBHOOK_URL not set"
        return delivery

    delivery["attempted"] = True
    headers = {"Content-Type": "application/json"}
    if WEBSITE_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = WEBSITE_WEBHOOK_SECRET

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(WEBSITE_TICKET_WEBHOOK_URL, json=record, headers=headers) as resp:
                delivery["status"] = resp.status
                delivery["ok"] = 200 <= resp.status < 300
                if not delivery["ok"]:
                    delivery["error"] = await resp.text()
    except Exception as exc:
        delivery["error"] = str(exc)

    return delivery


def build_closed_embed(record: dict) -> discord.Embed:
    t1 = record["trader_1"]
    t2 = record["trader_2"]
    embed = discord.Embed(
        title=f"Ticket Closed • {record['ticket_id']}",
        color=discord.Color.gold(),
        timestamp=datetime.fromisoformat(record["closed_at"]),
    )
    embed.add_field(
        name="Trader 1 (Giving)",
        value=f"**Name:** {t1['name']} ({t1['mention']})\n**Items:** {t1['giving_items']}",
        inline=True,
    )
    embed.add_field(
        name="Trader 2 (Giving)",
        value=f"**Name:** {t2['name']} ({t2['mention']})\n**Items:** {t2['giving_items']}",
        inline=True,
    )
    embed.add_field(
        name="Claimed By",
        value=f"**{record['claimed_by']}** (`{record.get('claimed_by_id', 'N/A')}`)",
        inline=False,
    )
    if record.get("game") or record.get("notes"):
        embed.add_field(
            name="Trade Details",
            value=f"**Game:** {record.get('game', 'Any')}\n**Notes:** {record.get('notes') or 'None'}",
            inline=False,
        )
    if t1.get("avatar_url"):
        embed.set_thumbnail(url=t1["avatar_url"])
    if t2.get("avatar_url"):
        embed.set_image(url=t2["avatar_url"])
    return embed


async def finalize_close_ticket(
    interaction: discord.Interaction,
    override_trader1: str | None = None,
    override_trader2: str | None = None,
    override_claimer: str | None = None,
    override_notes: str | None = None,
) -> None:
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Run this inside a ticket text channel.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    ticket = active_tickets.get(channel.id, {})
    guild = interaction.guild

    raw_t1 = override_trader1 or ticket.get("trader_1_raw") or interaction.user.name
    raw_t2 = override_trader2 or ticket.get("trader_2_raw") or "Trader 2"
    raw_claimer = override_claimer or ticket.get("claimed_by_raw") or format_at_user(interaction.user)

    u1, m1 = await resolve_member_or_user(guild, raw_t1)
    u2, m2 = await resolve_member_or_user(guild, raw_t2)
    u_claim, m_claim = await resolve_member_or_user(guild, raw_claimer)

    record = {
        "ticket_id": ticket.get("ticket_id", f"VX-{channel.id % 10000:04d}"),
        "channel_id": channel.id,
        "channel_name": channel.name,
        "status": "CLOSED",
        "game": ticket.get("game", "Roblox Crosstrade"),
        "trader_1": {
            "name": u1.display_name if u1 else m1.lstrip("@"),
            "mention": m1,
            "user_id": str(u1.id) if u1 else None,
            "avatar_url": get_avatar_url(u1),
            "giving_items": ticket.get("trader_1_items", "Confirmed in ticket"),
        },
        "trader_2": {
            "name": u2.display_name if u2 else m2.lstrip("@"),
            "mention": m2,
            "user_id": str(u2.id) if u2 else None,
            "avatar_url": get_avatar_url(u2),
            "giving_items": ticket.get("trader_2_items", "Confirmed in ticket"),
        },
        "claimed_by": m_claim,
        "claimed_by_name": u_claim.display_name if u_claim else m_claim.lstrip("@"),
        "claimed_by_id": str(u_claim.id) if u_claim else str(interaction.user.id),
        "claimed_by_avatar_url": get_avatar_url(u_claim or interaction.user),
        "notes": override_notes if override_notes is not None else ticket.get("notes", ""),
        "closed_by": format_at_user(interaction.user),
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }

    delivery = await post_closed_ticket_to_website(record)
    record["website_delivery"] = delivery

    closed_tickets.insert(0, record)
    save_closed_tickets()
    active_tickets.pop(channel.id, None)

    if TRANSCRIPT_CHANNEL_ID and guild:
        log_ch = guild.get_channel(TRANSCRIPT_CHANNEL_ID)
        if isinstance(log_ch, discord.TextChannel):
            await log_ch.send(embed=build_closed_embed(record))

    status_msg = (
        f"Closed **{record['ticket_id']}** and sent to website (HTTP {delivery['status']})."
        if delivery["ok"]
        else f"Closed **{record['ticket_id']}** and saved locally ({delivery['error'] or 'ready for sync'})."
    )
    await interaction.followup.send(f"{status_msg} Deleting channel in 3 seconds...", ephemeral=True)
    await asyncio.sleep(3)
    try:
        await channel.delete(reason=f"Closed by {interaction.user}")
    except discord.Forbidden:
        pass


# ==============================================================================
# DISCORD UI COMPONENTS (MODAL, OPEN PANEL, TICKET CONTROLS)
# ==============================================================================
class OpenTradeTicketModal(ui.Modal, title="Open Vortex Trade / MM Ticket"):
    trader_1 = ui.TextInput(
        label="Trader 1 (@user or ID)",
        placeholder="e.g. @trader_one or 123456789012345678",
        required=True,
        max_length=100,
    )
    trader_1_items = ui.TextInput(
        label="Trader 1 Giving",
        placeholder="e.g. Harvester + Icepiercer (MM2)",
        required=True,
        max_length=200,
    )
    trader_2 = ui.TextInput(
        label="Trader 2 (@user or ID)",
        placeholder="e.g. @trader_two or 987654321098765432",
        required=True,
        max_length=100,
    )
    trader_2_items = ui.TextInput(
        label="Trader 2 Giving",
        placeholder="e.g. Raccoon + Dragonfly (Grow a Garden 2)",
        required=True,
        max_length=200,
    )
    notes = ui.TextInput(
        label="Game & Notes",
        placeholder="e.g. MM2 -> GaG 2 | Verified MM requested",
        required=False,
        max_length=250,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Tickets can only be opened inside a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        u1, m1 = await resolve_member_or_user(guild, self.trader_1.value)
        u2, m2 = await resolve_member_or_user(guild, self.trader_2.value)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for target_u in (u1, u2):
            if isinstance(target_u, discord.Member):
                overwrites[target_u] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
        if MM_ROLE_ID:
            mm_role = guild.get_role(MM_ROLE_ID)
            if mm_role:
                overwrites[mm_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        safe_slug = "".join(ch for ch in interaction.user.name.lower() if ch.isalnum())[:12] or "trade"
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{safe_slug}-{interaction.id % 10000:04d}",
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user}",
        )

        ticket_id = f"VX-{ticket_channel.id % 10000:04d}"
        active_tickets[ticket_channel.id] = {
            "ticket_id": ticket_id,
            "opened_by": format_at_user(interaction.user),
            "trader_1_raw": self.trader_1.value.strip(),
            "trader_1_items": self.trader_1_items.value.strip(),
            "trader_2_raw": self.trader_2.value.strip(),
            "trader_2_items": self.trader_2_items.value.strip(),
            "claimed_by_raw": None,
            "notes": self.notes.value.strip(),
        }

        embed = discord.Embed(
            title=f"Trade Ticket Opened • {ticket_id}",
            description="Claim this ticket to lock in the handler, then close to send Trader 1, Trader 2 & claim info to the website.",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Trader 1 Giving", value=f"{m1}\n`{self.trader_1_items.value.strip()}`", inline=True)
        embed.add_field(name="Trader 2 Giving", value=f"{m2}\n`{self.trader_2_items.value.strip()}`", inline=True)
        embed.add_field(name="Claimed By", value="*Unclaimed*", inline=False)
        if self.notes.value.strip():
            embed.add_field(name="Notes", value=self.notes.value.strip(), inline=False)
        embed.set_thumbnail(url=get_avatar_url(u1))

        await ticket_channel.send(
            content=f"{interaction.user.mention} {u1.mention if isinstance(u1, discord.Member) else ''} {u2.mention if isinstance(u2, discord.Member) else ''}".strip(),
            embed=embed,
            view=TicketActionView(),
        )
        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


class TicketPanelView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(
        label="Open Trade / MM Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="vortex_open_ticket_btn",
        emoji="🎫",
    )
    async def open_ticket_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(OpenTradeTicketModal())


class TicketActionView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.success,
        custom_id="vortex_claim_ticket_btn",
        emoji="🛡️",
    )
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        claimed_handle = format_at_user(interaction.user)
        ticket = active_tickets.setdefault(channel.id, {"ticket_id": f"VX-{channel.id % 10000:04d}"})
        ticket["claimed_by_raw"] = claimed_handle
        ticket["claimed_by_id"] = str(interaction.user.id)
        ticket["claimed_by_avatar_url"] = get_avatar_url(interaction.user)

        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0]
            for i, f in enumerate(emb.fields):
                if f.name == "Claimed By":
                    emb.set_field_at(i, name="Claimed By", value=f"**{claimed_handle}** ({interaction.user.mention})", inline=False)
                    break
            await interaction.message.edit(embed=emb, view=self)

        await interaction.response.send_message(f"Ticket claimed by **{claimed_handle}**.")

    @ui.button(
        label="Close & Send to Website",
        style=discord.ButtonStyle.danger,
        custom_id="vortex_close_ticket_btn",
        emoji="🔒",
    )
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await finalize_close_ticket(interaction)


# ==============================================================================
# SLASH COMMANDS
# ==============================================================================
@tree.command(name="ticket-panel", description="Post the Vortex Exchange & MM ticket panel")
@app_commands.default_permissions(manage_channels=True)
async def ticket_panel_cmd(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Vortex Exchange & MM — Ticket System",
        description=(
            "Click **Open Trade / MM Ticket** below to enter **Trader 1**, **Trader 2**, and each side's items.\n"
            "Once claimed and finished, closing the ticket automatically sends Trader 1 & Trader 2 profiles/names and the **Claimed by @user** record to the website."
        ),
        color=discord.Color.from_rgb(168, 85, 247),
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


@tree.command(name="close-ticket", description="Close ticket and send Trader 1, Trader 2 & claim info to website")
@app_commands.describe(
    trader_1="Trader 1 @username or ID (optional if already set)",
    trader_2="Trader 2 @username or ID (optional if already set)",
    claimed_by="Claimed by @username or ID (defaults to ticket claimer or you)",
    notes="Optional closing notes",
)
async def close_ticket_cmd(
    interaction: discord.Interaction,
    trader_1: str | None = None,
    trader_2: str | None = None,
    claimed_by: str | None = None,
    notes: str | None = None,
) -> None:
    await finalize_close_ticket(
        interaction,
        override_trader1=trader_1,
        override_trader2=trader_2,
        override_claimer=claimed_by,
        override_notes=notes,
    )


# ==============================================================================
# BUILT-IN HTTP SERVER (RECEIVES / SERVES CLOSED TICKETS)
# ==============================================================================
async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "closed_tickets_count": len(closed_tickets)})


async def handle_get_closed_tickets(request: web.Request) -> web.Response:
    return web.json_response({"tickets": closed_tickets})


async def handle_post_closed_ticket(request: web.Request) -> web.Response:
    """Allows your website or external call to post a closed ticket directly."""
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "Expected JSON object"}, status=400)

    t1 = payload.get("trader_1") or {}
    t2 = payload.get("trader_2") or {}
    claimed = str(payload.get("claimed_by") or "@unassigned").strip()
    if not claimed.startswith("@"):
        claimed = f"@{claimed}"

    normalized = {
        "ticket_id": payload.get("ticket_id") or f"VX-{len(closed_tickets) + 1001}",
        "status": "CLOSED",
        "game": payload.get("game") or "Roblox Crosstrade",
        "trader_1": {
            "name": t1.get("name") or "Trader 1",
            "mention": t1.get("mention") or f"@{t1.get('name', 'trader1')}",
            "avatar_url": t1.get("avatar_url") or "https://cdn.discordapp.com/embed/avatars/0.png",
            "giving_items": t1.get("giving_items") or "",
        },
        "trader_2": {
            "name": t2.get("name") or "Trader 2",
            "mention": t2.get("mention") or f"@{t2.get('name', 'trader2')}",
            "avatar_url": t2.get("avatar_url") or "https://cdn.discordapp.com/embed/avatars/1.png",
            "giving_items": t2.get("giving_items") or "",
        },
        "claimed_by": claimed,
        "notes": payload.get("notes") or "",
        "closed_at": payload.get("closed_at") or datetime.now(timezone.utc).isoformat(),
    }

    closed_tickets.insert(0, normalized)
    save_closed_tickets()
    return web.json_response({"ok": True, "ticket": normalized}, status=201)


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/api/closed-tickets", handle_get_closed_tickets)
    app.router.add_post("/api/tickets/closed", handle_post_closed_ticket)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    return runner


@bot.event
async def setup_hook() -> None:
    global closed_tickets
    closed_tickets = load_closed_tickets()
    bot.add_view(TicketPanelView())
    bot.add_view(TicketActionView())
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild_obj)
        await tree.sync(guild=guild_obj)
    else:
        await tree.sync()
    await start_web_server()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) | HTTP on {WEB_HOST}:{WEB_PORT}")


if __name__ == "__main__":
    if DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
        raise RuntimeError("Set DISCORD_TOKEN environment variable before running main.py.")
    bot.run(DISCORD_TOKEN)
