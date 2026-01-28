from __future__ import annotations

import json

def _safe_qty(val):
    """Convert common Uzum numeric-ish qty structures to int."""
    if val is None:
        return 0
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return 0
        try:
            return int(float(s.replace(",", ".")))
        except Exception:
            return 0
    if isinstance(val, dict):
        # Prefer likely keys first
        for k in (
            "quantityActive","quantity","qty","available","availableQty","stock","stockQty","stockQuantity",
            "left","leftQty","leftovers","balance","amount","value","count",
            "warehouseQty","warehouseQuantity","inStock","onStock","onHand","free","total"
        ):
            if k in val:
                q = _safe_qty(val.get(k))
                if q != 0:
                    return q
        # fallback sum
        return sum(_safe_qty(v) for v in val.values())
    if isinstance(val, (list, tuple)):
        return sum(_safe_qty(x) for x in val)
    return 0

def _extract_uzum_qty(obj: dict) -> int:
    """Best-effort quantity extraction.

    Uzum responses are not stable across endpoints/versions. We:
    1) check common direct keys
    2) check common nested containers
    3) do a shallow recursive scan and pick the *best-looking* numeric field
    """
    if not isinstance(obj, dict):
        return 0

    direct_keys = [
        # most common
        "quantityActive",
        "availableAmount", "availableQty", "availableQuantity", "available",
        "stockQty", "stockQuantity", "stock",
        "quantity", "qty",
        # other variants
        "left", "leftQty", "leftovers", "leftover", "remain", "remains", "rest", "balance",
        "warehouseQty", "warehouseQuantity", "freeStock", "free", "onStock", "inStock", "onHand", "on_hand",
        "totalAvailable", "totalQty",
        # our own stored field names
        "uzumQty", "uzumQuantity", "uzum_quantity",
    ]

    for k in direct_keys:
        if k in obj:
            q = _safe_qty(obj.get(k))
            if q != 0:
                return q

    nested_containers = [
        "stocks", "stockList", "warehouseStocks", "warehouseStock",
        "inventories", "inventory", "availability",
        "remainsByWarehouse", "leftoversByWarehouse",
        "warehouse", "warehouses", "stores", "storeStocks",
    ]
    for k in nested_containers:
        if k in obj:
            q = _safe_qty(obj.get(k))
            if q != 0:
                return q

    st = obj.get("status")
    if isinstance(st, dict):
        for k in direct_keys:
            if k in st:
                q = _safe_qty(st.get(k))
                if q != 0:
                    return q
        add = st.get("additional")
        if add is not None:
            q = _safe_qty(add)
            if q != 0:
                return q

    # last-resort recursive scan (bounded)
    best_score = -1
    best_qty = 0

    def _score_key(key: str) -> int:
        k = (key or "").lower()
        score = 0
        if "qty" in k or "quantity" in k:
            score += 5
        if "stock" in k or "remain" in k or "left" in k or "available" in k:
            score += 4
        if "price" in k or "cost" in k or "amount" == k:
            score -= 3
        return score

    def _walk(node, depth: int = 0):
        nonlocal best_score, best_qty
        if depth > 4:
            return
        if isinstance(node, dict):
            for kk, vv in node.items():
                if isinstance(vv, (int, float, str, bool)):
                    q = _safe_qty(vv)
                    if q == 0:
                        continue
                    sc = _score_key(str(kk))
                    # prefer more plausible qty range (avoid gigantic accidental numbers)
                    if q > 1000000:
                        sc -= 2
                    if sc > best_score:
                        best_score, best_qty = sc, q
                else:
                    _walk(vv, depth + 1)
        elif isinstance(node, (list, tuple)):
            for vv in node:
                _walk(vv, depth + 1)

    _walk(obj, 0)
    return int(best_qty or 0)

