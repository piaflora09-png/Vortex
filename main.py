import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web
import discord
from discord import app_commands, ui

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "1542941315933667348"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
MM_ROLE_ID = int(os.getenv("MM_ROLE_ID", "0"))
TRANSCRIPT_CHANNEL_ID = int(os.getenv("TRANSCRIPT_CHANNEL_ID", "0"))

# Admin password required to add items to the shop
SHOP_ADMIN_PASSWORD = os.getenv("SHOP_ADMIN_PASSWORD", "vortexadmin2026")

# Webhooks (fall back to DISCORD_WEBHOOK_URL if specific ones are not set)
DEFAULT_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
ITEM_ADDED_WEBHOOK_URL = os.getenv("ITEM_ADDED_WEBHOOK_URL", DEFAULT_WEBHOOK_URL).strip()
ITEM_SOLD_WEBHOOK_URL = os.getenv("ITEM_SOLD_WEBHOOK_URL", DEFAULT_WEBHOOK_URL).strip()
TICKET_CLOSED_WEBHOOK_URL = os.getenv("TICKET_CLOSED_WEBHOOK_URL", DEFAULT_WEBHOOK_URL).strip()

WEB_HOST = os.getenv("HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT", "8080"))

DB_FILE = Path("vortex_store_data.json")
HTML_FILE = Path("index.html")

