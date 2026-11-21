import asyncio
import json
import os
import re
import threading
import traceback
import urllib.request
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

ELWEY_EFFECTS_URL = "https://elwey.fr/effects/"

STAFF_ROLE_IDS = [
    1568386943945801839,
    1568387066709024788,
    1568387138322694268,
    1568387457752371270,
]

ROLE_ICONS = {
    "founder": "https://cdn.discordapp.com/attachments/1400483862273851553/1573617003909087273/f0Y7LKdtE0xaAAAAAElFTkSuQmCC.png?ex=6b02a88a&is=6b01570a&hm=7a7ccb5f62c414545ce0af68ee27783bbfcfc313c4ea8f4dd84dd887d0253b7d",
    "server_manager": "https://media.discordapp.net/attachments/1400483862273851553/1573617317273673860/344441-communitymanager.png?ex=6b02a8d4&is=6b015754&hm=b723bf6c131749a7051f2e32859d807ebfd1b7df87ac669e5e704067b579022b&format=webp&quality=lossless&width=320&height=320",
    "senior_moderator": "https://media.discordapp.net/attachments/1400483862273851553/1573618296643649586/download.png?ex=6b02a9be&is=6b01583e&hm=c3a9a803edf2341f16a6d323bd239f347f47c77601c323526522b41a52910ecd&format=webp&quality=lossless&width=320&height=320",
    "support_server": "https://media.discordapp.net/attachments/1400483862273851553/1573619256468180992/269160-support.gif?ex=6b02aaa3&is=6b015923&hm=aff56438c85d06c263383b6b2ce42f98cff8c68d50a0e87a98da6871d69b6c06",
    "head_moderator": "https://media.discordapp.net/attachments/1400483862273851553/1573619265356169346/19683-senior-moderator-head-moderator.png?ex=6b02aaa5&is=6b015925&hm=62760f162af7acfe52a8a7d2a0f93d85e7448c6fdd1edc6faab43653b708dbfb&format=webp&quality=lossless&width=384&height=384",
}

ROLE_CATALOG_ITEMS = [
    {"id": str(STAFF_ROLE_IDS[0]), "label": "Founder Role", "short_label": "Founder", "icon_url": ROLE_ICONS["founder"]},
    {"id": str(STAFF_ROLE_IDS[1]), "label": "Server Manager Role", "short_label": "Manager", "icon_url": ROLE_ICONS["server_manager"]},
    {"id": str(STAFF_ROLE_IDS[2]), "label": "Senior Moderator Role", "short_label": "Senior Mod", "icon_url": ROLE_ICONS["senior_moderator"]},
    {"id": str(STAFF_ROLE_IDS[3]), "label": "Head Moderator Role", "short_label": "Head Mod", "icon_url": ROLE_ICONS["head_moderator"]},
    {"id": "support_server", "label": "Support Server Role", "short_label": "Support", "icon_url": ROLE_ICONS["support_server"]},
]

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
    "role_badge_text": "Founder • VortexShop",
    "role_badge_icon_url": ROLE_ICONS["founder"],
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
        "profile_effect": {
            "name": None,
            "asset_url": None,
            "source": "elwey.fr/effects",
        },
        "badges": USER_BADGES,
        "status": "online",
        "custom_status": {"emoji": None, "text": "Very nice day"},
        "clan_badge_url": PROFILE_CONFIG["clan_badge_url"],
        "clan_emoji": PROFILE_CONFIG["clan_emoji"],
        "clan_tag": PROFILE_CONFIG["clan_tag"],
        "role_badge_text": PROFILE_CONFIG["role_badge_text"],
        "role_badge_icon_url": PROFILE_CONFIG["role_badge_icon_url"],
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
    "role_catalog": ROLE_CATALOG_ITEMS,
    "staff_members": [],
}

_ELWEY_CACHE: dict = {"fetched_at": 0.0, "entries": []}
_USER_DETAIL_CACHE: dict[int, dict] = {}


def _fetch_elwey_effects_sync() -> list[dict]:
    now = datetime.now(timezone.utc).timestamp()
    if _ELWEY_CACHE["entries"] and (now - _ELWEY_CACHE["fetched_at"]) < 900:
        return _ELWEY_CACHE["entries"]

    try:
        req = urllib.request.Request(
            ELWEY_EFFECTS_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VortexShowcaseBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html, flags=re.IGNORECASE)
        entries = []
        for raw_src in img_matches:
            if raw_src.startswith("//"):
                full_url = "https:" + raw_src
            elif raw_src.startswith("/"):
                full_url = "https://elwey.fr" + raw_src
            elif raw_src.startswith("http"):
                full_url = raw_src
            else:
                continue

            slug = raw_src.split("/")[-1].split("?")[0]
            clean_name = re.sub(r"[-_]+", " ", Path(slug).stem).strip().title()
            if clean_name:
                entries.append({"name": clean_name, "asset_url": full_url})

        if entries:
            _ELWEY_CACHE["fetched_at"] = now
            _ELWEY_CACHE["entries"] = entries
        return entries
    except Exception:
        return _ELWEY_CACHE["entries"]


def build_effect_payload(user_obj, elwey_entries: list[dict]) -> dict:
    effect_obj = getattr(user_obj, "profile_effect", None) if user_obj else None
    effect_id = getattr(effect_obj, "id", None) if effect_obj else None
    effect_name = getattr(effect_obj, "name", None) if effect_obj else None

    matched_asset = None
    if elwey_entries:
        if effect_name:
            target_key = effect_name.lower().strip()
            for item in elwey_entries:
                if target_key in item["name"].lower() or item["name"].lower() in target_key:
                    matched_asset = item["asset_url"]
                    break
        if not matched_asset and effect_id:
            id_str = str(effect_id)
            for item in elwey_entries:
                if id_str in item["asset_url"]:
                    matched_asset = item["asset_url"]
                    break

    return {
        "id": str(effect_id) if effect_id else None,
        "name": effect_name,
        "asset_url": matched_asset,
        "source": "elwey.fr/effects",
    }


