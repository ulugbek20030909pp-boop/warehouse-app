/* Simple, dependency-free frontend using Bootstrap + fetch */

const styleSheet = document.createElement("style");
styleSheet.innerText = `
  .product-img, .card-img-top, .card-img, .card img {
    width: 100% !important;
    height: auto !important;
    aspect-ratio: 3/4 !important;
    object-fit: cover !important;
  }
`;
document.head.appendChild(styleSheet);

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
};

const state = {
  products: [],
  selected: null,
  days: 30
};

const productModal = new bootstrap.Modal($("#productModal"));
const saleModal = new bootstrap.Modal($("#saleModal"));
const summaryModal = new bootstrap.Modal($("#summaryModal"));

function showAlert(message, type = "danger", timeoutMs = 4500) {
  const area = $("#alertArea");
  const wrap = el("div", `alert alert-${type} alert-dismissible fade show`);
  wrap.role = "alert";
  wrap.innerHTML = `
    <div>${message}</div>
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;
  area.appendChild(wrap);
  if (timeoutMs) setTimeout(() => wrap.remove(), timeoutMs);
}

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function esc(s) {
  return (s ?? "").toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (body && body.error) ? body.error : (typeof body === "string" ? body : "Request failed");
    throw new Error(msg);
  }
  return body;
}

function renderSkeleton() {
  const grid = $("#productsGrid");
  grid.innerHTML = "";
  for (let i = 0; i < 8; i++) {
    const col = el("div", "col-12 col-sm-6 col-lg-4 col-xl-3");
    const sk = el("div", "skeleton");
    col.appendChild(sk);
    grid.appendChild(col);
  }
}

function renderProducts() {
  const grid = $("#productsGrid");
  const items = state.products;
  $("#countLabel").textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;

  grid.innerHTML = "";
  if (!items.length) {
    const empty = el("div", "col-12");
    empty.innerHTML = `
      <div class="p-4 rounded-4 border bg-white text-center">
        <div class="fw-semibold">No products yet</div>
        <div class="text-secondary">Click “Add Product” to create your first item.</div>
      </div>`;
    grid.appendChild(empty);
    return;
  }

  for (const p of items) {
    const col = el("div", "col-12 col-sm-6 col-lg-4 col-xl-3");
    const card = el("div", "card product-card");
    const img = p.image_url
      ? `<img class="product-img" style="width: 100%; height: auto; aspect-ratio: 3/4; object-fit: cover;" src="${esc(p.image_url)}" alt="product">`
      : `<div class="product-img d-flex align-items-center justify-content-center text-secondary small" style="width: 100%; aspect-ratio: 3/4; background: #f8f9fa;">No image</div>`;

    const skuImg = p.image_url ? `<img src="${esc(p.image_url)}" style="width: 20px; height: 27px; object-fit: cover; margin-right: 6px; vertical-align: middle; border-radius: 2px;">` : "";
    const sku = p.sku ? `<div class="mono d-flex align-items-center mt-1">${skuImg}<div><span class="text-secondary">SKU:</span> ${esc(p.sku)}</div></div>` : "";
    const barcode = p.barcode ? `<div class="mono"><span class="text-secondary">Barcode:</span> ${esc(p.barcode)}</div>` : "";
    const last30 = Number(p.last_30_days_sales ?? 0);

    card.innerHTML = `
      ${img}
      <div class="card-body">
        <div class="d-flex justify-content-between gap-2">
          <div class="fw-semibold text-truncate" title="${esc(p.name)}">${esc(p.name)}</div>
          <span class="badge badge-soft">${last30} / 30d</span>
        </div>
        <div class="mt-2 small text-secondary">Stock</div>
        <div class="fs-4 fw-semibold">${Number(p.quantity ?? 0)}</div>
        <div class="mt-2">${sku} ${barcode}</div>
      </div>
      <div class="card-footer bg-white border-0 pt-0">
        <button class="btn btn-outline-primary w-100" data-id="${p.id}">Open</button>
      </div>
    `;

    card.querySelector("button").addEventListener("click", () => openProduct(p.id));
    col.appendChild(card);
    grid.appendChild(col);
  }
}

async function loadProducts() {
  renderSkeleton();
  const q = ($("#searchInput").value || "").trim();
  const sort = $("#sortSelect").value;
  const dir = $("#dirSelect").value;

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("sort", sort);
  params.set("dir", dir);
  params.set("days", String(state.days));

  const data = await api(`/api/products?${params.toString()}`);
  state.products = data.items || [];
  renderProducts();
}

function fillProductForm(p) {
  $("#productId").value = p?.id ?? "";
  $("#name").value = p?.name ?? "";
  $("#sku").value = p?.sku ?? "";
  $("#barcode").value = p?.barcode ?? "";
  $("#quantity").value = (p?.quantity ?? 0);
  $("#image_url").value = p?.image_url ?? "";
}

function setProductModalMode(mode, p) {
  const isEdit = mode === "edit";
  $("#productModalTitle").textContent = isEdit ? "Edit Product" : "Add Product";
  $("#btnDelete").style.display = isEdit ? "inline-block" : "none";
  $("#btnAddSale").disabled = !isEdit;
  $("#salesArea").innerHTML = isEdit ? `<div class="text-secondary small">Loading sales…</div>` : `<div class="text-secondary small">Save product first to add sales.</div>`;
}

async function openProduct(id) {
  try {
    const p = await api(`/api/products/${id}`);
    state.selected = p;
    fillProductForm(p);
    setProductModalMode("edit", p);
    productModal.show();
    await loadSales(id);
  } catch (e) {
    showAlert(e.message);
  }
}

async function loadSales(productId) {
  try {
    const data = await api(`/api/products/${productId}/sales?days=${state.days}`);
    const items = data.items || [];
    const total = data.total_qty_sold ?? 0;

    const wrap = el("div");
    wrap.innerHTML = `
      <div class="d-flex justify-content-between align-items-center mt-2">
        <div class="small text-secondary">Last ${state.days} days total:</div>
        <div class="fw-semibold">${total}</div>
      </div>
      <div class="table-responsive mt-2">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th style="width: 45%;">Date</th>
              <th style="width: 35%;">Qty sold</th>
              <th style="width: 20%;">ID</th>
            </tr>
          </thead>
          <tbody>
            ${items.length ? items.map(s => `
              <tr>
                <td>${esc(s.date)}</td>
                <td class="fw-semibold">${Number(s.qty_sold)}</td>
                <td class="mono text-secondary">${Number(s.id)}</td>
              </tr>
            `).join("") : `<tr><td colspan="3" class="text-secondary small">No sales in the last ${state.days} days.</td></tr>`}
          </tbody>
        </table>
      </div>
    `;
    $("#salesArea").innerHTML = "";
    $("#salesArea").appendChild(wrap);
  } catch (e) {
    $("#salesArea").innerHTML = `<div class="text-danger small">${esc(e.message)}</div>`;
  }
}

async function saveProduct() {
  const id = ($("#productId").value || "").trim();
  const payload = {
    name: ($("#name").value || "").trim(),
    sku: ($("#sku").value || "").trim(),
    barcode: ($("#barcode").value || "").trim(),
    quantity: Number($("#quantity").value || 0),
    image_url: ($("#image_url").value || "").trim(),
  };

  if (!payload.name) {
    showAlert("Name is required.", "warning");
    return;
  }

  try {
    if (id) {
      await api(`/api/products/${id}`, { method: "PUT", body: JSON.stringify(payload) });
      showAlert("Product updated.", "success", 2500);
    } else {
      await api(`/api/products`, { method: "POST", body: JSON.stringify(payload) });
      showAlert("Product created.", "success", 2500);
    }
    productModal.hide();
    await loadProducts();
  } catch (e) {
    showAlert(e.message);
  }
}

async function deleteProduct() {
  const id = ($("#productId").value || "").trim();
  if (!id) return;

  const ok = confirm("Delete this product? This will also delete its sales history.");
  if (!ok) return;

  try {
    await api(`/api/products/${id}`, { method: "DELETE" });
    showAlert("Product deleted.", "success", 2500);
    productModal.hide();
    await loadProducts();
  } catch (e) {
    showAlert(e.message);
  }
}

function openAddProduct() {
  state.selected = null;
  fillProductForm(null);
  setProductModalMode("add", null);
  productModal.show();
}

function openAddSale() {
  $("#saleDate").value = todayISO();
  $("#saleQty").value = 1;
  saleModal.show();
}

async function saveSale() {
  const id = ($("#productId").value || "").trim();
  if (!id) return;

  const payload = {
    date: ($("#saleDate").value || "").trim(),
    qty_sold: Number($("#saleQty").value || 1)
  };

  try {
    await api(`/api/products/${id}/sales`, { method: "POST", body: JSON.stringify(payload) });
    saleModal.hide();
    showAlert("Sale added.", "success", 2500);
    await openProduct(Number(id)); // reload product + sales
    await loadProducts();          // update cards (last30 + quantity if auto decrease)
  } catch (e) {
    showAlert(e.message);
  }
}

async function openSummary() {
  try {
    $("#summaryBody").innerHTML = `<div class="text-secondary small">Loading…</div>`;
    summaryModal.show();

    const data = await api(`/api/summary?days=${state.days}`);
    const items = data.items || [];
    const totalAll = items.reduce((a, p) => a + Number(p.last_30_days_sales ?? 0), 0);

    const table = `
      <div class="d-flex justify-content-between align-items-center mb-2">
        <div class="text-secondary small">Total sold (all products) in last ${state.days} days</div>
        <div class="fw-semibold">${totalAll}</div>
      </div>
      <div class="table-responsive">
        <table class="table table-sm table-striped align-middle">
          <thead>
            <tr>
              <th>Name</th>
              <th class="text-end">Sold / ${state.days}d</th>
              <th class="text-end">Stock</th>
              <th>Img</th>
              <th>SKU</th>
              <th>Barcode</th>
            </tr>
          </thead>
          <tbody>
            ${items.length ? items.map(p => `
              <tr>
                <td class="fw-semibold">${esc(p.name)}</td>
                <td class="text-end">${Number(p.last_30_days_sales ?? 0)}</td>
                <td class="text-end">${Number(p.quantity ?? 0)}</td>
                <td>
                  ${p.image_url ? `<img src="${esc(p.image_url)}" class="table-img" style="width: 30px; aspect-ratio: 3/4; object-fit: cover;">` : ""}
                </td>
                <td class="mono">${esc(p.sku || "")}</td>
                <td class="mono">${esc(p.barcode || "")}</td>
              </tr>
            `).join("") : `<tr><td colspan="5" class="text-secondary small">No data</td></tr>`}
          </tbody>
        </table>
      </div>
    `;
    $("#summaryBody").innerHTML = table;
  } catch (e) {
    $("#summaryBody").innerHTML = `<div class="text-danger">${esc(e.message)}</div>`;
  }
}

function attachEvents() {
  $("#btnAdd").addEventListener("click", openAddProduct);
  $("#btnRefresh").addEventListener("click", loadProducts);
  $("#btnSummary").addEventListener("click", openSummary);

  $("#btnSave").addEventListener("click", saveProduct);
  $("#btnDelete").addEventListener("click", deleteProduct);

  $("#btnAddSale").addEventListener("click", openAddSale);
  $("#btnSaveSale").addEventListener("click", saveSale);

  // Sticky header logic removed to avoid conflict with uzum_ui.js

  let t = null;
  $("#searchInput").addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(loadProducts, 250);
  });
  $("#sortSelect").addEventListener("change", loadProducts);
  $("#dirSelect").addEventListener("change", loadProducts);
}

async function init() {
  attachEvents();
  try {
    await api("/api/health");
    $("#dbStatus").textContent = "DB: SQLite ✓";
  } catch (_) {
    $("#dbStatus").textContent = "DB: offline";
  }
  await loadProducts();
}

init();