# ==============================================================================
# EMBEDDED FALLBACK HTML (USED IF index.html IS NOT PRESENT ON DISK)
# ==============================================================================
FALLBACK_HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>VortexShop — Crosstrading Storefront, Ticket System &amp; Closed Trades</title>
  <style>
    :root {
      --bg: #070912;
      --panel: #0d1220;
      --border: rgba(148, 163, 184, 0.16);
      --accent: #3b82f6;
      --accent-2: #a855f7;
      --gold: #f59e0b;
      --green: #22c55e;
      --red: #ef4444;
      --text: #f8fafc;
      --muted: #94a3b8;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 15% 12%, rgba(59, 130, 246, 0.16), transparent 42%),
        radial-gradient(circle at 85% 20%, rgba(168, 85, 247, 0.14), transparent 45%),
        radial-gradient(circle at 50% 90%, rgba(245, 158, 11, 0.08), transparent 50%),
        var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      padding: 20px 16px 70px;
    }

    .container { max-width: 1180px; margin: 0 auto; }

    .topbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: rgba(13, 18, 32, 0.92);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 12px 16px;
      margin-bottom: 22px;
      backdrop-filter: blur(12px);
    }

    .brand { display: flex; align-items: center; gap: 10px; font-weight: 900; font-size: 1.05rem; letter-spacing: 0.02em; }
    .brand-badge {
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      background: rgba(59, 130, 246, 0.16);
      border: 1px solid rgba(59, 130, 246, 0.4);
      color: #93c5fd;
    }

    .nav-group { display: flex; flex-wrap: wrap; gap: 8px; }
    .nav-btn {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      color: #e2e8f0;
      padding: 8px 14px;
      border-radius: 10px;
      font-size: 0.84rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .nav-btn:hover { background: rgba(59, 130, 246, 0.16); color: #fff; }
    .nav-btn.active {
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      border-color: transparent;
      color: #fff;
      box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35);
    }

    .status-banner {
      display: none;
      margin-bottom: 16px;
      padding: 11px 14px;
      border-radius: 12px;
      font-size: 0.85rem;
      font-weight: 600;
      border: 1px solid rgba(34, 197, 94, 0.38);
      background: rgba(34, 197, 94, 0.12);
      color: #bbf7d0;
    }
    .status-banner.error {
      border-color: rgba(239, 68, 68, 0.45);
      background: rgba(239, 68, 68, 0.14);
      color: #fecaca;
    }

    .section-view { display: none; }
    .section-view.active { display: block; }
    .shop-layout { display: grid; grid-template-columns: 1.45fr 1fr; gap: 22px; align-items: start; }

    .card-box {
      background: linear-gradient(180deg, rgba(15, 22, 41, 0.96), rgba(10, 14, 26, 0.98));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.55);
      margin-bottom: 18px;
    }

    .eyebrow { font-size: 0.72rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #60a5fa; margin-bottom: 4px; }
    .section-heading-row { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin-bottom: 14px; }
    .section-heading-row h2 { margin: 0; font-size: 1.35rem; font-weight: 800; }
    .step-counter { font-size: 0.75rem; font-weight: 700; color: var(--muted); letter-spacing: 0.06em; }

    .info-strip {
      padding: 11px 13px;
      border-radius: 12px;
      background: rgba(245, 158, 11, 0.09);
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: #fde68a;
      font-size: 0.82rem;
      line-height: 1.45;
      margin-bottom: 14px;
    }

    .products-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }
    .product-card {
      background: rgba(18, 26, 48, 0.9);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .product-img-wrap { position: relative; height: 150px; background: #090d18; display: grid; place-items: center; overflow: hidden; }
    .product-img-wrap img { width: 100%; height: 100%; object-fit: cover; }

    .stock-pill {
      position: absolute;
      top: 8px;
      right: 8px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 800;
      background: rgba(15, 23, 42, 0.88);
      border: 1px solid rgba(255, 255, 255, 0.16);
      color: #86efac;
    }
    .stock-pill.sold-out { color: #fca5a5; border-color: rgba(239, 68, 68, 0.45); }

    .product-body { padding: 12px 14px 14px; }
    .product-cat { font-size: 0.7rem; font-weight: 700; color: #93c5fd; text-transform: uppercase; letter-spacing: 0.04em; }
    .product-title { margin: 3px 0 6px; font-size: 1rem; font-weight: 800; }
    .product-price { font-size: 1.05rem; font-weight: 900; color: #fbbf24; margin-bottom: 6px; }
    .product-desc { margin: 0 0 8px; font-size: 0.8rem; color: #cbd5e1; line-height: 1.4; }
    .product-seller { font-size: 0.73rem; color: var(--muted); margin-bottom: 10px; }
    .product-actions { display: flex; gap: 7px; flex-wrap: wrap; }

    .btn-primary {
      background: linear-gradient(135deg, #2563eb, #3b82f6);
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 9px 13px;
      font-size: 0.82rem;
      font-weight: 800;
      cursor: pointer;
    }
    .btn-primary:hover { filter: brightness(1.08); }
    .btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.06);
      color: #e2e8f0;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 11px;
      font-size: 0.76rem;
      font-weight: 700;
      cursor: pointer;
    }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.12); }

    .btn-gold {
      background: linear-gradient(180deg, #f59e0b, #d97706);
      color: #111827;
      border: none;
      border-radius: 10px;
      padding: 9px 14px;
      font-size: 0.82rem;
      font-weight: 900;
      cursor: pointer;
    }

    .upload-dropzone {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 20px 14px;
      border: 1.5px dashed rgba(59, 130, 246, 0.45);
      border-radius: 14px;
      background: rgba(15, 23, 42, 0.65);
      cursor: pointer;
      text-align: center;
      margin-bottom: 12px;
    }
    .upload-dropzone:hover { border-color: #60a5fa; background: rgba(30, 41, 59, 0.65); }
    .upload-preview { max-height: 110px; border-radius: 10px; display: none; margin-top: 6px; object-fit: cover; }

    .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .field { margin-bottom: 11px; }
    .field label { display: block; font-size: 0.78rem; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
    .field label span.req { color: #38bdf8; }
    .field label span.opt { color: #38bdf8; font-weight: 500; }

    .field input, .field select, .field textarea {
      width: 100%;
      background: #090d18;
      border: 1px solid rgba(148, 163, 184, 0.22);
      border-radius: 10px;
      padding: 9px 11px;
      color: #fff;
      font-size: 0.84rem;
      font-family: inherit;
      outline: none;
    }
    .field input:focus, .field select:focus, .field textarea:focus { border-color: #3b82f6; }
    .field textarea { min-height: 72px; resize: vertical; }

    .closed-card {
      background: rgba(18, 26, 48, 0.88);
      border: 1px solid rgba(245, 158, 11, 0.28);
      border-radius: 14px;
      padding: 13px 15px;
      margin-bottom: 12px;
    }
    .closed-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
    .traders-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 8px; }
    .trader-chip {
      display: flex;
      align-items: center;
      gap: 9px;
      background: #090d18;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
    }
    .trader-chip img { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 1.5px solid #f59e0b; }

    @media (max-width: 900px) { .shop-layout { grid-template-columns: 1fr; } }
    @media (max-width: 560px) { .form-grid-2, .traders-row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="container">
    <header class="topbar">
      <div class="brand">
        <span>VortexShop</span>
        <span class="brand-badge">TICKET + ADMIN SHOP</span>
      </div>
      <div class="nav-group">
        <button type="button" class="nav-btn active" data-view="shop" onclick="switchView('shop')">Shop &amp; Add Item</button>
        <button type="button" class="nav-btn" data-view="tickets" onclick="switchView('tickets')">Ticket &amp; Closed Trades</button>
      </div>
    </header>

    <div id="status-banner" class="status-banner"></div>

    <section id="view-shop" class="section-view active">
      <div class="shop-layout">
        <div>
          <div class="card-box">
            <div class="section-heading-row">
              <h2>Available Shop Items</h2>
              <span class="step-counter" id="shop-item-count">0 ITEMS</span>
            </div>
            <div class="info-strip">
              <strong>How Buying Works:</strong> No upfront website checkout payment. Click <strong>Make Ticket to Buy</strong> on any item to generate a ticket for that item and pay whoever posted it directly in your ticket.
            </div>
            <div class="products-grid" id="products-grid"></div>
          </div>
        </div>

        <div>
          <div class="card-box">
            <div class="eyebrow">PRODUCT DETAILS</div>
            <div class="section-heading-row">
              <h2>Add a new item</h2>
              <span class="step-counter">01 / ITEM</span>
            </div>

            <form id="add-item-form" onsubmit="handleAddItem(event)">
              <div class="field">
                <label for="admin-password">Admin Password <span class="req">*</span></label>
                <input type="password" id="admin-password" placeholder="Enter admin password (default: vortexadmin2026)" required />
              </div>

              <label class="upload-dropzone" for="product-image-file">
                <div style="font-size:1.25rem;">&#8593;</div>
                <div style="font-weight:800;font-size:0.88rem;">Upload product image</div>
                <div style="font-size:0.74rem;color:var(--muted);">PNG, JPG, or WebP &middot; up to 3 MB</div>
                <img id="product-image-preview" class="upload-preview" alt="Preview" />
              </label>
              <input type="file" id="product-image-file" accept="image/png,image/jpeg,image/webp" style="display:none;" onchange="handleImageFileChange(event)" />

              <div class="field">
                <label for="product-image-url">Or Image URL <span class="opt">(optional)</span></label>
                <input type="url" id="product-image-url" placeholder="https://..." />
              </div>

              <div class="field">
                <label for="item-name">Item name <span class="req">*</span></label>
                <input type="text" id="item-name" placeholder="e.g. Steam Wallet Code / MM2 Set" required />
              </div>

              <div class="form-grid-2">
                <div class="field">
                  <label for="item-category">Category <span class="req">*</span></label>
                  <input type="text" id="item-category" placeholder="e.g. Gift Cards / MM2" required />
                </div>
                <div class="field">
                  <label for="item-stock">Available stock <span class="req">*</span></label>
                  <input type="number" id="item-stock" min="1" value="1" required />
                </div>
              </div>

              <div class="form-grid-2">
                <div class="field">
                  <label for="item-price">Price <span class="req">*</span></label>
                  <input type="number" id="item-price" step="0.01" min="0" placeholder="0.00" required />
                </div>
                <div class="field">
                  <label for="item-currency">Currency <span class="req">*</span></label>
                  <select id="item-currency">
                    <option value="USD">USD &mdash; US Dollar</option>
                    <option value="PHP">PHP &mdash; Philippine Peso</option>
                    <option value="EUR">EUR &mdash; Euro</option>
                    <option value="ROB">ROB &mdash; Robux / Value</option>
                  </select>
                </div>
              </div>

              <div class="field">
                <label for="item-poster">Posted by (@user / Seller) <span class="req">*</span></label>
                <input type="text" id="item-poster" value="@mvn412." placeholder="@seller" required />
              </div>

              <div class="field">
                <label for="item-desc">Description <span class="opt">(optional)</span></label>
                <textarea id="item-desc" placeholder="Platform, region, edition, or anything else buyers should know."></textarea>
              </div>

              <button type="submit" class="btn-primary" style="width:100%;">Add product &#8599;</button>
            </form>
          </div>
        </div>
      </div>
    </section>

    <section id="view-tickets" class="section-view">
      <div class="shop-layout">
        <div class="card-box">
          <h2>Create / Close Trade Ticket</h2>
          <div class="info-strip">
            When you close a ticket, <strong>Trader 1</strong> (profile image &amp; name), <strong>Trader 2</strong> (profile image &amp; name), and <strong>Claimed by @user</strong> are sent to your website (<code>/api/tickets/closed</code>) and shown in the closed trades feed.
          </div>

          <form id="ticket-form" onsubmit="handleCloseTicket(event)">
            <div class="form-grid-2">
              <div class="field">
                <label for="t1-name">Trader 1 Name (Giving) *</label>
                <input type="text" id="t1-name" placeholder="e.g. Aurelia" required />
              </div>
              <div class="field">
                <label for="t1-avatar">Trader 1 Profile Image URL</label>
                <input type="url" id="t1-avatar" placeholder="https://cdn.discordapp.com/..." />
              </div>
            </div>

            <div class="field">
              <label for="t1-items">Trader 1 Giving Items *</label>
              <input type="text" id="t1-items" placeholder="e.g. Harvester + Icepiercer" required />
            </div>

            <div class="form-grid-2">
              <div class="field">
                <label for="t2-name">Trader 2 Name (Giving) *</label>
                <input type="text" id="t2-name" placeholder="e.g. Buyer / Seller" required />
              </div>
              <div class="field">
                <label for="t2-avatar">Trader 2 Profile Image URL</label>
                <input type="url" id="t2-avatar" placeholder="https://cdn.discordapp.com/..." />
              </div>
            </div>

            <div class="field">
              <label for="t2-items">Trader 2 Giving Items *</label>
              <input type="text" id="t2-items" placeholder="e.g. Paid via ticket / Dragonfly" required />
            </div>

            <div class="form-grid-2">
              <div class="field">
                <label for="t-claimed">Claimed By (@user) *</label>
                <input type="text" id="t-claimed" value="@mvn412." placeholder="@user" required />
              </div>
              <div class="field">
                <label for="t-game">Game / Item</label>
                <input type="text" id="t-game" value="Roblox Crosstrade" />
              </div>
            </div>

            <button type="submit" class="btn-gold" style="width:100%;">Close Ticket &amp; Send to Website</button>
          </form>
        </div>

        <div class="card-box">
          <div class="section-heading-row">
            <h2>Closed Trades Sent to Website</h2>
            <span class="step-counter" id="closed-count">0 CLOSED</span>
          </div>
          <div id="closed-trades-list"></div>
        </div>
      </div>
    </section>
  </div>

  <script>
    let shopItems = [];
    let closedTrades = [];
    let uploadedImageDataUrl = "";

    function showBanner(msg, isError = false) {
      const el = document.getElementById("status-banner");
      el.textContent = msg;
      el.className = isError ? "status-banner error" : "status-banner";
      el.style.display = "block";
      clearTimeout(window._bannerTimer);
      window._bannerTimer = setTimeout(() => { el.style.display = "none"; }, 3600);
    }

    function escapeHtml(str) {
      return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function switchView(viewName) {
      document.querySelectorAll(".nav-btn").forEach((b) => {
        b.classList.toggle("active", b.getAttribute("data-view") === viewName);
      });
      document.getElementById("view-shop").classList.toggle("active", viewName === "shop");
      document.getElementById("view-tickets").classList.toggle("active", viewName === "tickets");
    }

    function handleImageFileChange(e) {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      if (file.size > 3 * 1024 * 1024) {
        showBanner("Image must be 3 MB or smaller (PNG, JPG, or WebP).", true);
        e.target.value = "";
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        uploadedImageDataUrl = String(reader.result || "");
        const prev = document.getElementById("product-image-preview");
        prev.src = uploadedImageDataUrl;
        prev.style.display = "block";
      };
      reader.readAsDataURL(file);
    }

    async function handleAddItem(e) {
      e.preventDefault();
      const adminPassword = document.getElementById("admin-password").value;
      const imageUrl = document.getElementById("product-image-url").value.trim() || uploadedImageDataUrl;
      const payload = {
        admin_password: adminPassword,
        name: document.getElementById("item-name").value.trim(),
        category: document.getElementById("item-category").value.trim(),
        stock: Math.max(1, Number(document.getElementById("item-stock").value || 1)),
        price: Number(document.getElementById("item-price").value || 0).toFixed(2),
        currency: document.getElementById("item-currency").value,
        posted_by: document.getElementById("item-poster").value.trim() || "@mvn412.",
        description: document.getElementById("item-desc").value.trim(),
        image_url: imageUrl,
      };

      const res = await fetch("/api/shop/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        showBanner(data.error || "Failed to add item (check admin password).", true);
        return;
      }
      shopItems.unshift(data.item);
      renderShopItems();
      document.getElementById("add-item-form").reset();
      document.getElementById("item-stock").value = "1";
      document.getElementById("item-poster").value = "@mvn412.";
      uploadedImageDataUrl = "";
      const prev = document.getElementById("product-image-preview");
      prev.src = "";
      prev.style.display = "none";
      showBanner(`Added "${data.item.name}" & sent item-added webhook!`);
    }

    function makeTicketForItem(itemId) {
      const item = shopItems.find((i) => i.id === itemId);
      if (!item) return;
      switchView("tickets");
      document.getElementById("t1-name").value = item.posted_by.replace(/^@/, "");
      document.getElementById("t1-items").value = `${item.name} (${item.price} ${item.currency})`;
      document.getElementById("t2-items").value = `Direct payment to ${item.posted_by} via ticket`;
      document.getElementById("t-game").value = `${item.category} • ${item.name}`;
      showBanner(`Ticket form pre-filled for "${item.name}". Pay ${item.posted_by} inside your ticket.`);
    }

    async function markItemSold(itemId) {
      const buyerTag = prompt("Enter buyer @username or ticket note for the Sold Webhook:", "@buyer") || "@buyer";
      const res = await fetch(`/api/shop/items/${encodeURIComponent(itemId)}/sold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ buyer: buyerTag }),
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        shopItems = shopItems.map((it) => (it.id === itemId ? data.item : it));
        renderShopItems();
        showBanner(`Marked "${data.item.name}" as SOLD & sent sold webhook!`);
      } else {
        showBanner(data.error || "Could not mark sold.", true);
      }
    }

    function renderShopItems() {
      const grid = document.getElementById("products-grid");
      document.getElementById("shop-item-count").textContent = `${shopItems.length} ITEMS`;
      if (!shopItems.length) {
        grid.innerHTML = `<p style="color:var(--muted);font-size:0.86rem;">No items listed yet. Use <strong>Add a new item</strong> with your admin password.</p>`;
        return;
      }
      grid.innerHTML = shopItems.map((it) => {
        const soldOut = Number(it.stock || 0) <= 0 || it.status === "SOLD";
        const imgSrc = it.image_url || "https://cdn.discordapp.com/embed/avatars/0.png";
        return `
          <div class="product-card">
            <div>
              <div class="product-img-wrap">
                <img src="${escapeHtml(imgSrc)}" alt="${escapeHtml(it.name)}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'" />
                <span class="stock-pill ${soldOut ? "sold-out" : ""}">${soldOut ? "SOLD OUT" : `Stock: ${it.stock}`}</span>
              </div>
              <div class="product-body">
                <div class="product-cat">${escapeHtml(it.category || "Item")}</div>
                <div class="product-title">${escapeHtml(it.name)}</div>
                <div class="product-price">${escapeHtml(it.price)} ${escapeHtml(it.currency || "USD")}</div>
                ${it.description ? `<p class="product-desc">${escapeHtml(it.description)}</p>` : ""}
                <div class="product-seller">Posted by <strong>${escapeHtml(it.posted_by || "@mvn412.")}</strong></div>
              </div>
            </div>
            <div class="product-body" style="padding-top:0;">
              <div class="product-actions">
                <button type="button" class="btn-primary" ${soldOut ? "disabled" : ""} onclick="makeTicketForItem('${escapeHtml(it.id)}')">
                  Make Ticket to Buy
                </button>
                <button type="button" class="btn-secondary" ${soldOut ? "disabled" : ""} onclick="markItemSold('${escapeHtml(it.id)}')">
                  Mark Sold
                </button>
              </div>
            </div>
          </div>
        `;
      }).join("");
    }

    async function handleCloseTicket(e) {
      e.preventDefault();
      const t1Name = document.getElementById("t1-name").value.trim();
      const t2Name = document.getElementById("t2-name").value.trim();
      const claimedRaw = document.getElementById("t-claimed").value.trim();
      const payload = {
        ticket_id: "VX-" + Math.floor(1000 + Math.random() * 9000),
        status: "CLOSED",
        game: document.getElementById("t-game").value.trim() || "Roblox Crosstrade",
        trader_1: {
          name: t1Name,
          mention: "@" + t1Name.replace(/^@/, ""),
          avatar_url: document.getElementById("t1-avatar").value.trim() || "https://cdn.discordapp.com/embed/avatars/0.png",
          giving_items: document.getElementById("t1-items").value.trim(),
        },
        trader_2: {
          name: t2Name,
          mention: "@" + t2Name.replace(/^@/, ""),
          avatar_url: document.getElementById("t2-avatar").value.trim() || "https://cdn.discordapp.com/embed/avatars/1.png",
          giving_items: document.getElementById("t2-items").value.trim(),
        },
        claimed_by: claimedRaw.startsWith("@") ? claimedRaw : "@" + claimedRaw,
      };

      const res = await fetch("/api/tickets/closed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.ok) {
        closedTrades.unshift(data.ticket);
        renderClosedTrades();
        document.getElementById("ticket-form").reset();
        document.getElementById("t-claimed").value = "@mvn412.";
        document.getElementById("t-game").value = "Roblox Crosstrade";
        showBanner(`Closed ticket ${data.ticket.ticket_id} sent to website!`);
      } else {
        showBanner(data.error || "Failed to close ticket.", true);
      }
    }

    function renderClosedTrades() {
      const box = document.getElementById("closed-trades-list");
      document.getElementById("closed-count").textContent = `${closedTrades.length} CLOSED`;
      if (!closedTrades.length) {
        box.innerHTML = `<p style="color:var(--muted);font-size:0.86rem;">No closed tickets yet.</p>`;
        return;
      }
      box.innerHTML = closedTrades.map((t) => `
        <div class="closed-card">
          <div class="closed-head">
            <strong>${escapeHtml(t.ticket_id)} &middot; ${escapeHtml(t.game)}</strong>
            <span style="color:#fbbf24;font-size:0.8rem;font-weight:800;">Claimed by ${escapeHtml(t.claimed_by)}</span>
          </div>
          <div class="traders-row">
            <div class="trader-chip">
              <img src="${escapeHtml(t.trader_1.avatar_url)}" alt="${escapeHtml(t.trader_1.name)}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'" />
              <div>
                <div style="font-size:0.82rem;font-weight:800;">Trader 1: ${escapeHtml(t.trader_1.name)}</div>
                <div style="font-size:0.74rem;color:#cbd5e1;">Gives: ${escapeHtml(t.trader_1.giving_items)}</div>
              </div>
            </div>
            <div class="trader-chip">
              <img src="${escapeHtml(t.trader_2.avatar_url)}" alt="${escapeHtml(t.trader_2.name)}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/1.png'" />
              <div>
                <div style="font-size:0.82rem;font-weight:800;">Trader 2: ${escapeHtml(t.trader_2.name)}</div>
                <div style="font-size:0.74rem;color:#cbd5e1;">Gives: ${escapeHtml(t.trader_2.giving_items)}</div>
              </div>
            </div>
          </div>
        </div>
      `).join("");
    }

    async function loadInitialState() {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          shopItems = data.items || [];
          closedTrades = data.closed_tickets || [];
        }
      } catch {}
      renderShopItems();
      renderClosedTrades();
    }

    loadInitialState();
  </script>
</body>
</html>
"""

# ==============================================================================
# STATE & PERSISTENCE
# ==============================================================================
shop_items: list[dict] = []
closed_tickets: list[dict] = []
active_tickets: dict[int, dict] = {}


def load_db() -> None:
    global shop_items, closed_tickets
    if not DB_FILE.exists():
        shop_items = []
        closed_tickets = []
        return
    try:
        data = json.loads(DB_FILE.read_text(encoding="utf-8"))
        shop_items = data.get("items", []) if isinstance(data.get("items"), list) else []
        closed_tickets = data.get("closed_tickets", []) if isinstance(data.get("closed_tickets"), list) else []
    except Exception:
        shop_items = []
        closed_tickets = []


def save_db() -> None:
    DB_FILE.write_text(
        json.dumps({"items": shop_items[:300], "closed_tickets": closed_tickets[:300]}, indent=2),
        encoding="utf-8",
    )


async def send_discord_webhook(webhook_url: str, payload: dict) -> None:
    if not webhook_url:
        return
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=payload) as resp:
                await resp.text()
    except Exception as exc:
        print(f"Webhook error: {exc}")


async def notify_item_added(item: dict) -> None:
    embed = {
        "title": f"New Shop Item Added • {item['name']}",
        "color": 0x3B82F6,
        "fields": [
            {"name": "Price", "value": f"**{item['price']} {item['currency']}**", "inline": True},
            {"name": "Category", "value": item["category"] or "General", "inline": True},
            {"name": "Stock", "value": str(item["stock"]), "inline": True},
            {"name": "Posted By", "value": item["posted_by"], "inline": True},
            {"name": "Payment Flow", "value": "No upfront site pay — buyer opens a ticket & pays poster", "inline": False},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if item.get("description"):
        embed["description"] = item["description"]
    if item.get("image_url") and item["image_url"].startswith("http"):
        embed["image"] = {"url": item["image_url"]}
    await send_discord_webhook(ITEM_ADDED_WEBHOOK_URL, {"embeds": [embed]})


async def notify_item_sold(item: dict, buyer: str) -> None:
    embed = {
        "title": f"Shop Item Sold • {item['name']}",
        "color": 0x22C55E,
        "fields": [
            {"name": "Price", "value": f"**{item['price']} {item['currency']}**", "inline": True},
            {"name": "Seller (Posted By)", "value": item["posted_by"], "inline": True},
            {"name": "Buyer / Ticket", "value": buyer, "inline": True},
            {"name": "Remaining Stock", "value": str(item["stock"]), "inline": True},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if item.get("image_url") and item["image_url"].startswith("http"):
        embed["thumbnail"] = {"url": item["image_url"]}
    await send_discord_webhook(ITEM_SOLD_WEBHOOK_URL, {"embeds": [embed]})


async def notify_ticket_closed(record: dict) -> None:
    t1 = record["trader_1"]
    t2 = record["trader_2"]
    embed = {
        "title": f"Closed Ticket • {record['ticket_id']}",
        "color": 0xF59E0B,
        "fields": [
            {
                "name": "Trader 1 (Giving)",
                "value": f"**{t1['name']}** ({t1['mention']})\nItems: {t1['giving_items']}",
                "inline": True,
            },
            {
                "name": "Trader 2 (Giving)",
                "value": f"**{t2['name']}** ({t2['mention']})\nItems: {t2['giving_items']}",
                "inline": True,
            },
            {"name": "Claimed By", "value": f"**{record['claimed_by']}**", "inline": False},
        ],
        "timestamp": record.get("closed_at") or datetime.now(timezone.utc).isoformat(),
    }
    if t1.get("avatar_url") and t1["avatar_url"].startswith("http"):
        embed["thumbnail"] = {"url": t1["avatar_url"]}
    await send_discord_webhook(TICKET_CLOSED_WEBHOOK_URL, {"embeds": [embed]})


# ==============================================================================
# AIOHTTP WEB SERVER
# ==============================================================================
async def handle_index(request: web.Request) -> web.Response:
    if HTML_FILE.exists():
        return web.FileResponse(HTML_FILE)
    return web.Response(text=FALLBACK_HTML_PAGE, content_type="text/html")


async def handle_get_state(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "items": shop_items, "closed_tickets": closed_tickets})


async def handle_create_item(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    if str(body.get("admin_password") or "") != SHOP_ADMIN_PASSWORD:
        return web.json_response({"ok": False, "error": "Invalid admin password."}, status=403)

    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Item name is required."}, status=400)

    stock = max(1, int(body.get("stock") or 1))
    posted_by = str(body.get("posted_by") or "@mvn412.").strip()
    if not posted_by.startswith("@"):
        posted_by = f"@{posted_by}"

    item = {
        "id": f"ITM-{uuid.uuid4().hex[:6].upper()}",
        "name": name,
        "category": str(body.get("category") or "General").strip(),
        "stock": stock,
        "price": str(body.get("price") or "0.00").strip(),
        "currency": str(body.get("currency") or "USD").strip(),
        "posted_by": posted_by,
        "description": str(body.get("description") or "").strip(),
        "image_url": str(body.get("image_url") or "").strip(),
        "status": "AVAILABLE",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    shop_items.insert(0, item)
    save_db()
    asyncio.create_task(notify_item_added(item))
    return web.json_response({"ok": True, "item": item}, status=201)


async def handle_mark_item_sold(request: web.Request) -> web.Response:
    item_id = request.match_info.get("item_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    buyer = str(body.get("buyer") or "@buyer").strip()
    if not buyer.startswith("@"):
        buyer = f"@{buyer}"

    for idx, it in enumerate(shop_items):
        if it.get("id") == item_id:
            next_stock = max(0, int(it.get("stock") or 1) - 1)
            updated = {
                **it,
                "stock": next_stock,
                "status": "SOLD" if next_stock == 0 else "AVAILABLE",
                "sold_to": buyer,
                "sold_at": datetime.now(timezone.utc).isoformat(),
            }
            shop_items[idx] = updated
            save_db()
            asyncio.create_task(notify_item_sold(updated, buyer))
            return web.json_response({"ok": True, "item": updated})

    return web.json_response({"ok": False, "error": "Item not found"}, status=404)


async def handle_post_closed_ticket(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    t1 = body.get("trader_1") or {}
    t2 = body.get("trader_2") or {}
    claimed = str(body.get("claimed_by") or "@unassigned").strip()
    if not claimed.startswith("@"):
        claimed = f"@{claimed}"

    record = {
        "ticket_id": str(body.get("ticket_id") or f"VX-{len(closed_tickets) + 1001}"),
        "status": "CLOSED",
        "game": str(body.get("game") or "Roblox Crosstrade"),
        "trader_1": {
            "name": str(t1.get("name") or "Trader 1"),
            "mention": str(t1.get("mention") or f"@{t1.get('name', 'trader1')}"),
            "avatar_url": str(t1.get("avatar_url") or "https://cdn.discordapp.com/embed/avatars/0.png"),
            "giving_items": str(t1.get("giving_items") or ""),
        },
        "trader_2": {
            "name": str(t2.get("name") or "Trader 2"),
            "mention": str(t2.get("mention") or f"@{t2.get('name', 'trader2')}"),
            "avatar_url": str(t2.get("avatar_url") or "https://cdn.discordapp.com/embed/avatars/1.png"),
            "giving_items": str(t2.get("giving_items") or ""),
        },
        "claimed_by": claimed,
        "closed_at": str(body.get("closed_at") or datetime.now(timezone.utc).isoformat()),
    }

    closed_tickets.insert(0, record)
    save_db()
    asyncio.create_task(notify_ticket_closed(record))
    return web.json_response({"ok": True, "ticket": record}, status=201)


async def start_web_server() -> web.AppRunner:
    app = web.Application(client_max_size=5 * 1024 * 1024)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_get_state)
    app.router.add_post("/api/shop/items", handle_create_item)
    app.router.add_post("/api/shop/items/{item_id}/sold", handle_mark_item_sold)
    app.router.add_post("/api/tickets/closed", handle_post_closed_ticket)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    print(f"Web storefront & API running on http://{WEB_HOST}:{WEB_PORT}")
    return runner


# ==============================================================================
# OPTIONAL DISCORD BOT
# ==============================================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


def format_at(user: discord.abc.User | None, fallback: str = "@unknown") -> str:
    if not user:
        s = fallback.strip()
        return s if s.startswith("@") else f"@{s}"
    return f"@{user.name}"


def avatar_of(user: discord.abc.User | None) -> str:
    if user and user.display_avatar:
        return user.display_avatar.url
    return "https://cdn.discordapp.com/embed/avatars/0.png"


async def resolve_user(guild: discord.Guild | None, raw: str) -> tuple[discord.abc.User | None, str]:
    txt = (raw or "").strip()
    if not txt:
        return None, "@unknown"
    digits = "".join(c for c in txt if c.isdigit())
    if guild and len(digits) >= 15:
        uid = int(digits)
        m = guild.get_member(uid)
        if m:
            return m, format_at(m)
        try:
            u = await bot.fetch_user(uid)
            if u:
                return u, format_at(u)
        except Exception:
            pass
    clean = txt.lstrip("@").lower()
    if guild and clean:
        for m in guild.members:
            if m.name.lower() == clean or (m.display_name and m.display_name.lower() == clean):
                return m, format_at(m)
    return None, txt if txt.startswith("@") else f"@{txt}"


async def close_ticket_channel(interaction: discord.Interaction) -> None:
    ch = interaction.channel
    if not isinstance(ch, discord.TextChannel):
        await interaction.response.send_message("Use inside a ticket channel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    tk = active_tickets.get(ch.id, {})
    u1, m1 = await resolve_user(interaction.guild, tk.get("t1_raw", interaction.user.name))
    u2, m2 = await resolve_user(interaction.guild, tk.get("t2_raw", "Trader 2"))
    uc, mc = await resolve_user(interaction.guild, tk.get("claimed_raw") or format_at(interaction.user))

    record = {
        "ticket_id": tk.get("ticket_id", f"VX-{ch.id % 10000:04d}"),
        "status": "CLOSED",
        "game": tk.get("game", "Roblox Crosstrade"),
        "trader_1": {
            "name": u1.display_name if u1 else m1.lstrip("@"),
            "mention": m1,
            "avatar_url": avatar_of(u1),
            "giving_items": tk.get("t1_items", "Confirmed in ticket"),
        },
        "trader_2": {
            "name": u2.display_name if u2 else m2.lstrip("@"),
            "mention": m2,
            "avatar_url": avatar_of(u2),
            "giving_items": tk.get("t2_items", "Confirmed in ticket"),
        },
        "claimed_by": mc,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }

    closed_tickets.insert(0, record)
    save_db()
    active_tickets.pop(ch.id, None)
    await notify_ticket_closed(record)

    if TRANSCRIPT_CHANNEL_ID and interaction.guild:
        log_ch = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
        if isinstance(log_ch, discord.TextChannel):
            emb = discord.Embed(title=f"Closed Ticket • {record['ticket_id']}", color=discord.Color.gold())
            emb.add_field(name="Trader 1", value=f"{record['trader_1']['name']} ({m1})\n{record['trader_1']['giving_items']}", inline=True)
            emb.add_field(name="Trader 2", value=f"{record['trader_2']['name']} ({m2})\n{record['trader_2']['giving_items']}", inline=True)
            emb.add_field(name="Claimed By", value=mc, inline=False)
            emb.set_thumbnail(url=record["trader_1"]["avatar_url"])
            await log_ch.send(embed=emb)

    await interaction.followup.send(f"Closed **{record['ticket_id']}** and sent to website.", ephemeral=True)
    await asyncio.sleep(2)
    try:
        await ch.delete()
    except discord.Forbidden:
        pass


class TicketModal(ui.Modal, title="Open Trade / Shop Ticket"):
    t1 = ui.TextInput(label="Trader 1 (@user or ID)", required=True)
    t1_items = ui.TextInput(label="Trader 1 Giving", required=True)
    t2 = ui.TextInput(label="Trader 2 (@user or ID)", required=True)
    t2_items = ui.TextInput(label="Trader 2 Giving", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            return
        await interaction.response.defer(ephemeral=True)
        u1, m1 = await resolve_user(guild, self.t1.value)
        u2, m2 = await resolve_user(guild, self.t2.value)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for u in (u1, u2):
            if isinstance(u, discord.Member):
                overwrites[u] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if MM_ROLE_ID:
            role = guild.get_role(MM_ROLE_ID)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        cat = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        ch = await guild.create_text_channel(
            name=f"ticket-{interaction.id % 10000:04d}",
            category=cat if isinstance(cat, discord.CategoryChannel) else None,
            overwrites=overwrites,
        )
        active_tickets[ch.id] = {
            "ticket_id": f"VX-{ch.id % 10000:04d}",
            "t1_raw": self.t1.value.strip(),
            "t1_items": self.t1_items.value.strip(),
            "t2_raw": self.t2.value.strip(),
            "t2_items": self.t2_items.value.strip(),
            "claimed_raw": None,
        }
        emb = discord.Embed(title=f"Ticket {active_tickets[ch.id]['ticket_id']}", color=discord.Color.purple())
        emb.add_field(name="Trader 1 Giving", value=f"{m1}\n{self.t1_items.value.strip()}", inline=True)
        emb.add_field(name="Trader 2 Giving", value=f"{m2}\n{self.t2_items.value.strip()}", inline=True)
        emb.add_field(name="Claimed By", value="*Unclaimed*", inline=False)
        await ch.send(embed=emb, view=TicketControlsView())
        await interaction.followup.send(f"Opened {ch.mention}", ephemeral=True)


class PanelView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="vx_open_btn", emoji="🎫")
    async def open_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(TicketModal())


class TicketControlsView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, custom_id="vx_claim_btn", emoji="🛡️")
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if isinstance(interaction.channel, discord.TextChannel):
            claimed = format_at(interaction.user)
            tk = active_tickets.setdefault(interaction.channel.id, {"ticket_id": f"VX-{interaction.channel.id % 10000:04d}"})
            tk["claimed_raw"] = claimed
            await interaction.response.send_message(f"Claimed by **{claimed}**.")

    @ui.button(label="Close & Send to Website", style=discord.ButtonStyle.danger, custom_id="vx_close_btn", emoji="🔒")
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await close_ticket_channel(interaction)


@tree.command(name="ticket-panel", description="Post ticket panel")
async def ticket_panel_cmd(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        embed=discord.Embed(title="VortexShop Tickets", description="Open a ticket to trade or buy items directly from the poster.", color=discord.Color.purple()),
        view=PanelView(),
    )


@tree.command(name="close-ticket", description="Close ticket and send to website")
async def close_ticket_cmd(interaction: discord.Interaction) -> None:
    await close_ticket_channel(interaction)


@bot.event
async def setup_hook() -> None:
    bot.add_view(PanelView())
    bot.add_view(TicketControlsView())
    if GUILD_ID:
        g = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=g)
        await tree.sync(guild=g)
    else:
        await tree.sync()


@bot.event
async def on_ready() -> None:
    print(f"Bot logged in as {bot.user}")


async def main_runner() -> None:
    load_db()
    runner = await start_web_server()
    try:
        if DISCORD_TOKEN:
            await bot.start(DISCORD_TOKEN)
        else:
            print("DISCORD_TOKEN not set — running website & shop API standalone.")
            while True:
                await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main_runner())