async def get_enriched_user(user_id: int, fallback_member: discord.Member | None = None):
    now = datetime.now(timezone.utc).timestamp()
    cached = _USER_DETAIL_CACHE.get(user_id)
    if cached and (now - cached["ts"]) < 300:
        return cached["user"]

    try:
        fetched = await bot.fetch_user(user_id)
        _USER_DETAIL_CACHE[user_id] = {"ts": now, "user": fetched}
        return fetched
    except Exception:
        return fallback_member


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


def resolve_role_icon(role: discord.Role) -> tuple[str | None, str]:
    lower = role.name.lower()
    if "founder" in lower or "owner" in lower:
        return ROLE_ICONS["founder"], "founder"
    if "server manager" in lower or "community manager" in lower or "manager" in lower:
        return ROLE_ICONS["server_manager"], "server_manager"
    if "head moderator" in lower or "head mod" in lower:
        return ROLE_ICONS["head_moderator"], "head_moderator"
    if "senior moderator" in lower or "senior mod" in lower or "mod" in lower:
        return ROLE_ICONS["senior_moderator"], "senior_moderator"
    if "support" in lower:
        return ROLE_ICONS["support_server"], "support_server"
    if role.icon:
        return role.icon.url, str(role.id)
    return None, str(role.id)


async def collect_staff_members(guild: discord.Guild | None, elwey_entries: list[dict]) -> list[dict]:
    if not guild:
        return []

    tracked_set = set(STAFF_ROLE_IDS)
    matched_pairs: list[tuple[discord.Member, list[discord.Role]]] = []

    for member in guild.members:
        matched_roles = [r for r in member.roles if r.id in tracked_set]
        if matched_roles:
            matched_roles.sort(key=lambda r: r.position, reverse=True)
            matched_pairs.append((member, matched_roles))

    results = []
    for member, matched_roles in matched_pairs[:30]:
        detailed_user = await get_enriched_user(member.id, fallback_member=member)
        source_obj = detailed_user or member

        banner_url = None
        if getattr(source_obj, "banner", None):
            banner_url = source_obj.banner.url
        elif getattr(member, "banner", None):
            banner_url = member.banner.url

        deco_obj = getattr(source_obj, "avatar_decoration", None) or getattr(member, "avatar_decoration", None)
        deco_url = deco_obj.url if deco_obj else None

        effect_payload = build_effect_payload(source_obj, elwey_entries)

        role_items = []
        for r in matched_roles:
            icon_url, role_key = resolve_role_icon(r)
            role_items.append({
                "id": str(r.id),
                "role_key": role_key,
                "name": r.name,
                "icon_url": icon_url,
            })

        results.append({
            "id": str(member.id),
            "username": member.name,
            "display_name": member.display_name,
            "status": str(member.status) if member.status else "offline",
            "avatar_url": member.display_avatar.url,
            "banner_url": banner_url,
            "avatar_decoration_url": deco_url,
            "profile_effect": effect_payload,
            "roles": role_items,
        })

    return results


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

    elwey_entries = await asyncio.to_thread(_fetch_elwey_effects_sync)

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

    profile_effect_payload = build_effect_payload(user, elwey_entries)

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
        "profile_effect": profile_effect_payload,
        "badges": USER_BADGES,
        "status": status,
        "custom_status": custom_status,
        "clan_badge_url": PROFILE_CONFIG["clan_badge_url"],
        "clan_emoji": PROFILE_CONFIG["clan_emoji"],
        "clan_tag": clan_tag,
        "role_badge_text": PROFILE_CONFIG["role_badge_text"],
        "role_badge_icon_url": PROFILE_CONFIG["role_badge_icon_url"],
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
        staff_list = await collect_staff_members(guild, elwey_entries)
    else:
        server_payload = dict(SERVER_DEFAULTS)
        staff_list = []

    LATEST_DATA = {
        "last_synced": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "bot_status": bot_status,
        "profile": profile_payload,
        "server": server_payload,
        "role_catalog": ROLE_CATALOG_ITEMS,
        "staff_members": staff_list,
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


@tasks.loop(seconds=25)
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


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.guild and after.guild.id == TARGET_GUILD_ID:
        _USER_DETAIL_CACHE.pop(after.id, None)
        await refresh_showcase_data(bot_status="online")


@bot.command(name="badgesync")
async def sync_command(ctx: commands.Context):
    if ctx.author.id != TARGET_USER_ID:
        return
    _USER_DETAIL_CACHE.clear()
    await refresh_showcase_data(bot_status="online")
    await ctx.send("Synced showcase, role members, profile media, banners, decorations, and effects.")


async def idle_forever():
    while True:
        await asyncio.sleep(3600)


async def run_bot_loop():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("ERROR: DISCORD_BOT_TOKEN is missing or placeholder. Keeping web server alive.", flush=True)
        LATEST_DATA["bot_status"] = "missing_token"
        await idle_forever()
        return

    retry_delay = 90
    while True:
        try:
            LATEST_DATA["bot_status"] = "logging_in"
            await bot.start(BOT_TOKEN, reconnect=True)
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
            print(f"Bot loop error: {exc}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(60)


def main():
    try:
        threading.Thread(target=start_http_server, daemon=True).start()
        asyncio.run(run_bot_loop())
    except Exception as exc:
        print(f"Fatal startup error: {exc}", flush=True)
        traceback.print_exc()
        threading.Event().wait()


if __name__ == "__main__":
    main()