def _extract_sku(row: dict) -> str:
    """Extract a SKU-like identifier from a row; fallback to barcode/id."""
    if not isinstance(row, dict):
        return ""
    for k in (
        "skuFullTitle", "skuTitle",
        "sku","sellerSku","merchantSku","vendorCode","offerId","article","code","productSku","skuCode",
        "productSkuId","skuId","id","seller_sku","merchant_sku"
    ):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    # fallback to barcode
    for k in ("barcode","ean","gtin"):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    # last resort
    pid = row.get("productId") or row.get("product_id")
    vid = row.get("id") or row.get("skuId")
    if pid or vid:
        return f"{pid or 'p'}-{vid or 'v'}"
    return ""

def _collect_variant_rows(item: dict) -> list:
    """Collect possible variant/SKU rows from an Uzum product item."""
    rows = []
    if isinstance(item, dict):
        # if item itself looks like a SKU row (has barcode or sku-ish keys)
        if any(k in item for k in ("sku","sellerSku","merchantSku","vendorCode","offerId","barcode","skuTitle","skuCode","skuId")):
            rows.append(item)
        # nested lists
        for k in ("skuList","skus","variants","offers","offerList","items","sku_table"):
            v = item.get(k)
            if isinstance(v, list) and v:
                rows.extend([x for x in v if isinstance(x, dict)])
        # sometimes nested under payload/data
        for k in ("payload","data","result"):
            v = item.get(k)
            if isinstance(v, dict):
                for kk in ("skuList","skus","variants","offers","items"):
                    vv = v.get(kk)
                    if isinstance(vv, list) and vv:
                        rows.extend([x for x in vv if isinstance(x, dict)])
    # de-dup by object id
    seen = set()
    out = []
    for r in rows:
        key = id(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

def _safe_status_text(val):
    """Uzum sometimes returns status as an object. SQLite expects TEXT."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        # Prefer human-friendly fields if present
        for k in ("title", "value", "name", "code", "status"):
            if k in val and val[k] is not None:
                return str(val[k])
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, (list, tuple)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)

def _safe_text(val):
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        s = str(val).strip()
        return s if s else None
    return json.dumps(val, ensure_ascii=False)


import os
from datetime import date, datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from sqlalchemy import create_engine, select, func, desc
from sqlalchemy.orm import sessionmaker

from models import Base, Product, Sale, ProductGroup, Variant, VariantSale

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "app.db")
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
Base.metadata.create_all(engine)

app = Flask(__name__)
CORS(app)


# ----------------------------
# Helpers
# ----------------------------
def _json_response(obj, status=200):
    return jsonify(obj), status


def http_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None
    # NOTE: Cloudflare (especially on *.workers.dev) may block default Python user agents
    # with Error 1010 / 403. Use a browser-like UA by default.
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": os.getenv(
            "HTTP_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ),
        "Accept-Language": os.getenv("HTTP_ACCEPT_LANGUAGE", "en-US,en;q=0.9,ru;q=0.8"),
        "Connection": "close",
    }

    # Optional extra headers (JSON) if you need to pass cookies / auth to a protected proxy.
    # Example: HTTP_EXTRA_HEADERS_JSON='{"Cookie":"cf_clearance=..."}'
    try:
        extra = os.getenv("HTTP_EXTRA_HEADERS_JSON", "").strip()
        if extra:
            headers.update(json.loads(extra))
    except Exception:
        pass
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, method=method, data=data, headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {msg}") from e
    except URLError as e:
        raise RuntimeError(f"Network error: {e}") from e


def pick(obj: dict, keys: list[str], default=None):
    for k in keys:
        if obj is None:
            break
        if k in obj and obj[k] not in (None, ""):
            return obj[k]
    return default


def first_list_item(v):
    return v[0] if isinstance(v, list) and v else None


def find_first_array(obj, preferred_keys: list[str]):
    if obj is None:
        return None
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        # preferred keys first
        for k in preferred_keys:
            v = obj.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                found = find_first_array(v, preferred_keys)
                if found is not None:
                    return found
        # walk all values
        for v in obj.values():
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                found = find_first_array(v, preferred_keys)
                if found is not None:
                    return found
    return None


def extract_group_image(p: dict) -> str | None:
    # Check keys in order
    keys = ["image", "imageUrl", "photo", "photoUrl", "thumbnail", "thumbnailUrl", "picture", "preview", "previewImage", "previewImg", "preview_image"]
    
    for k in keys:
        val = p.get(k)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            sub = val.get("url") or val.get("link") or val.get("src") or val.get("path")
            if isinstance(sub, str) and sub:
                return sub

    # Check lists
    for k in ["images", "photos", "pictureUrls", "productImages"]:
        val = p.get(k)
        if isinstance(val, list) and val:
            item = val[0]
            if isinstance(item, str) and item:
                return item
            if isinstance(item, dict):
                sub = item.get("url") or item.get("link") or item.get("src")
                if isinstance(sub, str) and sub:
                    return sub
    return None


def _extract_variant_image(obj: dict) -> str | None:
    """Helper to extract image for a variant, prioritizing preview keys."""
    for k in ["previewImage", "previewImg", "preview_image", "preview", "previewPhoto", "preview_photo", "image", "photo"]:
        val = obj.get(k)
        if isinstance(val, str) and val.strip(): return val.strip()
        if isinstance(val, dict): 
            v = val.get("url") or val.get("link") or val.get("src") or val.get("path")
            if v: return v
        if isinstance(val, list) and val:
            item = val[0]
            if isinstance(item, str) and item: return item.strip()
            if isinstance(item, dict):
                v = item.get("url") or item.get("link") or item.get("src") or item.get("path")
                if v: return v
    return extract_group_image(obj)

def extract_variants(p: dict) -> list[dict]:
    # Uzum product detail often includes a list of SKUs/variants; we search common keys.
    keys = ["skuList", "skus", "variants", "offers", "items", "skuTable"]
    arr = None
    for k in keys:
        if isinstance(p.get(k), list):
            arr = p.get(k)
            break
    if arr is None:
        # Check specific wrappers only. Do NOT use recursive find_first_array here,
        # as it might pick up "relatedProducts" or "similar" lists from other parts of the JSON.
        for wrapper in ["payload", "data", "result", "content"]:
            w = p.get(wrapper)
            if isinstance(w, dict):
                for k in keys:
                    if isinstance(w.get(k), list):
                        arr = w.get(k)
                        break
            if arr:
                break
    return arr if isinstance(arr, list) else []


def variant_sales_last30_map(db, variant_ids: list[int]) -> dict[int, int]:
    if not variant_ids:
        return {}
    since = date.today() - timedelta(days=30)
    stmt = (
        select(VariantSale.variant_id, func.coalesce(func.sum(VariantSale.qty_sold), 0))
        .where(VariantSale.variant_id.in_(variant_ids))
        .where(VariantSale.date >= since)
        .group_by(VariantSale.variant_id)
    )
    return {vid: int(total or 0) for (vid, total) in db.execute(stmt).all()}


# ----------------------------
# Pages (new)
# ----------------------------
@app.get("/")
def home():
    return redirect(url_for("groups_page"))


@app.get("/groups")
def groups_page():
    q = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "active").strip().lower()

    with SessionLocal() as db:
        stmt = select(ProductGroup)
        
        if status_filter == "archived":
            stmt = stmt.where(ProductGroup.is_archived == True)
        else:
            stmt = stmt.where((ProductGroup.is_archived == False) | (ProductGroup.is_archived == None))

        if q:
            like = f"%{q}%"
            stmt = stmt.where(ProductGroup.name.ilike(like))
        stmt = stmt.order_by(ProductGroup.id)

        groups = db.execute(stmt).scalars().all()

        # aggregate counts
        group_ids = [g.id for g in groups]
        vstmt = (
            select(
                Variant.group_id,
                func.count(Variant.id),
                func.coalesce(func.sum(Variant.uzum_quantity), 0),
                func.coalesce(func.sum(Variant.warehouse_quantity), 0),
            )
            .where(Variant.group_id.in_(group_ids) if group_ids else True)
            .group_by(Variant.group_id)
        )
        agg = {gid: {"variants": c, "uzum_qty": int(u), "wh_qty": int(w)} for (gid, c, u, w) in db.execute(vstmt).all()}

    return render_template("groups.html", groups=groups, agg=agg, q=q)


@app.get("/groups/<int:group_id>")
def group_detail(group_id: int):
    with SessionLocal() as db:
        group = db.get(ProductGroup, group_id)
        if not group:
            return render_template("not_found.html", message="Product not found"), 404

        variants = db.execute(
            select(Variant).where(Variant.group_id == group_id).order_by(func.lower(Variant.sku))
        ).scalars().all()

        sales_map = variant_sales_last30_map(db, [v.id for v in variants])

    return render_template("group_detail.html", group=group, variants=variants, sales_map=sales_map)



# ----------------------------
# Product pages (requested)
# ----------------------------
@app.get("/products")
def products_redirect():
    # alias to match "main products page"
    return redirect(url_for("groups_page"))


@app.get("/products/new")
def product_new_form():
    return render_template("group_edit.html", group=None, error=None)


@app.post("/products/new")
def product_new_save():
    form = request.form
    name = (form.get("name") or "").strip()
    if not name:
        return render_template("group_edit.html", group=None, error="Name is required"), 400

    category = (form.get("category") or "").strip() or None
    image_url = (form.get("image_url") or "").strip() or None

    with SessionLocal() as db:
        g = ProductGroup(name=name, category=category, image_url=image_url)
        db.add(g)
        db.commit()
        return redirect(url_for("group_detail", group_id=g.id))


@app.get("/products/<int:group_id>/edit")
def product_edit_form(group_id: int):
    with SessionLocal() as db:
        g = db.get(ProductGroup, group_id)
        if not g:
            return render_template("not_found.html", message="Product not found"), 404
    return render_template("group_edit.html", group=g, error=None)


@app.post("/products/<int:group_id>/edit")
def product_edit_save(group_id: int):
    form = request.form
    with SessionLocal() as db:
        g = db.get(ProductGroup, group_id)
        if not g:
            return _json_response({"error": "Product not found"}, 404)

        name = (form.get("name") or "").strip()
        if name:
            g.name = name
        g.category = (form.get("category") or "").strip() or None
        g.image_url = (form.get("image_url") or "").strip() or None

        db.add(g)
        db.commit()
        return redirect(url_for("group_detail", group_id=g.id))


@app.get("/products/<int:group_id>/skus/new")
def sku_new_form(group_id: int):
    with SessionLocal() as db:
        g = db.get(ProductGroup, group_id)
        if not g:
            return render_template("not_found.html", message="Product not found"), 404
    v = Variant(group_id=group_id, sku="", warehouse_quantity=0, uzum_quantity=0)
    return render_template("variant_edit.html", variant=v, group=g, is_new=True, error=None)


@app.post("/products/<int:group_id>/skus/new")
def sku_new_save(group_id: int):
    form = request.form
    sku = (form.get("sku") or "").strip()
    with SessionLocal() as db:
        g = db.get(ProductGroup, group_id)
        if not g:
            return _json_response({"error": "Product not found"}, 404)

        if not sku:
            v = Variant(group_id=group_id, sku="")
            return render_template("variant_edit.html", variant=v, group=g, is_new=True, error="SKU is required"), 400

        existing = db.execute(select(Variant).where(Variant.group_id == group_id, Variant.sku == sku)).scalar_one_or_none()
        if existing:
            return redirect(url_for("variant_edit_form", variant_id=existing.id))

        v = Variant(group_id=group_id, sku=sku)
        v.barcode = (form.get("barcode") or "").strip() or None
        v.color = (form.get("color") or "").strip() or None
        v.size = (form.get("size") or "").strip() or None
        v.status = _safe_status_text((form.get("status") or "").strip() or None)
        try:
            v.warehouse_quantity = int(form.get("warehouse_quantity") or 0)
        except ValueError:
            v.warehouse_quantity = 0

        db.add(v)
        db.commit()
        return redirect(url_for("group_detail", group_id=group_id))


@app.get("/variants/<int:variant_id>/edit")
def variant_edit_form(variant_id: int):
    with SessionLocal() as db:
        v = db.get(Variant, variant_id)
        if not v:
            return render_template("not_found.html", message="Variant not found"), 404
        group = db.get(ProductGroup, v.group_id)
    return render_template("variant_edit.html", variant=v, group=group)


@app.post("/variants/<int:variant_id>/edit")
def variant_edit_save(variant_id: int):
    form = request.form
    with SessionLocal() as db:
        v = db.get(Variant, variant_id)
        if not v:
            return _json_response({"error": "Variant not found"}, 404)

        v.sku = (form.get("sku") or v.sku).strip()
        v.barcode = (form.get("barcode") or "").strip() or None
        v.color = (form.get("color") or "").strip() or None
        v.size = (form.get("size") or "").strip() or None
        v.status = _safe_status_text((form.get("status") or "").strip() or None)

        try:
            v.warehouse_quantity = int(form.get("warehouse_quantity") or 0)
        except ValueError:
            v.warehouse_quantity = 0

        db.add(v)
        db.commit()
        return redirect(url_for("group_detail", group_id=v.group_id))


# ----------------------------
# Uzum sync API (new)
# ----------------------------
@app.post("/api/uzum/sync")
def uzum_sync():
    payload = request.get_json(force=True, silent=True) or {}
    worker_base = (payload.get("worker_base") or os.environ.get("UZUM_WORKER_BASE") or "https://uzum-api.ulugbek2003-09-09-pp.workers.dev").strip().rstrip("/")
    shop_id = str(payload.get("shop_id") or "").strip()

    if not worker_base:
        return _json_response({"error": "worker_base missing (or set UZUM_WORKER_BASE env var)"}, 400)
    if not shop_id:
        return _json_response({"error": "shop_id missing"}, 400)

    size = int(payload.get("size") or 50)
    sync_all = bool(payload.get("sync_all", True))
    max_pages = int(payload.get("max_pages") or 500)

    preferred_root_keys = ["productList", "items", "products", "list", "rows", "content"]

    fetched_products = 0
    pages = 0

    with SessionLocal() as db:
        page = 0
        while True:
            url = f"{worker_base}/v1/product/shop/{shop_id}?page={page}&size={size}"
            raw = http_json(url)

            items = find_first_array(raw, preferred_root_keys) or []
            if not isinstance(items, list):
                items = []

            pages += 1
            fetched_products += len(items)

            # Upsert groups + variants
            for p in items:
                uzum_product_id = str(pick(p, ["productId", "id", "product_id"], default="")).strip() or None
                # Ignore placeholder ID "0" to prevent merging different products
                if uzum_product_id in ("0", "0.0"):
                    uzum_product_id = None

                name = (
                    pick(p, ["name", "title", "productName", "fullName"], default=None)
                    or pick(p.get("status") or {}, ["title"], default=None)
                    or f"Product {uzum_product_id or ''}".strip()
                )
                category = pick(p, ["category"], default=None)
                image_url = extract_group_image(p)
                parent_preview = _extract_variant_image(p)

                # Check for archived status
                is_archived = False
                # 1. Check explicit 'archived' field (bool or string)
                val_archived = p.get("archived")
                if val_archived is True or (isinstance(val_archived, str) and val_archived.lower() == "true"):
                    is_archived = True
                # 2. Check 'status' field
                
                # 1. Check explicit keys (archived, archive, isArchived)
                for k in ["archived", "archive", "isArchived", "is_archived"]:
                    val = p.get(k)
                    if val is True:
                        is_archived = True
                        break
                    if isinstance(val, str) and val.lower() in ("true", "1", "yes"):
                        is_archived = True
                        break
                    if isinstance(val, int) and val == 1:
                        is_archived = True
                        break

                # 2. Check 'status' object/string
                if not is_archived:
                    raw_status = p.get("status")
                    if isinstance(raw_status, str) and raw_status.upper() in ("ARCHIVED", "TRASH", "DELETED"):
                        is_archived = True
                    elif isinstance(raw_status, dict):
                        if (raw_status.get("code") or "").upper() == "ARCHIVED" or (raw_status.get("title") or "").upper() == "ARCHIVED":
                            is_archived = True

                # group key: prefer uzum_product_id, else name
                group = None
                if uzum_product_id:
                    group = db.execute(select(ProductGroup).where(ProductGroup.uzum_product_id == uzum_product_id)).scalar_one_or_none()
                
                # Only fallback to name if we DO NOT have a valid uzum_product_id.
                # If we have an ID, we assume it defines uniqueness. Merging by name causes mixing.
                if not group and not uzum_product_id:
                    group = db.execute(select(ProductGroup).where(ProductGroup.name == name)).scalar_one_or_none()

                if not group:
                    group = ProductGroup(uzum_product_id=uzum_product_id, name=name, category=category, image_url=image_url, is_archived=is_archived)
                else:
                    group.name = name
                    group.category = category or group.category
                    group.image_url = image_url or group.image_url
                    group.is_archived = is_archived
                    if uzum_product_id and not group.uzum_product_id:
                        group.uzum_product_id = uzum_product_id

                db.add(group)
                db.flush()  # get group.id

                variants = extract_variants(p)
                if variants:
                    for s in variants:
                        sku = _extract_sku(s)


                        barcode = (
                            pick(s, ["barcode"], default=None)
                            or first_list_item(s.get("barcodes") or [])
                            or first_list_item(s.get("barcodeList") or [])
                        )
                        color = pick(s, ["color"], default=None)
                        size_v = pick(s, ["size"], default=None)
                        status = pick(s, ["status"], default=None) or pick(s.get("status") or {}, ["title"], default=None)
                        price = pick(s, ["price", "priceSum", "price_sum"], default=None)
                        uz_qty = pick(s, ["quantityActive", "availableAmount", "availableQty", "availableQuantity", "available", "quantity", "qty", "stock", "remain"], default=None)
                        avg_sales = pick(s, ["avgdsales", "averageDailySales"], default=0)
                        
                        v_img = _extract_variant_image(s)
                        if not sku:
                            continue

                        v = db.execute(
                            select(Variant).where(Variant.group_id == group.id, Variant.sku == sku)
                        ).scalar_one_or_none()

                        if not v:
                            v = Variant(group_id=group.id, sku=sku)

                        v.barcode = str(barcode).strip() if barcode else v.barcode
                        v.color = color or v.color
                        v.size = size_v or v.size
                        v.status = _safe_status_text(status or v.status)
                        v.image_url = v_img or parent_preview or v.image_url
                        if avg_sales is not None:
                            try:
                                v.avg_daily_sales = float(avg_sales)
                            except:
                                v.avg_daily_sales = 0.0
                        if price is not None:
                            try:
                                v.price_sum = int(price)
                            except Exception:
                                pass
                        # Uzum stock/qty can appear in many shapes. Prefer the direct value if present,
                        # otherwise run a best-effort extractor over the whole variant payload.
                        if uz_qty is not None:
                            try:
                                v.uzum_quantity = int(uz_qty)
                            except Exception:
                                v.uzum_quantity = _extract_uzum_qty(s)
                        else:
                            # still attempt to infer from nested structures
                            v.uzum_quantity = _extract_uzum_qty(s) or (v.uzum_quantity or 0)

                        db.add(v)
                else:
                    # If no explicit variants, create one variant per product



                    sku = _extract_sku(p) or (uzum_product_id or name)
                    barcode = pick(p, ["barcode"], default=None) or first_list_item(p.get("barcodes") or [])
                    uz_qty = pick(p, ["quantityActive", "availableAmount", "availableQty", "availableQuantity", "available", "quantity", "qty", "stock", "remain"], default=None)
                    
                    avg_sales = pick(p, ["avgdsales", "averageDailySales"], default=0)
                    v_img = _extract_variant_image(p)

                    v = db.execute(select(Variant).where(Variant.group_id == group.id, Variant.sku == sku)).scalar_one_or_none()
                    if not v:
                        v = Variant(group_id=group.id, sku=sku)
                    if barcode:
                        v.barcode = str(barcode).strip()
                    v.image_url = v_img or parent_preview or v.image_url
                    if avg_sales is not None:
                        try:
                            v.avg_daily_sales = float(avg_sales)
                        except:
                            v.avg_daily_sales = 0.0
                    if uz_qty is not None:
                        try:
                            v.uzum_quantity = int(uz_qty)
                        except Exception:
                            v.uzum_quantity = _extract_uzum_qty(p)
                    else:
                        v.uzum_quantity = _extract_uzum_qty(p) or (v.uzum_quantity or 0)
                    db.add(v)

            db.commit()

            # Stop conditions
            if not sync_all:
                break
            if len(items) < size:
                break
            if pages >= max_pages:
                break
            page += 1

    return _json_response({"ok": True, "shop_id": shop_id, "pages_synced": pages, "fetched": fetched_products})


@app.get("/api/groups/<int:group_id>/variants")
def get_group_variants_api(group_id: int):
    with SessionLocal() as db:
        variants = db.execute(
            select(Variant).where(Variant.group_id == group_id).order_by(func.lower(Variant.sku))
        ).scalars().all()
        return _json_response({
            "variants": [{
                "id": v.id,
                "sku": v.sku,
                "image_url": v.image_url,
                "sales_30d": int((v.avg_daily_sales or 0) * 30)
            } for v in variants]
        })


@app.post("/api/variants/<int:variant_id>/sales")
def add_variant_sale(variant_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        qty = int(payload.get("qty") or 0)
    except ValueError:
        qty = 0
    if qty <= 0:
        return _json_response({"error": "qty must be > 0"}, 400)

    try:
        sale_date = payload.get("date")
        d = date.fromisoformat(sale_date) if sale_date else date.today()
    except Exception:
        d = date.today()

    with SessionLocal() as db:
        v = db.get(Variant, variant_id)
        if not v:
            return _json_response({"error": "Variant not found"}, 404)
        s = VariantSale(variant_id=variant_id, date=d, qty_sold=qty)
        db.add(s)
        db.commit()
        return _json_response({"ok": True})


@app.get("/api/products/<int:variant_id>")
def get_product_detail_api(variant_id: int):
    with SessionLocal() as db:
        row = db.execute(
            select(Variant, ProductGroup)
            .join(ProductGroup, Variant.group_id == ProductGroup.id)
            .where(Variant.id == variant_id)
        ).first()
        
        if not row:
            return _json_response({"error": "Product not found"}, 404)
        
        v, g = row
        name = g.name
        attrs = []
        if v.color: attrs.append(v.color)
        if v.size: attrs.append(v.size)
        if attrs:
            name += f" ({', '.join(attrs)})"

        return _json_response({
            "id": v.id,
            "name": name,
            "sku": v.sku,
            "barcode": v.barcode,
            "quantity": v.warehouse_quantity,
            "image_url": v.image_url or g.image_url,
            "created_at": v.created_at.isoformat(),
            "updated_at": v.updated_at.isoformat(),
        })


@app.put("/api/products/<int:variant_id>")
def update_product_api(variant_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    with SessionLocal() as db:
        v = db.get(Variant, variant_id)
        if not v:
            return _json_response({"error": "Product not found"}, 404)
        
        if "quantity" in payload:
            try:
                v.warehouse_quantity = int(payload["quantity"])
            except:
                pass
        if "barcode" in payload:
            v.barcode = str(payload["barcode"]).strip() or None
        if "sku" in payload:
            v.sku = str(payload["sku"]).strip()
        
        db.commit()
        return _json_response({"ok": True})


@app.delete("/api/products/<int:variant_id>")
def delete_product_api(variant_id: int):
    with SessionLocal() as db:
        v = db.get(Variant, variant_id)
        if not v:
            return _json_response({"error": "Product not found"}, 404)
        db.delete(v)
        db.commit()
        return _json_response({"ok": True})


# ----------------------------
# Legacy API (kept)
# ----------------------------
def product_to_dict(p: Product, last30_sales: int = 0):
    return {
        "id": p.id,
        "name": p.name,
        "sku": p.sku,
        "barcode": p.barcode,
        "quantity": p.quantity,
        "image_url": p.image_url,
        "last30_sales": last30_sales,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@app.get("/api/health")
def health():
    return _json_response({"ok": True, "db": "sqlite", "db_path": DB_PATH})


@app.get("/api/products")
def get_products():
    q = (request.args.get("q") or "").strip()
    days = int(request.args.get("days") or 30)
    since = date.today() - timedelta(days=days)

    with SessionLocal() as db:
        # Return Variants (synced data) instead of legacy Products
        sales_subq = (
            select(VariantSale.variant_id, func.coalesce(func.sum(VariantSale.qty_sold), 0).label("sales_sum"))
            .where(VariantSale.date >= since)
            .group_by(VariantSale.variant_id)
            .subquery()
        )

        stmt = (
            select(
                Variant, 
                ProductGroup, 
                func.coalesce(sales_subq.c.sales_sum, 0).label("sales_sum")
            )
            .join(ProductGroup, Variant.group_id == ProductGroup.id)
            .outerjoin(sales_subq, Variant.id == sales_subq.c.variant_id)
        )

        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                ProductGroup.name.ilike(like) | 
                Variant.sku.ilike(like) | 
                Variant.barcode.ilike(like)
            )

        stmt = stmt.order_by(Variant.id)
        rows = db.execute(stmt).all()

        items = []
        for v, g, s_sum in rows:
            name = g.name
            attrs = []
            if v.color: attrs.append(v.color)
            if v.size: attrs.append(v.size)
            if attrs:
                name += f" ({', '.join(attrs)})"

            items.append({
                "id": v.id,
                "name": name,
                "sku": v.sku,
                "barcode": v.barcode,
                "quantity": v.warehouse_quantity,
                "image_url": v.image_url or g.image_url,
                "last30_sales": int(s_sum),
                "created_at": v.created_at.isoformat(),
                "updated_at": v.updated_at.isoformat(),
            })

        return _json_response({
            "days": days,
            "items": items
        })


# ----------------------------
# Static templates
# ----------------------------
@app.get("/api/summary")
def summary():
    days = int(request.args.get("days") or 30)
    since = date.today() - timedelta(days=days)

    with SessionLocal() as db:
        # Return top selling variants for the summary table
        sales_subq = (
            select(VariantSale.variant_id, func.coalesce(func.sum(VariantSale.qty_sold), 0).label("sales_sum"))
            .where(VariantSale.date >= since)
            .group_by(VariantSale.variant_id)
            .subquery()
        )

        stmt = (
            select(Variant, ProductGroup, sales_subq.c.sales_sum)
            .join(ProductGroup, Variant.group_id == ProductGroup.id)
            .join(sales_subq, Variant.id == sales_subq.c.variant_id)
            .order_by(desc(sales_subq.c.sales_sum))
            .limit(50)
        )
        rows = db.execute(stmt).all()
        
        items = []
        for v, g, s_sum in rows:
            items.append({
                "id": v.id,
                "name": g.name,
                "sku": v.sku,
                "barcode": v.barcode,
                "quantity": v.warehouse_quantity,
                "image_url": v.image_url or g.image_url,
                "last30_sales": int(s_sum),
            })

    return _json_response({
        "days": days,
        "items": items
    })


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
