import streamlit as st
import requests
import json
import time
import random
from datetime import datetime

st.set_page_config(page_title="Woolies Specials Scanner", page_icon="🛒", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
:root {
    --green:#007837; --green-light:#e6f4ec; --gold:#f5a623;
    --red:#e63946; --bg:#f9f7f4; --card:#fff;
    --text:#1a1a2e; --muted:#6b7280; --border:#e5e7eb;
}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);}
.hero{background:linear-gradient(135deg,var(--green),#004d23);border-radius:16px;
      padding:2rem 2.5rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:1rem;color:#fff;}
.hero h1{font-family:'DM Serif Display',serif;font-size:2.2rem;margin:0;}
.hero p{margin:.3rem 0 0;opacity:.85;font-size:.9rem;}
.stats-row{display:flex;gap:.8rem;margin-bottom:1.2rem;flex-wrap:wrap;}
.stat-pill{border-radius:999px;padding:.35rem .9rem;font-size:.82rem;font-weight:600;
           display:inline-flex;align-items:center;gap:.3rem;border:1.5px solid;}
.stat-pill.green{border-color:var(--green);color:var(--green);background:var(--green-light);}
.stat-pill.gold{border-color:var(--gold);color:#9a6000;background:#fff8ec;}
.stat-pill.red{border-color:var(--red);color:var(--red);background:#fff0f0;}
.stat-pill.gray{border-color:#d1d5db;color:var(--muted);background:#fff;}
.product-card{background:var(--card);border-radius:14px;border:1px solid var(--border);padding:1rem;margin-bottom:.2rem;}
.badge{display:inline-block;background:var(--red);color:#fff;font-size:.68rem;font-weight:700;
       padding:.2rem .5rem;border-radius:999px;text-transform:uppercase;margin-bottom:.5rem;}
.badge.half{background:var(--green);}
.product-img{width:100%;height:120px;object-fit:contain;border-radius:8px;background:var(--bg);margin-bottom:.6rem;}
.product-name{font-size:.83rem;font-weight:500;line-height:1.35;margin-bottom:.5rem;
              display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.price-now{font-family:'DM Serif Display',serif;font-size:1.35rem;color:var(--green);}
.price-was{font-size:.78rem;color:var(--muted);text-decoration:line-through;margin-left:4px;}
.saving{font-size:.73rem;font-weight:600;color:var(--red);margin-top:.15rem;}
.unit-price{font-size:.7rem;color:var(--muted);}
.view-link{font-size:.75rem;color:var(--green);}
</style>
""", unsafe_allow_html=True)


# ── Session ───────────────────────────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    html_hdrs = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    try:
        s.get("https://www.woolworths.com.au/", headers=html_hdrs, timeout=15)
        time.sleep(random.uniform(1.0, 1.8))
        s.get("https://www.woolworths.com.au/shop/browse/specials",
              headers={**html_hdrs, "Referer": "https://www.woolworths.com.au/"}, timeout=15)
        time.sleep(random.uniform(0.8, 1.4))
    except Exception:
        pass
    s.headers.clear()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "Origin": "https://www.woolworths.com.au",
        "Referer": "https://www.woolworths.com.au/shop/browse/specials",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
    })
    return s


# ── Step 1: get specials category node IDs ────────────────────────────────────────
def get_specials_categories(session):
    """
    GET /apis/ui/PiesCategoriesWithSpecials
    Returns {"Categories": [{"NodeId": "...", "Description": "..."}, ...]}
    We want the child NodeIds (leaf categories that have specials).
    """
    resp = session.get(
        "https://www.woolworths.com.au/apis/ui/PiesCategoriesWithSpecials",
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    cats = data.get("Categories") or []

    # Collect all leaf-level node IDs (children of specialsgroup)
    node_ids = []
    for cat in cats:
        if cat.get("NodeId") == "specialsgroup":
            # top-level group — get its children
            for child in (cat.get("Children") or []):
                node_ids.append(child.get("NodeId"))
        elif cat.get("ParentNodeId") == "specialsgroup":
            node_ids.append(cat.get("NodeId"))

    # If we couldn't find children, fall back to top-level IDs excluding root
    if not node_ids:
        node_ids = [
            c.get("NodeId") for c in cats
            if c.get("NodeId") and c.get("NodeId") != "specialsgroup"
        ]

    # If still nothing, use "specialsgroup" itself
    if not node_ids:
        node_ids = ["specialsgroup"]

    return node_ids, resp.text[:400]


# ── Step 2: fetch products for a category ─────────────────────────────────────────
def fetch_category_products(session, node_id, page=1, page_size=36):
    """
    POST /apis/ui/browse/category with a specific categoryId (node_id).
    This is what the Woolworths website does when you click a specials sub-category.
    """
    payload = {
        "categoryId": node_id,
        "pageNumber": page,
        "pageSize": page_size,
        "sortType": "TraderRelevance",
        "url": f"/shop/browse/specials/{node_id}",
        "location": f"/shop/browse/specials/{node_id}?pageNumber={page}",
        "formatObject": json.dumps({"name": "Specials"}),
        "isSpecial": True,
        "isBundle": False,
        "isMobile": False,
        "filters": [],
        "token": "",
        "gpBoost": 0,
        "isHideUnavailableProducts": False,
        "isRegisteredRewardCardPromotion": False,
        "enableAdReRanking": False,
        "groupEdmVariants": True,
        "enableCategoryFacets": True,
    }
    resp = session.post(
        "https://www.woolworths.com.au/apis/ui/browse/category",
        json=payload, timeout=20
    )
    resp.raise_for_status()
    data = resp.json()
    bundles = data.get("Bundles") or []
    items = [p for b in bundles for p in (b.get("Products") or [])]
    total = data.get("TotalRecordCount") or 0
    return items, total


# ── Step 3: parse ─────────────────────────────────────────────────────────────────
def parse_product(p):
    stockcode  = str(p.get("Stockcode") or "")
    name       = p.get("Name") or "Unknown"
    price      = p.get("Price")
    was_price  = p.get("WasPrice")
    save_amt   = p.get("SavingsAmount")
    unit_price = p.get("CupString") or ""
    promo_type = (p.get("PromotionType") or "").lower()

    price_str = f"${price:.2f}"         if price     else "N/A"
    was_str   = f"${was_price:.2f}"     if was_price else ""
    save_str  = f"Save ${save_amt:.2f}" if save_amt  else ""
    disc_pct  = ""
    if price and was_price and was_price > 0:
        disc_pct = f"{round((was_price - price) / was_price * 100)}% off"

    image_url = (
        f"https://cdn0.woolworths.media/content/wowproductimages/large/{stockcode}.jpg"
        if stockcode else ""
    )
    slug = name.lower().replace(" ", "-").replace("/", "-")
    product_url = (
        f"https://www.woolworths.com.au/shop/productdetails/{stockcode}/{slug}"
        if stockcode else "https://www.woolworths.com.au/shop/browse/specials"
    )
    return {
        "name": name, "price": price or 0, "price_str": price_str,
        "was_str": was_str, "save_str": save_str, "disc_pct": disc_pct,
        "unit_price": unit_price, "image_url": image_url,
        "product_url": product_url, "is_half_price": "half" in promo_type,
        "stockcode": stockcode,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def load_all_specials(max_items: int):
    session = make_session()
    debug_lines = []
    errors = []
    seen = set()
    all_products = []

    # Step 1 — get category IDs
    try:
        node_ids, cat_raw = get_specials_categories(session)
        debug_lines.append(f"Categories found: {node_ids}\nRaw: {cat_raw}")
    except Exception as e:
        errors.append(f"Category fetch failed: {e}")
        debug_lines.append(f"❌ Category fetch failed: {e}")
        return [], errors, debug_lines

    if not node_ids:
        errors.append("No specials categories found")
        return [], errors, debug_lines

    # Step 2 — fetch products from each category
    for node_id in node_ids:
        if len(all_products) >= max_items:
            break
        try:
            items, total = fetch_category_products(session, node_id, page=1, page_size=36)
            debug_lines.append(f"✅ Category {node_id}: {len(items)} products (total={total})")

            for p in items:
                sc = str(p.get("Stockcode") or "")
                if sc and sc in seen:
                    continue
                if sc:
                    seen.add(sc)
                all_products.append(parse_product(p))

            time.sleep(random.uniform(0.5, 1.0))
        except requests.HTTPError as e:
            msg = f"❌ Category {node_id}: HTTP {e.response.status_code} — {e.response.text[:150]}"
            debug_lines.append(msg)
            errors.append(msg)
        except Exception as e:
            msg = f"❌ Category {node_id}: {e}"
            debug_lines.append(msg)

    return all_products, errors, debug_lines


# ── Sidebar ───────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Filters")
    search_q   = st.text_input("🔍 Search", placeholder="e.g. chicken, Tim Tam…")
    max_price  = st.slider("Max price ($)", 0.5, 60.0, 60.0, 0.5)
    min_disc   = st.slider("Min discount %", 0, 80, 0, 5)
    half_only  = st.checkbox("Half price only")
    sort_by    = st.selectbox("Sort by", [
        "Biggest saving %", "Lowest price", "Highest saving $", "Name A–Z"])
    max_items  = st.slider("Max products to load", 50, 500, 200, 50)
    debug_mode = st.checkbox("🐛 Debug mode")
    do_refresh = st.button("🔄 Refresh deals", use_container_width=True)
    st.divider()
    st.caption("Data fetched live from woolworths.com.au · Prices may differ in-store.")

if do_refresh:
    st.cache_data.clear()

# ── Header ────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div style="font-size:3rem;line-height:1">🛒</div>
  <div>
    <h1>Woolies Specials Scanner</h1>
    <p>Live deals from woolworths.com.au · refreshes every 30 min</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Fetch ─────────────────────────────────────────────────────────────────────────
with st.spinner("Fetching specials from Woolworths… 🏷️"):
    products, fetch_errors, debug_lines = load_all_specials(max_items)

if debug_mode:
    with st.expander("🐛 Debug info", expanded=True):
        for line in debug_lines:
            st.code(line)

if not products:
    st.error(
        "❌ **Couldn't load specials.** Enable **🐛 Debug mode** and press "
        "**Refresh deals** to see what the API is returning.\n\n"
        "**Common fixes:**\n"
        "- Open [woolworths.com.au](https://www.woolworths.com.au) in your browser, "
        "then press **Refresh deals** here\n"
        "- Disable VPN/proxy\n"
        "- Wait 60 s and retry"
    )
    if st.button("🔄 Retry"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

# ── Filter ────────────────────────────────────────────────────────────────────────
filtered = products[:]
if search_q:
    q = search_q.lower()
    filtered = [p for p in filtered if q in p["name"].lower()]
filtered = [p for p in filtered if p["price"] == 0 or p["price"] <= max_price]
if half_only:
    filtered = [p for p in filtered if p["is_half_price"]]

def get_disc_pct(p):
    if p["was_str"] and p["price"]:
        try:
            was = float(p["was_str"].replace("$", ""))
            return round((was - p["price"]) / was * 100) if was else 0
        except Exception:
            return 0
    return 0

if min_disc > 0:
    filtered = [p for p in filtered if get_disc_pct(p) >= min_disc]

if sort_by == "Lowest price":
    filtered.sort(key=lambda p: p["price"])
elif sort_by == "Name A–Z":
    filtered.sort(key=lambda p: p["name"].lower())
elif sort_by == "Biggest saving %":
    filtered.sort(key=get_disc_pct, reverse=True)
elif sort_by == "Highest saving $":
    def save_dollars(p):
        try:
            return float(p["save_str"].replace("Save $", "")) if p["save_str"] else 0
        except Exception:
            return 0
    filtered.sort(key=save_dollars, reverse=True)

# ── Stats ─────────────────────────────────────────────────────────────────────────
half_count = sum(1 for p in filtered if p["is_half_price"])
pcts = [get_disc_pct(p) for p in filtered if get_disc_pct(p) > 0]
avg_pct = round(sum(pcts) / len(pcts)) if pcts else 0

st.markdown(f"""
<div class="stats-row">
  <span class="stat-pill green">🏷️ {len(filtered)} specials</span>
  <span class="stat-pill gold">⭐ {half_count} half price</span>
  <span class="stat-pill red">💸 avg {avg_pct}% off</span>
  <span class="stat-pill gray">🕐 {datetime.now().strftime("%-I:%M %p")}</span>
</div>
""", unsafe_allow_html=True)

if not filtered:
    st.info("No results match your filters — try adjusting the search or sliders.")
    st.stop()

# ── Grid ──────────────────────────────────────────────────────────────────────────
COLS = 4
for i in range(0, len(filtered), COLS):
    row = filtered[i: i + COLS]
    cols = st.columns(len(row))
    for col, p in zip(cols, row):
        with col:
            badge = (
                '<span class="badge half">½ Price</span><br>' if p["is_half_price"]
                else f'<span class="badge">{p["disc_pct"]}</span><br>' if p["disc_pct"]
                else ""
            )
            img = (
                f'<img src="{p["image_url"]}" class="product-img" '
                'onerror="this.style.display=\'none\'">'
                if p["image_url"] else
                '<div style="height:120px;background:#f3f4f6;border-radius:8px;'
                'display:flex;align-items:center;justify-content:center;'
                'font-size:2rem;margin-bottom:.6rem">🛍️</div>'
            )
            st.markdown(f"""
<div class="product-card">
  {badge}{img}
  <div class="product-name">{p['name']}</div>
  <div>
    <span class="price-now">{p['price_str']}</span>
    <span class="price-was">{p['was_str']}</span>
  </div>
  <div class="saving">{p['save_str']}</div>
  <div class="unit-price">{p['unit_price']}</div>
  <div style="margin-top:.5rem">
    <a href="{p['product_url']}" target="_blank" class="view-link">View on Woolworths ↗</a>
  </div>
</div>""", unsafe_allow_html=True)
