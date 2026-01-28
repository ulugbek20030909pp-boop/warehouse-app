(function () {
  // Inject CSS to fix image aspect ratio globally (3:4)
  const style = document.createElement("style");
  style.innerHTML = `
    .card-img-top, .product-img, .card img {
      width: 100% !important;
      height: auto !important;
      aspect-ratio: 3/4 !important;
      object-fit: cover !important;
    }
    /* Small table image with 3:4 aspect ratio */
    .table-img {
      width: 40px !important;
      height: auto !important;
      aspect-ratio: 3/4 !important;
      object-fit: cover !important;
    }
  `;
  document.head.appendChild(style);

  const $ = (id) => document.getElementById(id);

  function initUzumUI() {
    // 1. Create a dedicated Top Bar container
    const topBar = document.createElement("div");
    topBar.id = "uzumTopBar";
    Object.assign(topBar.style, {
      position: "fixed", top: "0", left: "0", width: "100%",
      zIndex: "1050", backgroundColor: "#fff", padding: "10px 15px",
      boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
      display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap"
    });

    // 2. Move Search Form into Top Bar
    const searchInput = document.querySelector("input[name='q']");
    if (searchInput) {
      const form = searchInput.closest("form");
      if (form) {
        form.style.margin = "0"; // Reset margins
        topBar.appendChild(form); // Move form to top bar

        const urlParams = new URLSearchParams(window.location.search);
        const currentStatus = urlParams.get("status") || "active";
        const currentQ = urlParams.get("q") || "";

        const btnGroup = document.createElement("div");
        btnGroup.className = "btn-group ms-2";
        btnGroup.role = "group";

        const makeBtn = (label, val) => {
          const isActive = currentStatus === val;
          const a = document.createElement("a");
          a.className = `btn btn-sm ${isActive ? "btn-primary" : "btn-outline-primary"}`;
          a.textContent = label;
          let href = `?status=${val}`;
          if (currentQ) href += `&q=${encodeURIComponent(currentQ)}`;
          a.href = href;
          return a;
        };

        btnGroup.appendChild(makeBtn("Active", "active"));
        btnGroup.appendChild(makeBtn("Archived", "archived"));
        form.appendChild(btnGroup);
      }
    }

    // 3. Move Add Product & Uzum Sync Button into Top Bar (Right side)
    const rightContainer = document.createElement("div");
    rightContainer.className = "ms-auto d-flex gap-2 align-items-center";
    
    const btnAdd = $("btnAdd");
    if (btnAdd) {
      if (!btnAdd.classList.contains("btn")) btnAdd.classList.add("btn", "btn-primary", "btn-sm");
      rightContainer.appendChild(btnAdd);
    }

    const btnUzumToggle = document.createElement("button");
    btnUzumToggle.className = "btn btn-outline-secondary btn-sm";
    btnUzumToggle.textContent = "Uzum Sync";
    btnUzumToggle.type = "button";
    rightContainer.appendChild(btnUzumToggle);

    topBar.appendChild(rightContainer);

    // 4. Create Dropdown for Shop ID + Sync Now (Hidden initially)
    const syncDropdown = document.createElement("div");
    Object.assign(syncDropdown.style, {
      position: "absolute", top: "100%", right: "10px",
      backgroundColor: "#fff", border: "1px solid #dee2e6", borderRadius: "0 0 4px 4px",
      padding: "10px", boxShadow: "0 4px 6px rgba(0,0,0,0.1)",
      display: "none", flexDirection: "column", gap: "8px", zIndex: "1060", minWidth: "200px"
    });

    const shopIdInput = $("syncShopId");
    if (shopIdInput) {
      shopIdInput.className = "form-control form-control-sm";
      shopIdInput.placeholder = "Shop ID";
      syncDropdown.appendChild(shopIdInput);
    }

    const btnSync = $("btnDoSync");
    if (btnSync) {
      btnSync.className = "btn btn-success btn-sm w-100";
      btnSync.textContent = "Sync Now";
      syncDropdown.appendChild(btnSync);
    }

    if (shopIdInput || btnSync) {
      topBar.appendChild(syncDropdown);
      btnUzumToggle.addEventListener("click", (e) => {
        e.stopPropagation();
        syncDropdown.style.display = syncDropdown.style.display === "none" ? "flex" : "none";
      });
      document.addEventListener("click", (e) => {
        if (!syncDropdown.contains(e.target) && e.target !== btnUzumToggle) {
          syncDropdown.style.display = "none";
        }
      });
    }

    // 5. Inject Top Bar and Spacer
    document.body.prepend(topBar);
    const spacer = document.createElement("div");
    spacer.style.height = "70px";
    document.body.prepend(spacer);

    // 5. Hide inputs that are now hardcoded (AFTER moving Shop ID)
    ["syncWorkerBase", "syncSize"].forEach(id => {
      const el = $(id);
      if (el) {
        const p = el.closest(".mb-3") || el.parentElement;
        if (p) p.style.display = "none";
      }
    });

    // 6. Attach Sync Event Listener
    const btn = $("btnDoSync");
    if (btn) {
      btn.addEventListener("click", async () => {
        const worker_base = "https://uzum-api.ulugbek2003-09-09-pp.workers.dev";
        const shop_id = ($("syncShopId")?.value || "").trim();
        const size = 100;
        const sync_all = $("syncAll")?.checked || false;

        const out = $("syncResult");
        if (out) {
          out.style.display = "block";
          out.className = "alert alert-secondary mb-0 small";
          out.textContent = "Syncing… please wait (can take time for many pages).";
        }

        try {
          const data = await postJson("/api/uzum/sync", { worker_base, shop_id, size, sync_all, max_pages: 500 });
          if (out) {
            out.className = "alert alert-success mb-0 small";
            out.textContent = `Done. Pages: ${data.pages_synced}, fetched: ${data.fetched}. Reloading…`;
          }
          setTimeout(() => location.reload(), 800);
        } catch (e) {
          if (out) {
            out.className = "alert alert-danger mb-0 small";
            out.textContent = "Error: " + e.message;
          }
        }
      });
    }

    // Inject images into group detail table (server-rendered)
    const match = window.location.pathname.match(/\/groups\/(\d+)$/);
    if (match) {
      const groupId = match[1];
      fetch(`/api/groups/${groupId}/variants?_=${Date.now()}`)
        .then(r => r.json())
        .then(data => {
          const imgs = (data.variants || []).map(v => v.image_url);
          const sales = (data.variants || []).map(v => v.sales_30d);
          const table = document.querySelector("table");
          if (!table) return;

          const theadRow = table.querySelector("thead tr");
          if (theadRow) {
              if (theadRow.querySelector(".th-img-col")) return; // Prevent double injection
              const th = document.createElement("th");
              th.textContent = "Img";
              th.className = "th-img-col";
              th.style.width = "50px";
              theadRow.insertBefore(th, theadRow.firstElementChild);

              const thSales = document.createElement("th");
              thSales.textContent = "30d Sales";
              thSales.className = "text-end";
              theadRow.appendChild(thSales);
          }

          const rows = table.querySelectorAll("tbody tr");
          rows.forEach((row, i) => {
              let url = imgs[i];
              const s30 = sales[i] || 0;
              
              // Safety check: if URL is a JSON string (legacy bad data), parse it
              if (url && url.startsWith("{")) {
                try {
                  const parsed = JSON.parse(url);
                  url = parsed.url || parsed.link || parsed.src || null;
                } catch (e) {}
              }

              const td = document.createElement("td");
              if (url) {
                td.innerHTML = `<img src="${url}" class="table-img" onerror="this.style.opacity=0.5">`;
              } else {
                td.innerHTML = `<span class="text-secondary small" style="font-size:0.7rem">-</span>`;
              }
              row.insertBefore(td, row.firstElementChild);

              const tdSales = document.createElement("td");
              tdSales.className = "text-end fw-semibold";
              tdSales.textContent = s30;
              row.appendChild(tdSales);
          });
        });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initUzumUI);
  } else {
    initUzumUI();
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!res.ok) {
      const msg = data?.error ? data.error : (typeof data === "string" ? data : JSON.stringify(data));
      throw new Error(msg);
    }
    return data;
  }
})();