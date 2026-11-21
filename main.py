import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import discord
from discord.ext import commands, tasks

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
TARGET_USER_ID = 1540575139538796634
TARGET_GUILD_ID = 1542941315933667348
PORT = int(os.getenv("PORT", "8080"))
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = BASE_DIR / "index.html"

DEFAULT_AVATAR_DECORATION = (
    "https://cdn.discordapp.com/media/v1/collectibles-shop/1570925242799497256/static"
)

DEFAULT_CLAN_BADGE_URL = (
    "https://cdn.discordapp.com/clan-badges/1542941315933667348/4d6d0a54a28859fb2b8ce09ee98b6f72.png?size=16"
)

USER_BADGES = [
    {
        "id": "universalist",
        "label": "Game Variety: Universalist",
        "icon_url": "https://raw.githubusercontent.com/mezotv/discord-badges/7175b749242ae7e593f70b3b0130b83e22a947e1/assets/game-variety/universalist.svg",
        "fallback_icon": "🎮",
    },
    {
        "id": "casual",
        "label": "Game Time: Casual",
        "icon_url": "https://raw.githubusercontent.com/mezotv/discord-badges/7175b749242ae7e593f70b3b0130b83e22a947e1/assets/game-time/casual.svg",
        "fallback_icon": "⚔️",
    },
    {
        "id": "breakout",
        "label": "Streaming: Breakout",
        "icon_url": "https://raw.githubusercontent.com/mezotv/discord-badges/7175b749242ae7e593f70b3b0130b83e22a947e1/assets/streaming/breakout.svg",
        "fallback_icon": "🖥️",
    },
    {
        "id": "orb",
        "label": "Orbs",
        "icon_url": "https://github.com/mezotv/discord-badges/raw/main/assets/orb.svg",
        "fallback_icon": "🔮",
    },
    {
        "id": "quest",
        "label": "Completed a Quest",
        "icon_url": "https://github.com/mezotv/discord-badges/raw/main/assets/quest.png",
        "fallback_icon": "🎯",
    },
    {
        "id": "hypesquad_bravery",
        "label": "HypeSquad Bravery",
        "icon_url": "https://github.com/mezotv/discord-badges/raw/main/assets/hype-squad-bravery.svg",
        "fallback_icon": "💜",
    },
]

PROFILE_CONFIG = {
    "bio_link_text": "Check out vortexshop.onrender.com",
    "store_url": "https://vortexshop.onrender.com",
    "custom_banner_url": None,
    "banner_position": "center",
    "clan_badge_url": DEFAULT_CLAN_BADGE_URL,
    "clan_emoji": "🍃",
    "clan_tag": "VEM",
    "role_badge_text": "VortexShop",
    "owner_line": "Owner of this server-",
    "invite_url": "https://discord.gg/3JPatMmyF",
    "full_bio": (
        "VortexShop Official — Roblox Crosstrading (Any Game) & Verified Middleman Hub. "
        "Always verify MM & official server tickets before trading."
    ),
    "member_since_fallback": "Aug 22, 2026",
    "mutual_servers_count": 4,
    "vouches_count": 120,
    "custom_trade_note": (
        "All Roblox crosstrades across any game go through official server tickets with verified "
        "middleman escrow. Double-check usernames and trade terms before confirming."
    ),
    "vouches": [
        {
            "name": "Aurelia",
            "avatar_url": None,
            "stars": 5,
            "trade_tag": "High-Value Crosstrade",
            "note": "Smooth trade from start to finish. Fast ticket response and zero stress.",
        },
        {
            "name": "KairoTradez",
            "avatar_url": None,
            "stars": 5,
            "trade_tag": "Roblox MM Escrow",
            "note": "Verified middleman handled the exchange cleanly and kept both sides updated.",
        },
        {
            "name": "MikaVortex",
            "avatar_url": None,
            "stars": 4,
            "trade_tag": "Storefront & Trade",
            "note": "Legit crosstrade and clear rules. Took a few extra minutes during peak hours, still solid.",
        },
        {
            "name": "NolanRBLX",
            "avatar_url": None,
            "stars": 4,
            "trade_tag": "Any-Game Swap",
            "note": "Safe ticket process and reliable server staff. Would trade again.",
        },
    ],
    "mm_rules": [
        "Open an official ticket inside the server before starting any Roblox crosstrade.",
        "Always confirm the Middleman's Discord ID and role inside the ticket channel.",
        "Avoid risky direct in-game trade windows or off-server DMs from unverified accounts.",
        "Double-check all items, quantities, and crosstrade terms before confirming.",
    ],
    "games": [
        {
            "key": "roblox-all",
            "category": "All Games",
            "title": "Roblox Crosstrading (Any Game)",
            "tag": "❖",
            "note": "We handle cross-trades across any Roblox game with verified middleman escrow & official tickets.",
        },
        {
            "key": "roblox-escrow",
            "category": "Escrow & Shop",
            "title": "Middleman Escrow & Storefront",
            "tag": "✦",
            "note": "Structured ticket protection, clear trade verification & listings at vortexshop.onrender.com.",
        },
    ],
}

