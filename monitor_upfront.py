"""
Upfront.nl Prijs- & Productmonitor
-----------------------------------
Haalt periodiek het volledige productassortiment van upfront.nl op via hun
publieke Shopify /products.json endpoint, slaat prijzen/varianten op, en
stuurt een Telegram-melding zodra er een NIEUW product verschijnt.

De opgeslagen data (products_data.json) wordt gebruikt door:
  - de webpagina (index.html, via GitHub Pages)
  - je Excel Power Query-tool (kan rechtstreeks naar de raw GitHub-URL wijzen)

Vereist environment variables:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

SHOP_URL = "https://upfront.nl/products.json?limit=250"
DATA_FILE = Path(__file__).parent / "products_data.json"
SEEN_FILE = Path(__file__).parent / "seen_products.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Verzendkosten-regels upfront.nl (bevestigd op hun site, 12 aug 2026)
SHIPPING_COST = 4.95
FREE_SHIPPING_THRESHOLD = 59.00


def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def fetch_products():
    """Haalt alle producten + varianten op via Shopify's publieke JSON endpoint."""
    resp = requests.get(SHOP_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for p in data.get("products", []):
        variants = []
        for v in p.get("variants", []):
            variants.append({
                "id": v["id"],
                "title": v.get("title", "Default"),
                "price": float(v.get("price", 0)),
                "available": v.get("available", False),
                "sku": v.get("sku", ""),
            })
        image = p["images"][0]["src"] if p.get("images") else None
        products.append({
            "id": p["id"],
            "title": p["title"],
            "handle": p["handle"],
            "url": f"https://upfront.nl/products/{p['handle']}",
            "product_type": p.get("product_type", ""),
            "image": image,
            "variants": variants,
        })
    return products


def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Geen bot token/chat id ingesteld, melding wordt alleen geprint:")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Telegram] Fout bij versturen: {e}")


def run_check():
    seen = load_seen()

    try:
        products = fetch_products()
    except Exception as e:
        print(f"[Upfront] Fout bij ophalen: {e}")
        return

    new_products = [p for p in products if p["id"] not in seen]

    for p in new_products:
        prices = [v["price"] for v in p["variants"]]
        price_range = f"€{min(prices):.2f}" if len(set(prices)) == 1 else f"€{min(prices):.2f} - €{max(prices):.2f}"
        message = (
            f"🆕 <b>Nieuw product bij Upfront!</b>\n"
            f"{p['title']}\n"
            f"Prijs: {price_range}\n"
            f"{p['url']}"
        )
        send_telegram(message)
        seen.add(p["id"])

    save_seen(seen)

    # Data opslaan voor de webpagina en Excel
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "shipping_cost": SHIPPING_COST,
        "free_shipping_threshold": FREE_SHIPPING_THRESHOLD,
        "products": products,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Check voltooid. {len(new_products)} nieuw(e) product(en) van {len(products)} totaal.")
    return new_products


if __name__ == "__main__":
    run_check()
