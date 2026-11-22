import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
PORT = int(os.getenv("PORT", "10000"))

# Path to your uploaded HTML file
HTML_PATH = Path(os.getenv("HTML_PATH", "index.html"))

# Tracked Role IDs referenced in your HTML showcase
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
# DISCORD BOT SETUP (Requires Server Members & Presence Intents in Dev Portal)
# ==============================================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cache for fetched user banners/accents (since guild member objects lack banners)
user_profile_cache: dict[int, dict[str, Any]] = {}


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
    """Fetches full User object (for banner_url) and caches it."""
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


def build_default_games() -> list[dict[str, str]]:
    return [
        {
            "tag": "MM2",
            "title": "Murder Mystery 2 — Godlies, Chromas & Sets",
            "note": "Harvester, Icepiercer, Gingerscope, Corrupt Set, Sakura Set & Traveler's Gun.",
        },
        {
            "tag": "GAG2",
            "title": "Grow a Garden 2 — Rare Pets & Seeds",
            "note": "Raccoons, Dragonflies, Unicorns, Ice Serpents, Black Dragons & Exotic Seeds.",
        },
        {
            "tag": "PS99 / ADM",
            "title": "Pet Simulator 99 & Adopt Me!",
            "note": "Titanics, Huges, Gems, High-Tier Neon/Mega Pets & Verified Crosstrades.",
        },
        {
            "tag": "ANY GAME",
            "title": "Blade Ball, Steal a Brainrot & Custom Requests",
            "note": "All crosstrades secured inside official Vortex Exchange & MM tickets.",
        },
    ]


def build_default_vouches() -> list[dict[str, Any]]:
    return [
        {
            "name": "TrustedTrader_PH",
            "trade_tag": "MM2 Harvester ↔ Robux",
            "stars": 5,
            "avatar_url": "",
            "note": "Super fast MM service, zero hassle and smooth handoff inside ticket.",
        },
        {
            "name": "KiroVFX",
            "trade_tag": "PS99 Titanic ↔ Adopt Me",
            "stars": 5,
            "avatar_url": "",
            "note": "Legit middleman and active staff. Vouching 100%!",
        },
        {
            "name": "ZyroBlox",
            "trade_tag": "Grow a Garden 2 Bundle",
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

    # 1. Server Stats
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

        # Collect members holding any of the tracked role IDs
        for member in guild.members:
            if member.bot:
                continue
            matched_roles = [r for r in member.roles if r.id in TRACKED_ROLE_IDS]
            if not matched_roles:
                continue

            # Sort matched roles highest hierarchy first
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

    # Sort staff: online/idle/dnd first, then display name
    status_rank = {"online": 0, "idle": 1, "dnd": 2, "offline": 3}
    staff_members_list.sort(key=lambda m: (status_rank.get(m["status"], 3), m["display_name"].lower()))

    # 2. Owner Profile
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
        "full_bio": "Founder of Vortex Exchange & MM. Safe Roblox crosstrading, verified middleman tickets, and instant storefront stock.",
        "member_since": owner_enriched["created_at"] or "Aug 22, 2026",
        "custom_trade_note": "Verified Roblox crosstrading across MM2, Grow a Garden 2, PS99, Adopt Me!, and Blade Ball via official server tickets.",
        "badges": [
            {"id": "founder", "label": "Server Founder", "fallback_icon": "👑"},
            {"id": "verified_mm", "label": "Verified Middleman", "fallback_icon": "🛡️"},
            {"id": "booster", "label": "Nitro & Server Booster", "fallback_icon": "💎"},
        ],
        "games": build_default_games(),
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
# AIOHTTP WEB ROUTES
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


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "bot_ready": bot.is_ready()})


@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")


async def start_services():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/showcase", handle_showcase_api)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    print(f"[WEB] Serving showcase on http://0.0.0.0:{PORT}")

    if DISCORD_TOKEN:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    else:
        print("[WARN] DISCORD_TOKEN not set — running web server in fallback mode.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start_services())