SERVER_DEFAULTS = {
    "id": str(TARGET_GUILD_ID),
    "name": "Vortex Exchange & MM",
    "icon_url": None,
    "banner_url": None,
    "member_count": 0,
    "online_count": 0,
    "offline_count": 0,
    "boost_count": 0,
    "invite_url": "https://discord.gg/3JPatMmyF",
}

LATEST_DATA: dict = {
    "last_synced": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    "bot_status": "starting",
    "profile": {
        "id": str(TARGET_USER_ID),
        "username": "mvn412.",
        "display_name": "VortexShop",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
        "banner_url": PROFILE_CONFIG["custom_banner_url"],
        "banner_position": PROFILE_CONFIG["banner_position"],
        "avatar_decoration_url": DEFAULT_AVATAR_DECORATION,
        "badges": USER_BADGES,
        "status": "online",
        "custom_status": {"emoji": None, "text": "Very nice day"},
        "clan_badge_url": PROFILE_CONFIG["clan_badge_url"],
        "clan_emoji": PROFILE_CONFIG["clan_emoji"],
        "clan_tag": PROFILE_CONFIG["clan_tag"],
        "role_badge_text": PROFILE_CONFIG["role_badge_text"],
        "bio_link_text": PROFILE_CONFIG["bio_link_text"],
        "store_url": PROFILE_CONFIG["store_url"],
        "owner_line": PROFILE_CONFIG["owner_line"],
        "invite_url": PROFILE_CONFIG["invite_url"],
        "full_bio": PROFILE_CONFIG["full_bio"],
        "member_since": PROFILE_CONFIG["member_since_fallback"],
        "mutual_servers_count": PROFILE_CONFIG["mutual_servers_count"],
        "vouches_count": PROFILE_CONFIG["vouches_count"],
        "custom_trade_note": PROFILE_CONFIG["custom_trade_note"],
        "vouches": PROFILE_CONFIG["vouches"],
        "mm_rules": PROFILE_CONFIG["mm_rules"],
        "games": PROFILE_CONFIG["games"],
    },
    "server": dict(SERVER_DEFAULTS),
}


def load_index_html() -> bytes:
    try:
        return INDEX_HTML_PATH.read_text(encoding="utf-8").encode("utf-8")
    except Exception as exc:
        fallback = f"<h1>VortexShop Showcase</h1><p>Could not read index.html: {exc}</p>"
        return fallback.encode("utf-8")


intents = discord.Intents.default()
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)


def find_member(user_id: int) -> discord.Member | None:
    for guild in bot.guilds:
        m = guild.get_member(user_id)
        if m is not None:
            return m
    return None


async def resolve_guild_invite(guild: discord.Guild) -> str:
    try:
        invites = await guild.invites()
        for inv in invites:
            if inv.url and not inv.revoked:
                return inv.url
    except Exception:
        pass
    if guild.vanity_url:
        return str(guild.vanity_url)
    return PROFILE_CONFIG["invite_url"]


async def refresh_showcase_data(bot_status: str = "online"):
    global LATEST_DATA

    try:
        user = await bot.fetch_user(TARGET_USER_ID)
    except Exception as exc:
        print(f"Error fetching user {TARGET_USER_ID}: {exc}", flush=True)
        user = None

    member = find_member(TARGET_USER_ID)
    status = str(member.status) if member else "online"
    custom_status = {"emoji": None, "text": "Very nice day"}

    if member:
        for act in member.activities:
            if isinstance(act, discord.CustomActivity):
                custom_status = {
                    "emoji": str(act.emoji) if act.emoji else None,
                    "text": act.name or "Very nice day",
                }
                break

    live_deco = getattr(user, "avatar_decoration", None) if user else None
    deco_url = live_deco.url if live_deco else DEFAULT_AVATAR_DECORATION

    primary_guild = getattr(user, "primary_guild", None) if user else None
    clan_tag = getattr(primary_guild, "tag", None) if primary_guild else PROFILE_CONFIG["clan_tag"]

    mutual_count = sum(1 for g in bot.guilds if g.get_member(TARGET_USER_ID) is not None)

    banner_url = PROFILE_CONFIG["custom_banner_url"] or (
        user.banner.url if (user and user.banner) else None
    )

    profile_payload = {
        "id": str(user.id) if user else str(TARGET_USER_ID),
        "username": user.name if user else "mvn412.",
        "display_name": (user.global_name or user.name) if user else "VortexShop",
        "avatar_url": user.display_avatar.url if user else "https://cdn.discordapp.com/embed/avatars/0.png",
        "banner_url": banner_url,
        "banner_position": PROFILE_CONFIG["banner_position"],
        "avatar_decoration_url": deco_url,
        "badges": USER_BADGES,
        "status": status,
        "custom_status": custom_status,
        "clan_badge_url": PROFILE_CONFIG["clan_badge_url"],
        "clan_emoji": PROFILE_CONFIG["clan_emoji"],
        "clan_tag": clan_tag,
        "role_badge_text": PROFILE_CONFIG["role_badge_text"],
        "bio_link_text": PROFILE_CONFIG["bio_link_text"],
        "store_url": PROFILE_CONFIG["store_url"],
        "owner_line": PROFILE_CONFIG["owner_line"],
        "invite_url": PROFILE_CONFIG["invite_url"],
        "full_bio": PROFILE_CONFIG["full_bio"],
        "member_since": (
            user.created_at.strftime("%b %d, %Y")
            if (user and user.created_at)
            else PROFILE_CONFIG["member_since_fallback"]
        ),
        "mutual_servers_count": mutual_count if mutual_count > 0 else PROFILE_CONFIG["mutual_servers_count"],
        "vouches_count": PROFILE_CONFIG["vouches_count"],
        "custom_trade_note": PROFILE_CONFIG["custom_trade_note"],
        "vouches": PROFILE_CONFIG["vouches"],
        "mm_rules": PROFILE_CONFIG["mm_rules"],
        "games": PROFILE_CONFIG["games"],
    }

    guild = bot.get_guild(TARGET_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(TARGET_GUILD_ID, with_counts=True)
        except Exception:
            guild = None

    if guild:
        total_members = guild.member_count or len(guild.members)
        online_members = sum(
            1 for m in guild.members if m.status != discord.Status.offline
        )
        offline_members = max(0, total_members - online_members)
        invite_url = await resolve_guild_invite(guild)
        guild_banner_url = guild.banner.url if getattr(guild, "banner", None) else SERVER_DEFAULTS["banner_url"]

        server_payload = {
            "id": str(guild.id),
            "name": guild.name,
            "icon_url": guild.icon.url if guild.icon else None,
            "banner_url": guild_banner_url,
            "member_count": total_members,
            "online_count": online_members,
            "offline_count": offline_members,
            "boost_count": guild.premium_subscription_count or 0,
            "invite_url": invite_url,
        }
    else:
        server_payload = dict(SERVER_DEFAULTS)

    LATEST_DATA = {
        "last_synced": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "bot_status": bot_status,
        "profile": profile_payload,
        "server": server_payload,
    }


class ShowcaseHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/showcase") or self.path.startswith("/api/profile"):
            body = json.dumps(LATEST_DATA).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = load_index_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), ShowcaseHTTPHandler)
    print(f"Showcase running at http://0.0.0.0:{PORT}/ | JSON at /api/showcase", flush=True)
    server.serve_forever()


@tasks.loop(seconds=20)
async def sync_loop():
    await refresh_showcase_data(bot_status="online")


@bot.event
async def on_ready():
    print(f"Bot online as {bot.user} | User: {TARGET_USER_ID} | Server: {TARGET_GUILD_ID}", flush=True)
    await refresh_showcase_data(bot_status="online")
    if not sync_loop.is_running():
        sync_loop.start()


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    if after.id == TARGET_USER_ID or (after.guild and after.guild.id == TARGET_GUILD_ID):
        await refresh_showcase_data(bot_status="online")


@bot.command(name="badgesync")
async def sync_command(ctx: commands.Context):
    if ctx.author.id != TARGET_USER_ID:
        return
    await refresh_showcase_data(bot_status="online")
    await ctx.send("Synced full showcase, profile badges, and server stats.")


async def run_bot_loop():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("ERROR: DISCORD_BOT_TOKEN is missing or placeholder.", flush=True)
        LATEST_DATA["bot_status"] = "missing_token"
        return

    retry_delay = 90
    while True:
        try:
            LATEST_DATA["bot_status"] = "logging_in"
            await bot.login(BOT_TOKEN)
            await bot.connect(reconnect=True)
            break
        except discord.HTTPException as exc:
            if exc.status == 429:
                LATEST_DATA["bot_status"] = "rate_limited_429"
                print(
                    f"Discord HTTP 429 rate limit hit. Retrying login in {retry_delay}s...",
                    flush=True,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 600)
            else:
                LATEST_DATA["bot_status"] = "http_error"
                print(f"Discord HTTPException: {exc}. Retrying in 60s...", flush=True)
                await asyncio.sleep(60)
        except Exception as exc:
            LATEST_DATA["bot_status"] = "error"
            print(f"Bot loop error: {exc}. Retrying in 60s...", flush=True)
            await asyncio.sleep(60)


if __name__ == "__main__":
    threading.Thread(target=start_http_server, daemon=True).start()
    asyncio.run(run_bot_loop())
