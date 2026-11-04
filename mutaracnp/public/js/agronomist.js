/* Agronomist Desk.
 *
 * One page for the whole job: build the season's programme, choose what it will
 * actually be drawn from, calculate it, send it for review, then follow the
 * plans, requests and applications it produces. The agronomist never opens a
 * doctype form, which is the point - the forms expose every field in the
 * schema, in schema order, with no idea which step comes next.
 *
 * Follows the clinic desk's shape: KPIs, pill tabs, and queues whose rows carry
 * the action that moves the work on. */

(function () {
  const cfg = window.CNP || {};
  const $  = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n, d = 0) => (Number(n) || 0).toLocaleString(undefined,
    { minimumFractionDigits: d, maximumFractionDigits: d });

  // `scope` is the one farm the module is operating on (Module Settings), or
  // "" for all. Every farm picker, list and new record below honours it.
  let state = { season: "", data: null, scope: "" };

  // Same vocabulary as Crop Nutrient Rule / Fertilizer Schedule - products
  // are grouped under these on the Load Products list so "under Nitrogen,
  // choose CAN" reads the way the agronomist thinks about it.
  const NUTRIENT_LABELS = {
    N: "Nitrogen", P: "Phosphate", K: "Potassium", Ca: "Calcium",
    Mg: "Magnesium", S: "Sulphur", Mn: "Manganese", B: "Boron",
    Mo: "Molybdenum", Zn: "Zinc",
  };

  // ------------------------------------------------------------------ transport
  async function call(method, args = {}, { quiet = false } = {}) {
    let res, data;
    try {
      res = await fetch("/api/method/mutaracnp.mutaracnp.api." + method, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Frappe-CSRF-Token": cfg.csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify(args),
      });
      data = await res.json();
    } catch (e) {
      if (!quiet) toast("Could not reach the server.", "bad");
      throw Object.assign(new Error("network"), { handled: true });
    }
    if (!res.ok || data.exc) {
      if (res.status === 401 || res.status === 403) {
        location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname);
      }
      const msg = serverMessage(data) || `Server error (${res.status}).`;
      if (!quiet) toast(msg, "bad");
      throw Object.assign(new Error(msg), { handled: true });
    }
    return data.message;
  }

  /** Frappe buries the useful sentence inside _server_messages. */
  function serverMessage(d) {
    try {
      if (d && d._server_messages) {
        const first = JSON.parse(d._server_messages)[0];
        const parsed = typeof first === "string" ? JSON.parse(first) : first;
        if (parsed && parsed.message) return String(parsed.message).replace(/<[^>]+>/g, "");
      }
    } catch (e) { /* fall through */ }
    if (d && d.exception) return String(d.exception).split(":").pop().trim();
    return null;
  }

  /** Top right, stacked, and gone on their own.
   *
   *  They used to land bottom-centre over the content and a second one
   *  replaced the first, so a run of actions left one message and no idea
   *  which. Ten seconds is long enough to read without becoming furniture. */
  function toast(msg, kind) {
    let wrap = $(".toastwrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toastwrap";
      document.body.appendChild(wrap);
    }
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " toast--" + kind : "");
    const ic = kind === "good" ? "✓" : kind === "bad" ? "!" : "•";
    el.innerHTML = `<span class="toast__ic">${ic}</span><span></span>`;
    el.lastElementChild.textContent = msg;
    wrap.appendChild(el);
    const go = () => {
      el.classList.add("toast--out");
      setTimeout(() => { el.remove(); if (!wrap.children.length) wrap.remove(); }, 320);
    };
    const t = setTimeout(go, 10000);
    el.addEventListener("click", () => { clearTimeout(t); go(); });
  }

  // --------------------------------------------------------------- frappe client
  /** Generic document calls. These are Frappe's own whitelisted endpoints, so
   *  permissions, validation and the doctype's own controller all still run -
   *  the desk is a nicer way in, not a way round. */
  async function doc(method, args) {
    let res, data;
    try {
      res = await fetch("/api/method/frappe.client." + method, {
        method: "POST",
        headers: {
          "Content-Type": "application/json", Accept: "application/json",
          "X-Frappe-CSRF-Token": cfg.csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify(args),
      });
      data = await res.json();
    } catch (e) {
      toast("Could not reach the server.", "bad");
      throw Object.assign(new Error("network"), { handled: true });
    }
    if (!res.ok || data.exc) {
      const msg = serverMessage(data) || `Server error (${res.status}).`;
      toast(msg, "bad");
      throw Object.assign(new Error(msg), { handled: true });
    }
    return data.message;
  }

  const getDoc  = (doctype, name) => doc("get", { doctype, name });
  const listDoc = (doctype, fields, filters, order, limit) =>
    doc("get_list", {
      doctype, fields, filters: filters || [],
      order_by: order || "modified desc", limit_page_length: limit || 200,
    });
  const saveDoc = (d) => doc(d.name && !d.__islocal ? "save" : "insert", { doc: d });

  // ----------------------------------------------------------------- modal/form
  let openModals = 0;

  function modal({ title, sub = "", body = "", foot = [], size = "", onClose }) {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `<div class="modal ${size ? "modal--" + size : ""}" role="dialog" aria-modal="true">
      <div class="modal__head"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div>
      <button class="modal__x" aria-label="Close">&times;</button></div>
      <div class="modal__body"></div><div class="modal__foot"></div></div>`;
    document.body.appendChild(back);
    openModals++;
    const bodyEl = $(".modal__body", back), footEl = $(".modal__foot", back);
    if (typeof body === "string") bodyEl.innerHTML = body; else bodyEl.appendChild(body);

    const handle = {
      el: back, body: bodyEl, foot: footEl,
      close() {
        if (!back.isConnected) return;
        back.remove(); openModals--;
        document.removeEventListener("keydown", onKey);
        if (onClose) onClose();
      },
      setFoot(buttons) {
        footEl.innerHTML = "";
        buttons.forEach((b) => {
          const btn = document.createElement("button");
          btn.className = "btn " + (b.cls || "");
          btn.textContent = b.label;
          btn.addEventListener("click", async () => {
            if (!b.onClick) return handle.close();
            const all = $$("button", footEl);
            all.forEach((x) => (x.disabled = true));
            try { await b.onClick(handle); }
            catch (e) { if (!e.handled) toast(e.message || "Something went wrong.", "bad"); }
            finally { if (back.isConnected) all.forEach((x) => (x.disabled = false)); }
          });
          footEl.appendChild(btn);
        });
        footEl.style.display = buttons.length ? "" : "none";
      },
    };
    const onKey = (e) => { if (e.key === "Escape") handle.close(); };
    document.addEventListener("keydown", onKey);
    $(".modal__x", back).addEventListener("click", () => handle.close());
    handle.setFoot(foot);
    return handle;
  }

  /** One labelled input. `link` fetches its options once, lazily. */
  function fieldHtml(f, value) {
    const v = value == null ? "" : value;
    const req = f.reqd ? ` <span class="req">*</span>` : "";
    let input;
    if (f.type === "select") {
      input = `<select data-f="${esc(f.name)}">${(f.options || []).map((o) =>
        `<option value="${esc(o)}"${String(o) === String(v) ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
    } else if (f.type === "link") {
      input = `<select data-f="${esc(f.name)}" data-link="${esc(f.doctype)}" data-val="${esc(v)}">
        <option value="${esc(v)}">${esc(v || "—")}</option></select>`;
    } else if (f.type === "itempick") {
      // Shows the name, stores the code. Nobody recognises "10070010005".
      input = `<div class="itempick">
        <input type="text" class="itempick__show" readonly placeholder="Search for an item…"
          value="${esc(f.display || v)}">
        <input type="hidden" data-f="${esc(f.name)}" value="${esc(v)}">
        <button type="button" class="btn itempick__go">Search</button>
      </div>`;
    } else if (f.type === "check") {
      input = `<input type="checkbox" data-f="${esc(f.name)}"${v ? " checked" : ""}>`;
    } else if (f.type === "text") {
      input = `<textarea data-f="${esc(f.name)}">${esc(v)}</textarea>`;
    } else {
      const t = f.type === "int" || f.type === "float" ? "number" : f.type === "date" ? "date" : "text";
      const step = f.type === "float" ? ' step="any"' : "";
      input = `<input type="${t}"${step} data-f="${esc(f.name)}" value="${esc(v)}">`;
    }
    return `<div class="field">
      <label>${esc(f.label)}${req}</label>${input}
      ${f.help ? `<small>${esc(f.help)}</small>` : ""}
    </div>`;
  }

  /** Fill every link select in a container from its doctype, once.
   *
   *  A field can declare `filterBy: "farm"` (looked up via `spec`, so this
   *  only applies to the top-level form, not table rows) to narrow its list
   *  to whatever the named sibling field currently holds - Section and Block
   *  pickers only make sense once a Farm is chosen, otherwise every section
   *  or block on every farm would be offered. That sibling is watched for
   *  changes so picking a different Farm re-narrows them live. */
  async function hydrateLinks(root, spec) {
    const sels = $$("select[data-link]", root);
    const byName = {};
    (spec ? spec.fields : []).forEach((f) => { byName[f.name] = f; });

    async function load(sel) {
      const dt = sel.dataset.link;
      const f = byName[sel.dataset.f];
      // Item is named by item_code ("1010100032"), not a human label - every
      // other doctype here is named by something readable already, so this
      // is the one place that needs its title field fetched and shown
      // instead of the raw name.
      const fields = dt === "Item" ? ["name", "item_name"] : ["name"];
      const label = (r) => (dt === "Item" && r.item_name) ? `${r.item_name} (${r.name})` : r.name;
      // Item is shared with the site's whole stock ledger - nails, PPE,
      // whatever else - so an unfiltered list of it is mostly not
      // fertilizer at all. Same item groups the rest of the module already
      // scopes Item pickers to (get_product_items, search_fertilizer_items).
      const itemFilters = [["item_group", "in", ["Fertilizer", "AVOCADO FERTILIZER"]], ["disabled", "=", 0]];
      let rows = [];
      try {
        if (f && f.filterBy) {
          const dep = $(`[data-f="${f.filterBy}"]`, root);
          const depVal = dep ? dep.value : "";
          rows = depVal ? await listDoc(dt, fields, [[f.filterBy, "=", depVal]], "name asc") : [];
        } else if (dt === "Item") {
          rows = await listDoc(dt, fields, itemFilters, "item_name asc", 500);
        } else {
          rows = await listDoc(dt, fields,
            dt === "CNP Farm" && state.scope ? [["name", "=", state.scope]] : [], "name asc");
        }
      } catch (e) { rows = []; }
      const cur = sel.dataset.val || "";
      sel.innerHTML = `<option value="">—</option>` + rows.map((r) =>
        `<option value="${esc(r.name)}"${r.name === cur ? " selected" : ""}>${esc(label(r))}</option>`).join("");
      sel.value = cur;
    }

    await Promise.all(sels.map(load));
    sels.forEach((sel) => {
      const f = byName[sel.dataset.f];
      if (!f || !f.filterBy) return;
      const dep = $(`[data-f="${f.filterBy}"]`, root);
      if (dep) dep.addEventListener("change", () => load(sel).catch(() => {}));
    });
  }

  /** Read a form back out of the DOM. */
  function readForm(root, spec) {
    const out = {};
    spec.fields.forEach((f) => {
      const el = $(`[data-f="${f.name}"]`, root);
      if (!el) return;
      out[f.name] = f.type === "check" ? (el.checked ? 1 : 0)
        : (f.type === "int" || f.type === "float") ? (el.value === "" ? 0 : Number(el.value))
        : el.value;
    });
    (spec.tables || []).forEach((t) => {
      out[t.name] = $$(`tr[data-row="${t.name}"]`, root).map((tr) => {
        const row = {};
        t.fields.forEach((f) => {
          const el = $(`[data-f="${f.name}"]`, tr);
          if (!el) return;
          row[f.name] = f.type === "check" ? (el.checked ? 1 : 0)
            : (f.type === "int" || f.type === "float") ? (el.value === "" ? 0 : Number(el.value))
            : el.value;
        });
        return row;
      });
    });
    return out;
  }

  function tableHtml(t, rows) {
    const head = t.fields.map((f) => `<th>${esc(f.label)}</th>`).join("") + "<th></th>";
    const body = (rows || []).map((r) => rowHtml(t, r)).join("");
    return `<div class="field"><label>${esc(t.label)}</label>
      ${t.help ? `<small>${esc(t.help)}</small>` : ""}
      <table class="gridtbl" data-table="${esc(t.name)}">
        <thead><tr>${head}</tr></thead><tbody>${body}</tbody>
      </table>
      <button class="btn" data-addrow="${esc(t.name)}" style="margin-top:8px">Add row</button></div>`;
  }

  function rowHtml(t, r) {
    r = r || {};
    const cells = t.fields.map((f) => {
      const v = r[f.name] == null ? "" : r[f.name];
      let input;
      if (f.type === "select") {
        input = `<select data-f="${esc(f.name)}">${(f.options || []).map((o) =>
          `<option value="${esc(o)}"${String(o) === String(v) ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
      } else if (f.type === "link") {
        input = `<select data-f="${esc(f.name)}" data-link="${esc(f.doctype)}" data-val="${esc(v)}">
          <option value="${esc(v)}">${esc(v || "—")}</option></select>`;
      } else if (f.type === "check") {
        input = `<input type="checkbox" data-f="${esc(f.name)}"${v ? " checked" : ""}>`;
      } else {
        const ty = (f.type === "int" || f.type === "float") ? "number" : "text";
        const step = f.type === "float" ? ' step="any"' : "";
        input = `<input type="${ty}"${step} data-f="${esc(f.name)}" value="${esc(v)}">`;
      }
      return `<td>${input}</td>`;
    }).join("");
    return `<tr data-row="${esc(t.name)}">${cells}<td><button class="x" data-delrow="1">&times;</button></td></tr>`;
  }

  /** A searchable item picker, by name. Resolves to the chosen row or null. */
  function pickItem(current) {
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.innerHTML = `<input class="searchbox" id="ip-q" placeholder="Type part of the name…" autofocus>
        <div class="queue" id="ip-rows"><div class="skel"></div></div>`;
      let done = false;
      const m = modal({
        title: "Choose an item", sub: "Fertilizer group, this farm's company.",
        body: wrap, foot: [{ label: "Cancel" }],
        onClose: () => { if (!done) resolve(null); },
      });

      let timer;
      async function search(q) {
        const rows = await call("search_fertilizer_items",
          { search: q || null });
        $("#ip-rows", wrap).innerHTML = rows.map((r) => `
          <div class="qrow" data-pick='${esc(JSON.stringify(r))}' style="cursor:pointer">
            <div class="qrow__mark" style="background:transparent">${r.item_code === current
              ? `<span class="mark mark--yes">✓</span>` : ""}</div>
            <div><div class="qrow__name">${esc(r.item_name || r.item_code)}</div>
            <div class="qrow__meta">${esc(r.item_code)} · ${num(r.stock_qty)} ${esc(r.stock_uom || "kg")} in stock</div></div>
            <div class="qrow__right">${r.stock_qty > 0 ? pill("in stock", "good") : pill("empty", "mute")}</div>
          </div>`).join("") || `<div class="none">Nothing matches.</div>`;
      }
      $("#ip-q", wrap).addEventListener("input", (e) => {
        clearTimeout(timer);
        const q = e.target.value;
        timer = setTimeout(() => search(q).catch(() => {}), 250);
      });
      wrap.addEventListener("click", (e) => {
        const row = e.target.closest("[data-pick]");
        if (!row) return;
        done = true;
        resolve(JSON.parse(row.dataset.pick));
        m.close();
      });
      search("").catch(() => {});
    });
  }

  // ---------------------------------------------------------------- what we edit
  /* Curated on purpose. A doctype form shows every field in the schema, in
   * schema order, which is exactly the thing this desk exists to avoid - so
   * each entry names the fields an agronomist actually fills, in the order
   * they think about them. Everything else on the record keeps its default or
   * is set by the controller. */
  const SPECS = {
    programme: {
      doctype: "Fertilizer Programme", title: "Fertilizer Programme",
      icon: "🗂", tint: "rgba(16,185,129,.13)", colour: "#059669",
      sub: "The season's plan. Build it, calculate it, submit it.",
      list: ["name", "season", "farm", "scope_type", "crop", "docstatus"],
      fields: [
        { name: "season", label: "Season", type: "select", reqd: 1,
          options: ["2025/2026", "2026/2027"] },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "scope_type", label: "Programme Scope", type: "select",
          options: ["Entire Farm", "Section", "Block"],
          help: "Entire Farm plans every block. Section or Block narrows it to one piece of the farm." },
        { name: "scope_section", label: "Section", type: "link", doctype: "Section",
          filterBy: "farm", showWhen: { field: "scope_type", equals: "Section" } },
        { name: "scope_block", label: "Block", type: "link", doctype: "Farm Block",
          filterBy: "farm", showWhen: { field: "scope_type", equals: "Block" } },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "production_calendar", label: "Production Calendar", type: "link", doctype: "Production Calendar", reqd: 1 },
        { name: "period_type", label: "Programme Period", type: "select", options: ["Full Year", "Custom Period"] },
        { name: "start_month", label: "Start Month", type: "select",
          showWhen: { field: "period_type", equals: "Custom Period" },
          options: ["", "January","February","March","April","May","June","July","August","September","October","November","December"] },
        { name: "end_month", label: "End Month", type: "select",
          showWhen: { field: "period_type", equals: "Custom Period" },
          options: ["", "January","February","March","April","May","June","July","August","September","October","November","December"] },
      ],
    },
    farm: {
      doctype: "CNP Farm", title: "Farm", icon: "🌍", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "The farms this module plans for.",
      list: ["name", "default_crop", "is_active"],
      fields: [
        { name: "farm_name", label: "Farm Name", reqd: 1 },
        { name: "default_crop", label: "Default Crop", type: "link", doctype: "Crop" },
        { name: "farm_manager", label: "Farm Manager", type: "link", doctype: "User" },
        { name: "warehouse", label: "Warehouse", type: "link", doctype: "Warehouse" },
        { name: "is_active", label: "Active", type: "check" },
      ],
    },
    section: {
      doctype: "Section", title: "Section", icon: "🗺", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Open a section to see its blocks, and add or correct them there.",
      open: "section",
      list: ["name", "farm", "is_active"],
      fields: [
        { name: "section_name", label: "Section Name", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "is_active", label: "Active", type: "check" },
      ],
    },
    block: {
      doctype: "Farm Block", title: "Farm Block", icon: "🧱", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Area, trees and projected yield - what the whole calculation rests on.",
      list: ["name", "section", "area_ha", "tree_count", "projected_yield_kg_ha"],
      fields: [
        { name: "block_name", label: "Block Name", reqd: 1 },
        { name: "block_number", label: "Block Number" },
        { name: "section", label: "Section", type: "link", doctype: "Section", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop" },
        { name: "area_ha", label: "Area (Ha)", type: "float", reqd: 1 },
        { name: "tree_count", label: "Tree Count", type: "int", reqd: 1 },
        { name: "projected_yield_kg_ha", label: "Projected Yield (Kg/Ha)", type: "float",
          help: "Decides the block's yield tier - a projection, since Mutara has no harvest history yet." },
        { name: "planting_year", label: "Planting Year", type: "int" },
      ],
    },
    crop: {
      doctype: "Crop", title: "Crop", icon: "🌱", tint: "rgba(16,185,129,.13)", colour: "#059669",
      sub: "Yield tiers and nutrient rules - the engine's master data.",
      list: ["name", "item", "compost_dose_kg"],
      fields: [
        { name: "crop_name", label: "Crop Name", reqd: 1 },
        { name: "item", label: "Produce Item", type: "link", doctype: "Item",
          help: "The harvested produce, not a fertilizer." },
        { name: "compost_dose_kg", label: "Compost Dose (Kg)", type: "float" },
        { name: "compost_n_pct", label: "Compost N (%)", type: "float" },
        { name: "leaf_adjustment_pct", label: "Leaf Adjustment (%)", type: "float" },
      ],
      tables: [
        { name: "yield_tiers", label: "Yield Tiers", fields: [
          { name: "tier_label", label: "Tier" },
          { name: "tier_tonnage", label: "Tonnage", type: "float" },
          { name: "min_yield_kg_ha", label: "Min Kg/Ha", type: "float" },
          { name: "max_yield_kg_ha", label: "Max Kg/Ha", type: "float" },
          { name: "sort_order", label: "Order", type: "int" },
        ] },
      ],
    },
    rule: {
      doctype: "Crop Nutrient Rule", title: "Crop Nutrient Rule", icon: "🧮",
      tint: "rgba(16,185,129,.13)", colour: "#059669",
      sub: "Nutrient removal/rate factors per crop - the engine's core dosing math.",
      list: ["name", "crop", "nutrient", "fertilizer_product", "rate_per_tonne"],
      fields: [
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "fertilizer_product", label: "Fertilizer Item", type: "link", doctype: "Item", reqd: 1 },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"], reqd: 1 },
        { name: "rate_per_tonne", label: "Rate/Tonne", type: "float" },
        { name: "bag_weight_kg", label: "Bag Kg", type: "float" },
        { name: "product_nutrient_pct", label: "Nutrient %", type: "float" },
        { name: "apply_compost_netting", label: "Net Compost", type: "check" },
        { name: "nutrient_source_group", label: "Source Group",
          help: "Groups interchangeable sources for the same nutrient, e.g. MOP+K2SO4 as alternate K sources." },
      ],
    },
    product: {
      doctype: "Fertilizer Product", title: "Fertilizer Product", icon: "🧪",
      tint: "rgba(245,158,11,.13)", colour: "#d97706",
      sub: "CAN, MOP, K2SO4 — and the spellings each is known by on this site.",
      list: ["name", "product_name", "nutrient", "disabled"],
      fields: [
        { name: "product_code", label: "Product Code", reqd: 1, help: "e.g. CAN" },
        { name: "product_name", label: "Product Name" },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
        { name: "item_group", label: "Item Group", type: "link", doctype: "Item Group" },
        { name: "search_terms", label: "Search Terms", type: "text", reqd: 1,
          help: "One per line. List every spelling - POTASIUM and POTASSIUM are different items here." },
        { name: "exclude_terms", label: "Exclude Terms", type: "text" },
        { name: "disabled", label: "Disabled", type: "check" },
      ],
    },
    calendar: {
      doctype: "Production Calendar", title: "Production Calendar", icon: "🗓",
      tint: "rgba(79,70,229,.13)", colour: "#4f46e5",
      sub: "Which months each product is applied in, and in what share.",
      list: ["name", "season", "farm"],
      fields: [
        { name: "season", label: "Season", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm", reqd: 1 },
        { name: "season_notes", label: "Notes", type: "text" },
      ],
      tables: [
        { name: "fertilizer_schedule", label: "Fertilizer Schedule",
          help: "By fertilizer Item, not nutrient - MOP and K2SO4 just get their own rows here like any other product.",
          fields: [
          { name: "fertilizer_product", label: "Fertilizer Item", type: "link", doctype: "Item" },
          { name: "application_month", label: "Month", type: "select", options: ["January","February","March","April","May","June","July","August","September","October","November","December"] },
          { name: "percentage", label: "% of Annual Total", type: "float" },
        ] },
      ],
    },
    leaf: {
      doctype: "Leaf Analysis", title: "Leaf Analysis", icon: "🍃",
      tint: "rgba(34,197,94,.13)", colour: "#16a34a",
      sub: "Lab results per section, which adjust the calculated rates.",
      list: ["name", "section", "sampling_date", "yield_tier"],
      fields: [
        { name: "section", label: "Section", type: "link", doctype: "Section", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm" },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop" },
        { name: "block", label: "Block", type: "link", doctype: "Farm Block" },
        { name: "sampling_date", label: "Sampling Date", type: "date" },
        { name: "season", label: "Season" },
      ],
      tables: [
        { name: "nutrient_results", label: "Nutrient Results", fields: [
          { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
          { name: "result_value", label: "Result", type: "float" },
          { name: "unit", label: "Unit", type: "select", options: ["%", "ppm"] },
        ] },
      ],
    },
    norm: {
      doctype: "Leaf Analysis Norm", title: "Leaf Analysis Norm", icon: "📏",
      tint: "rgba(6,182,212,.13)", colour: "#0891b2",
      sub: "The healthy range per nutrient. A result outside it moves the rate.",
      list: ["name", "crop", "nutrient", "low", "high", "midpoint"],
      fields: [
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"], reqd: 1 },
        { name: "low", label: "Low", type: "float" },
        { name: "high", label: "High", type: "float" },
        { name: "midpoint", label: "Midpoint", type: "float" },
        { name: "unit", label: "Unit", type: "select", options: ["%", "ppm"] },
      ],
    },
    soil: {
      doctype: "Soil Analysis", title: "Soil Analysis", icon: "🪨",
      tint: "rgba(120,113,108,.15)", colour: "#78716c",
      sub: "Lab results per section, which build up or draw down the calculated rates.",
      list: ["name", "section", "sampling_date", "yield_tier"],
      fields: [
        { name: "section", label: "Section", type: "link", doctype: "Section", reqd: 1 },
        { name: "farm", label: "Farm", type: "link", doctype: "CNP Farm" },
        { name: "crop", label: "Crop", type: "link", doctype: "Crop" },
        { name: "block", label: "Block", type: "link", doctype: "Farm Block" },
        { name: "sampling_date", label: "Sampling Date", type: "date" },
        { name: "season", label: "Season" },
      ],
      tables: [
        { name: "nutrient_results", label: "Nutrient Results", fields: [
          { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
          { name: "result_value", label: "Result", type: "float" },
          { name: "unit", label: "Unit", type: "select", options: ["%", "ppm", "me%", "mg/kg"] },
        ] },
      ],
    },
    soilnorm: {
      doctype: "Soil Analysis Norm", title: "Soil Analysis Norm", icon: "📐",
      tint: "rgba(120,113,108,.15)", colour: "#78716c",
      sub: "The healthy soil range per nutrient. A result outside it moves the rate.",
      list: ["name", "crop", "nutrient", "low", "high", "midpoint"],
      fields: [
        { name: "crop", label: "Crop", type: "link", doctype: "Crop", reqd: 1 },
        { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"], reqd: 1 },
        { name: "low", label: "Low", type: "float" },
        { name: "high", label: "High", type: "float" },
        { name: "midpoint", label: "Midpoint", type: "float" },
        { name: "unit", label: "Unit", type: "select", options: ["%", "ppm", "me%", "mg/kg"] },
      ],
    },
    settings: {
      doctype: "Crop Nutrition Planning Settings", single: true,
      title: "Module Settings", icon: "⚙", tint: "rgba(100,116,139,.15)", colour: "#64748b",
      sub: "Module-wide defaults, including the soil buildup factors below.",
      fields: [
        { name: "upcoming_alert_days", label: "Alert Days Before Application", type: "int" },
        { name: "variance_threshold_pct", label: "Variance Alert Threshold (%)", type: "int" },
      ],
      tables: [
        { name: "soil_buildup_factors", label: "Soil Buildup Factors",
          help: "One factor per nutrient, applied globally across crops when a soil test is below/above its norm.",
          fields: [
          { name: "nutrient", label: "Nutrient", type: "select", options: ["N","P","K","Ca","Mg","S","Mn","B","Mo","Zn"] },
          { name: "buildup_factor", label: "Buildup Factor", type: "float" },
          { name: "notes", label: "Notes" },
        ] },
      ],
    },
  };

  // --------------------------------------------------------------- record popups
  /** Open one record for editing, or a blank one. */
  async function openRecord(key, name, afterSave, defaults) {
    const spec = SPECS[key];
    let data = {};
    if (spec.single) {
      data = await getDoc(spec.doctype, spec.doctype);
    } else if (name) {
      data = await getDoc(spec.doctype, name);
    } else {
      // A new record that already knows where it belongs - a block added from
      // inside a section should not ask which section it is in, and with the
      // module on one farm nothing should ask which farm.
      const onFarm = state.scope && spec.fields.some((f) => f.name === "farm")
        ? { farm: state.scope } : {};
      data = Object.assign(onFarm, defaults || {});
    }

    const form = document.createElement("div");
    form.innerHTML = `<div class="fgrid">${spec.fields.map((f) =>
      fieldHtml(f, data[f.name])).join("")}</div>` +
      (spec.tables || []).map((t) => tableHtml(t, data[t.name])).join("");

    const m = modal({
      title: name || spec.single ? `Edit ${spec.title}` : `New ${spec.title}`,
      sub: spec.sub, body: form, size: (spec.tables || []).length ? "wide" : "",
      foot: [
        { label: "Cancel" },
        { label: "Save", cls: "btn--ink", onClick: async (h) => {
            const values = readForm(form, spec);
            const payload = spec.single
              ? Object.assign({}, data, values, { doctype: spec.doctype, name: spec.doctype })
              : name
                ? Object.assign({}, data, values)
                : Object.assign({ doctype: spec.doctype }, values);
            const saved = await saveDoc(payload);
            toast(`${spec.title} saved.`, "good");
            h.close();
            if (afterSave) afterSave(saved);
          } },
      ],
    });

    // A field tagged showWhen only matters once another field holds a given
    // value - the custom-period months, or the scope's section/block - so it
    // stays hidden until then instead of sitting there as noise.
    const conditional = spec.fields.filter((f) => f.showWhen);
    const syncConditional = () => {
      conditional.forEach((f) => {
        const dep = $(`[data-f="${f.showWhen.field}"]`, form);
        const el = $(`[data-f="${f.name}"]`, form);
        if (dep && el) el.closest(".field").style.display =
          dep.value === f.showWhen.equals ? "" : "none";
      });
    };
    new Set(conditional.map((f) => f.showWhen.field)).forEach((depName) => {
      const dep = $(`[data-f="${depName}"]`, form);
      if (dep) dep.addEventListener("change", syncConditional);
    });
    syncConditional();

    // searching for an item by name, from inside the form
    form.addEventListener("click", async (e) => {
      const go = e.target.closest(".itempick__go");
      if (!go) return;
      const wrap = go.closest(".itempick");
      const hidden = $('input[type="hidden"]', wrap);
      const shown = $(".itempick__show", wrap);
      const picked = await pickItem(hidden.value);
      if (picked) { hidden.value = picked.item_code; shown.value = picked.item_name || picked.item_code; }
    });

    // rows can be added and removed while the popup is open
    form.addEventListener("click", (e) => {
      const add = e.target.closest("[data-addrow]");
      if (add) {
        const t = (spec.tables || []).find((x) => x.name === add.dataset.addrow);
        const tb = $(`table[data-table="${t.name}"] tbody`, form);
        tb.insertAdjacentHTML("beforeend", rowHtml(t, {}));
        hydrateLinks(tb);
        return;
      }
      const del = e.target.closest("[data-delrow]");
      if (del) del.closest("tr").remove();
    });

    await hydrateLinks(form, spec);
    return m;
  }

  /** A section and its blocks: sizes, progress, and where blocks are added or
   *  corrected. `back` re-opens whatever list this was reached from. */
  async function openSection(name, back) {
    let d;
    try { d = await call("get_section_overview", { section: name, season: state.season || null }); }
    catch (e) { return; }
    const t = d.totals, sec = d.section;

    const body = document.createElement("div");
    const draw = (blocks) => blocks.map((b) => `
      <div class="qrow" data-sb-open="${esc(b.block)}" style="cursor:pointer">
        <div class="qrow__mark">${esc((b.block || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(b.block)}</div>
          <div class="qrow__meta">${num(b.area_ha, 2)} ha · ${num(b.tree_count)} trees ·
            ${b.last_yield ? num(b.last_yield) + " kg/ha last year" : "no yield recorded"} ·
            ${num(b.done)}/${num(b.rounds)} rounds</div>
        </div>
        <div class="qrow__right">${bar(b.pct, b.pct >= 100 ? "good" : b.pct ? "warn" : "")}
          ${pill(b.state, stateKindFor(b.state))}
          <button class="btn" data-sb-edit="${esc(b.block)}">Edit</button></div>
      </div>`).join("") || `<div class="none">No blocks in this section yet. Use “Add block”.</div>`;

    body.innerHTML = `
      <div class="kpi-grid" style="margin-bottom:16px">
        <div class="kpi"><div class="kpi__label">Blocks</div>
          <div class="kpi__value">${num(t.blocks)}</div>
          <div class="kpi__unit">${sec.is_active ? "active section" : "inactive section"}</div></div>
        <div class="kpi"><div class="kpi__label">Area</div>
          <div class="kpi__value">${num(t.area_ha, 1)}</div><div class="kpi__unit">hectares</div></div>
        <div class="kpi"><div class="kpi__label">Trees</div>
          <div class="kpi__value">${num(t.trees)}</div>
          <div class="kpi__unit">${t.avg_yield ? num(t.avg_yield) + " kg/ha avg yield" : "no yield recorded"}</div></div>
        <div class="kpi"><div class="kpi__label">Rounds applied</div>
          <div class="kpi__value ${t.pct >= 100 ? "good" : ""}">${num(t.done)}/${num(t.rounds)}</div>
          <div class="kpi__unit">${num(t.pct)}% done</div></div>
      </div>
      <input class="searchbox" id="sb-q" placeholder="Search this section's blocks…">
      <div class="queue" id="sb-list">${draw(d.blocks)}</div>`;

    const m = modal({
      title: sec.section_name || sec.name,
      sub: `${sec.farm || ""} · tap a block for its progress, or Edit to change it`,
      body, size: "wide",
      foot: [
        { label: back ? "Back" : "Close", onClick: (h) => { h.close(); if (back) back(); } },
        { label: "Edit section", onClick: (h) => {
            h.close(); openRecord("section", name, () => openSection(name, back)); } },
        { label: "Add block", cls: "btn--ink", onClick: (h) => {
            h.close();
            openRecord("block", null, () => openSection(name, back),
                       { section: name, farm: sec.farm, crop: (d.blocks[0] || {}).crop || "" }); } },
      ],
    });

    $("#sb-q", body).addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      $("#sb-list", body).innerHTML = draw(d.blocks.filter((b) =>
        !q || (b.block || "").toLowerCase().includes(q)));
    });
    body.addEventListener("click", (e) => {
      const ed = e.target.closest("[data-sb-edit]");
      if (ed) {
        m.close();
        return openRecord("block", ed.dataset.sbEdit, () => openSection(name, back));
      }
      const op = e.target.closest("[data-sb-open]");
      if (op) openBlock(op.dataset.sbOpen);
    });
  }

  /** A list of a doctype's records, each opening the editor. */
  async function openList(key) {
    const spec = SPECS[key];
    if (spec.single) return openRecord(key);

    const wrap = document.createElement("div");
    wrap.innerHTML = `<div class="queue"><div class="skel"></div></div>`;
    const m = modal({
      title: spec.title, sub: spec.sub, body: wrap, size: "wide",
      foot: [{ label: "Close" },
             { label: `New ${spec.title}`, cls: "btn--ink",
               onClick: (h) => { h.close(); openRecord(key, null, () => openList(key)); } }],
    });

    async function draw() {
      const farmField = spec.doctype === "CNP Farm" ? "name"
        : spec.fields.some((f) => f.name === "farm") ? "farm" : null;
      const rows = await listDoc(spec.doctype, spec.list,
        state.scope && farmField ? [[farmField, "=", state.scope]] : []);
      $(".queue", wrap).innerHTML = rows.map((r) => {
        const extra = spec.list.slice(1).map((f) =>
          r[f] === undefined || r[f] === null || r[f] === "" ? null : `${f.replace(/_/g, " ")}: ${r[f]}`)
          .filter(Boolean).join(" · ");
        return `<div class="qrow" data-open="${esc(r.name)}" style="cursor:pointer">
          <div class="qrow__mark">${esc(String(r.name).slice(0, 2))}</div>
          <div><div class="qrow__name">${esc(r.name)}</div>
          <div class="qrow__meta">${esc(extra)}</div></div>
          <div class="qrow__right"><span class="btn">Edit</span></div>
        </div>`;
      }).join("") || `<div class="none">Nothing yet. Use “New ${esc(spec.title)}”.</div>`;
    }
    wrap.addEventListener("click", (e) => {
      const row = e.target.closest("[data-open]");
      if (!row) return;
      m.close();
      // Some doctypes have a richer view than a form: a section is its blocks.
      if (spec.open === "section") return openSection(row.dataset.open, () => openList(key));
      openRecord(key, row.dataset.open, () => openList(key));
    });
    await draw();
    return m;
  }

  // ------------------------------------------------------------------- rendering
  function kpi(label, value, cls, unit) {
    return `<div class="kpi">
      <div class="kpi__label">${esc(label)}</div>
      <div class="kpi__value${cls ? " " + cls : ""}">${esc(value)}</div>
      ${unit ? `<div class="kpi__unit">${esc(unit)}</div>` : ""}
    </div>`;
  }

  /** The stylesheet colours `.pill.good`, `.pill.warn` and so on - two
   *  classes on one element. This used to emit `pill--good`, which no rule
   *  matches, so every status pill on the desk rendered unstyled however the
   *  colours were tuned. */
  function pill(text, kind, extra) {
    return `<span class="pill${kind ? " " + kind : ""}${extra ? " " + extra : ""}">${esc(text)}</span>`;
  }

  /** A programme's state as a pill: coloured by state, and marked - a tick when
   *  submitted, a pencil while it is still a draft. */
  function statePill(p) {
    const st = progState(p);
    return pill(st, stateKind(st),
      st === "Submitted" ? "pill--submitted" : st === "Draft" ? "pill--draft" : "");
  }

  /** What the programme is, in the words the agronomist uses. With approval
   *  switched off there are two states that matter: still being built, or in
   *  force. The workflow states only appear if someone turns approval on. */
  function progState(p) {
    // docstatus is the fact; workflow_state is a label that can lag behind it.
    // A submitted document cannot be anything but submitted, whatever the
    // label says - and with approval switched off Frappe never updates the
    // label on submit at all, so it can be left reading "Draft" forever.
    if (p.docstatus === 1) return "Submitted";
    if (p.docstatus === 2) return "Cancelled";
    // Only a draft sitting mid-chain has a state worth showing.
    return p.workflow_state && !["Draft", "Approved"].includes(p.workflow_state)
      ? p.workflow_state : "Draft";
  }

  /** One colour per state, so a programme's standing reads before its word:
   *  green - in force; amber - still yours to finish (a draft); blue - out
   *  with someone for approval; red - withdrawn or turned back. Grey is kept
   *  for "nothing here yet", which is a different thing from a draft. */
  function stateKind(s) {
    if (s === "Submitted" || s === "Approved") return "good";
    if (s === "Rejected" || s === "Cancelled") return "bad";
    if (s === "Draft") return "warn";
    return "info";
  }

  function renderKpis(d) {
    const m = d.metrics || {};
    const c = d.current;
    $("#kpis").innerHTML = [
      kpi("Programme state", c ? progState(c) : "none",
          c ? stateKind(progState(c)) : ""),
      kpi("Blocks planned", num(m.total_plans), "", "rounds across the season"),
      kpi("Season progress", num(m.progress_pct) + "%", "info",
          `${num(m.applied)} of ${num(m.total_plans)} applied`),
      kpi("Pending applications", num(m.pending_applications), "warn"),
      kpi("Ready to record", num(m.ready_to_record), "good", "issued by the store"),
      kpi("Pending store requests", num(m.pending_requests), "warn"),
    ].join("");
  }

  function renderProgramme(d) {
    const c = d.current;
    if (!c) {
      $("#prog-meta").textContent = "";
      $("#prog-body").innerHTML = `<div class="none">No programme for this farm yet.
        Create one in the MutaraCNP workspace, then it appears here.</div>`;
      $("#prod-body").innerHTML = `<div class="none">—</div>`;
      return;
    }
    const a = c.actions || {};
    $("#prog-meta").innerHTML = `${esc(c.season)} · ${esc(c.crop || "")}`;

    const steps = (a.steps || []).map((s) => `
      <div class="step">
        <div class="step__tick${s.done ? " on" : ""}">${s.done ? "✓" : ""}</div>
        <div>
          <div class="step__label">${esc(s.label)}</div>
          <div class="step__detail">${esc(s.detail || "")}</div>
        </div>
      </div>`).join("");

    const period = c.period_type === "Custom Period"
      ? `${esc(c.start_month)} – ${esc(c.end_month)}`
      : "Full year";

    $("#prog-body").innerHTML = `
      <div class="qrow" data-prog="${esc(c.name)}" style="border:0;padding-left:0;cursor:pointer">
        <div class="qrow__mark">${esc((c.season || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(c.name)}</div>
          <div class="qrow__meta">${period} · ${num(c.blocks)} blocks · ${num(c.lines)} lines ·
            <span style="color:var(--signal)">open for the numbers</span></div>
        </div>
        <div class="qrow__right">${statePill(c)}</div>
      </div>
      <div class="steps">${steps}</div>
      ${a.blocked ? `<div class="none">${esc(a.blocked)}</div>` : ""}
      <div class="btnrow">
        <button class="btn" data-edit-prog="${esc(c.name)}">Edit details</button>
        <button class="btn" data-act="pull_blocks" ${a.editable ? "" : "disabled"}>Pull blocks</button>
        <button class="btn" data-act="load_products" ${a.editable ? "" : "disabled"}>Load products</button>
        <button class="btn" data-act="calculate" ${a.editable ? "" : "disabled"}>Run calculation</button>
        <button class="btn" data-edit-rates="${esc(c.name)}" ${c.lines ? "" : "disabled"}>Edit Programme</button>
        <button class="btn" data-act="export_excel" ${c.lines ? "" : "disabled"}>Export Excel</button>
        <button class="btn btn--bad" data-act="delete_draft" ${a.editable ? "" : "disabled"}>Delete draft</button>
        <button class="btn btn--ink" data-act="submit"
          ${a.editable && a.ready_to_send ? "" : "disabled"}>Submit programme</button>
      </div>`;

    // products, grouped by nutrient - "under Nitrogen, choose CAN" - each
    // still with the item it draws from and whether stock covers it
    const byNutrient = {};
    (c.products || []).forEach((p) => {
      const key = p.nutrient || "—";
      (byNutrient[key] = byNutrient[key] || []).push(p);
    });
    const rows = Object.keys(byNutrient).sort().map((nutrient) => {
      const productRows = byNutrient[nutrient].map((p) => {
        const short = p.shortfall > 0;
        return `<div class="qrow">
          <div class="qrow__mark" style="background:transparent">
            <span class="mark mark--${p.item ? "yes" : "no"}">${p.item ? "✓" : "✕"}</span>
          </div>
          <div>
            <div class="qrow__name">${esc(p.item_name || p.item || "No item chosen yet")}</div>
            <div class="qrow__meta">${esc(p.product)}${p.item ? " · " + esc(p.item) : ""} ·
              needs ${num(p.required)} kg, ${num(p.available)} kg in stock</div>
          </div>
          <div class="qrow__right">
            ${!p.item ? pill("not chosen", "bad")
              : short ? pill("short " + num(p.shortfall) + " kg", "bad")
                      : pill("covered", "good")}
            <button class="btn" data-choose="${esc(p.product)}"
              ${c.actions && c.actions.editable ? "" : "disabled"}>${p.item ? "Change" : "Choose"}</button>
          </div>
        </div>`;
      }).join("");
      return `<div class="pagehead__eyebrow" style="margin:14px 0 6px">
        ${esc(NUTRIENT_LABELS[nutrient] || nutrient)}</div>${productRows}`;
    }).join("");
    $("#prod-meta").textContent = (c.products || []).length + " products";
    $("#prod-body").innerHTML = rows
      || `<div class="none">No products loaded. Use “Load products” to list what this crop needs.</div>`;
  }

  function renderProgrammeList(d) {
    $("#prog-list").innerHTML = (d.programmes || []).map((p) => `
      <div class="qrow" data-prog="${esc(p.name)}" style="cursor:pointer">
        <div class="qrow__mark">${esc((p.season || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(p.name)}</div>
          <div class="qrow__meta">${esc(p.season)} · ${esc(p.farm || "")} ·
            ${p.period_type === "Custom Period"
              ? esc(p.start_month) + " – " + esc(p.end_month) : "Full year"} ·
            <span style="color:var(--signal)">open</span></div>
        </div>
        <div class="qrow__right">${statePill(p)}</div>
      </div>`).join("") || `<div class="none">Nothing yet.</div>`;
  }

  /** The programme opened up: what it commits to, and where it has got to. */
  /** A second, smaller modal asking "are you sure" - the delete button does
   *  not get to be one tap, and the destructive action gets its own colour
   *  rather than borrowing the same ink button as everything else. */
  function confirmModal(title, body, confirmLabel) {
    return new Promise((resolve) => {
      let answered = false;
      const m = modal({
        title, sub: body, size: "",
        onClose: () => { if (!answered) resolve(false); },
        foot: [
          { label: "Cancel", onClick: () => { answered = true; resolve(false); } },
          { label: confirmLabel, cls: "btn--bad", onClick: () => { answered = true; resolve(true); } },
        ],
      });
    });
  }

  async function submitProgramme(name) {
    try {
      const r = await call("desk_submit_programme", { programme: name });
      toast(r.already ? "Already submitted." :
        "Programme submitted — the block plans are created.", "good");
      await load();
    } catch (e) { /* already surfaced */ }
  }

  async function deleteDraft(name, closeModal) {
    const ok = await confirmModal("Delete this draft?",
      `${name} and anything pulled into it — blocks, products, calculated lines — goes with it. This cannot be undone.`,
      "Delete draft");
    if (!ok) return;
    try {
      await doc("delete", { doctype: "Fertilizer Programme", name });
      toast("Draft deleted.", "good");
      closeModal();
      await load();
    } catch (e) { /* already surfaced */ }
  }

  async function openProgramme(name) {
    // Fetched by name rather than read off state.data.current, so every row
    // in "All programmes" opens - not only whichever one the desk happened
    // to pick as "current" (the newest draft, or failing that the newest
    // programme at all).
    let c, sum;
    try {
      [c, sum] = await Promise.all([
        call("get_programme_detail", { programme: name }),
        call("get_programme_summary", { programme: name }).catch(() => null),
      ]);
    } catch (e) { return; /* already surfaced */ }

    const prods = c.products || [];
    const chosen = prods.filter((p) => p.item).length;
    const required = prods.reduce((a, p) => a + (p.required || 0), 0);
    const draft = c.docstatus === 0;

    const body = document.createElement("div");
    body.innerHTML = `
      <div class="kpi-grid" style="margin-bottom:18px">
        <div class="kpi"><div class="kpi__label">State</div>
          <div class="kpi__value ${stateKind(progState(c))}">${esc(progState(c))}</div>
          <div class="kpi__unit">${esc(c.period_type === "Custom Period"
            ? c.start_month + " – " + c.end_month : "Full year")}</div></div>
        <div class="kpi"><div class="kpi__label">Blocks</div>
          <div class="kpi__value">${num(c.blocks)}</div>
          <div class="kpi__unit">${num(c.lines)} planned rounds</div></div>
        <div class="kpi"><div class="kpi__label">Fertilizer committed</div>
          <div class="kpi__value">${num(required)}</div>
          <div class="kpi__unit">kg across ${prods.length} products</div></div>
        <div class="kpi"><div class="kpi__label">Products chosen</div>
          <div class="kpi__value ${chosen === prods.length && prods.length ? "good" : "bad"}">${num(chosen)}/${num(prods.length)}</div>
          <div class="kpi__unit">${prods.length - chosen ? (prods.length - chosen) + " still to choose" : "all chosen"}</div></div>
        ${sum ? `
        <div class="kpi"><div class="kpi__label">Rounds applied</div>
          <div class="kpi__value ${sum.applied_rounds === sum.total_rounds && sum.total_rounds ? "good" : ""}">${num(sum.applied_rounds)}/${num(sum.total_rounds)}</div>
          <div class="kpi__unit">${num(sum.pct_applied)}% done</div></div>
        <div class="kpi"><div class="kpi__label">Overdue rounds</div>
          <div class="kpi__value ${sum.overdue_rounds ? "bad" : "good"}">${num(sum.overdue_rounds)}</div>
          <div class="kpi__unit">month passed, not yet applied</div></div>
        <div class="kpi"><div class="kpi__label">Estimated cost</div>
          <div class="kpi__value">${num(sum.cost_estimate)}</div>
          <div class="kpi__unit">at current buying price</div></div>
        <div class="kpi"><div class="kpi__label">Store requests</div>
          <div class="kpi__value ${sum.pending_requests ? "warn" : ""}">${num(sum.pending_requests)}</div>
          <div class="kpi__unit">raised for this programme</div></div>` : ""}
      </div>

      <div class="card" style="box-shadow:none;padding:0 0 18px">
        <div class="card__head"><h3>Fertilizer by month</h3>
          <span class="meta">What the calendar spreads it over</span></div>
        <div class="chartbox"><canvas id="pg-month"></canvas></div>
      </div>

      <div class="card" style="box-shadow:none;padding:0">
        <div class="card__head"><h3>Cover per product</h3>
          <span class="meta">Store against what this programme still needs</span></div>
        <div id="pg-stock"></div>
      </div>`;

    const foot = [];
    if (draft) {
      foot.push({ label: "Delete draft", cls: "btn--bad",
        onClick: (h) => deleteDraft(name, () => h.close()) });
      foot.push({ label: "Submit programme", cls: "btn--ink",
        onClick: async (h) => { await submitProgramme(name); h.close(); } });
    } else {
      foot.push({ label: "Close" });
    }

    // Submit and Delete belong to drafts. A submitted programme has already
    // created its block plans, so say so rather than leaving a footer with a
    // lone Close that reads as though the buttons failed to load.
    if (!draft) {
      const note = document.createElement("div");
      note.className = "none";
      note.style.cssText = "text-align:left;padding:14px 0 0";
      note.textContent = c.docstatus === 1
        ? "This programme is submitted and its block plans exist, so Submit and Delete no longer apply. They appear on a draft."
        : "This programme is cancelled.";
      body.appendChild(note);
    }

    modal({ title: c.name, sub: `${c.season} · ${c.farm || ""} · ${c.crop || ""}`,
            body, size: "wide", foot });

    // cover bars, straight from product_selections - already scoped to this
    // one programme, so a second programme on the same farm/season cannot
    // bleed its own required/available figures into this view.
    $("#pg-stock", body).innerHTML = prods.map((p) => {
      const pct = p.required ? Math.min(100, Math.round(p.available / p.required * 100)) : 100;
      const ok = !p.required || p.shortfall <= 0;
      return `<div class="hb">
        <div class="hb__name">${esc(p.item_name || p.item || p.product)}</div>
        <div class="hb__lane"><div class="hb__est"></div>
          <div class="hb__act${ok ? "" : " bad"}" style="width:${pct}%"></div></div>
        <div class="hb__pct">${pct}%</div>
      </div>`;
    }).join("") || `<div class="none">No products loaded yet.</div>`;

    const months = sum ? sum.monthly : [];
    if (window.Chart && months && months.length) {
      new Chart($("#pg-month", body), {
        type: "bar",
        data: {
          labels: months.map((m) => m.month),
          datasets: [{
            label: "Kg", data: months.map((m) => m.qty || 0),
            backgroundColor: "#24463c", borderRadius: 6,
          }],
        },
        options: {
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, grid: { color: "rgba(10,10,10,.06)" } },
                    x: { grid: { display: false } } },
          maintainAspectRatio: false,
          responsive: true,
        },
      });
    } else {
      $("#pg-month", body).replaceWith(Object.assign(document.createElement("div"),
        { className: "none", textContent: "No monthly split yet — run the calculation." }));
    }
  }

  // ----------------------------------------------------------------- other tabs
  // ----------------------------------------------------------------- other tabs
  function bar(pct, kind) {
    const w = Math.max(0, Math.min(100, Number(pct) || 0));
    return `<div class="bar"><div class="bar__fill${kind ? " " + kind : ""}" style="width:${w}%"></div></div>`;
  }
  const stateKindFor = (st) =>
    st === "Completed" ? "good" : st === "In progress" ? "warn"
    : st === "No plan" ? "mute" : "info";

  let allBlocks = [];

  async function loadPlans() {
    // every block, searchable
    try {
      allBlocks = await call("get_desk_blocks",
        { season: state.season || null });
      drawBlocks();
    } catch (e) { $("#blocks").innerHTML = `<div class="none">Could not load blocks.</div>`; }

    // and the ones with work outstanding
    try {
      const rows = await call("get_plan_queue",
        { season: state.season || null });
      $("#plans-meta").textContent = rows.length + " blocks";
      $("#plans").innerHTML = rows.map((r) => `
        <div class="qrow" data-block="${esc(r.block)}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.block)}</div>
            <div class="qrow__meta">${esc(r.section || "")} · ${num(r.rounds)} rounds ·
              ${num(r.total_kg, 0)} kg · next ${esc(r.next_month || "—")}</div>
          </div>
          <div class="qrow__right">${r.issued
            ? pill(num(r.issued) + " issued", "good") : pill("awaiting store", "warn")}</div>
        </div>`).join("") || `<div class="none">No block has work outstanding.</div>`;
    } catch (e) { $("#plans").innerHTML = `<div class="none">Could not load.</div>`; }
  }

  function drawBlocks() {
    const q = ($("#block-search").value || "").toLowerCase();
    const rows = allBlocks.filter((b) =>
      !q || (b.block || "").toLowerCase().includes(q) || (b.section || "").toLowerCase().includes(q));
    $("#blocks-meta").textContent = `${rows.length} of ${allBlocks.length}`;
    $("#blocks").innerHTML = rows.map((b) => `
      <div class="qrow" data-block="${esc(b.block)}" style="cursor:pointer">
        <div class="qrow__mark">${esc((b.block || "?").slice(0, 2))}</div>
        <div>
          <div class="qrow__name">${esc(b.block)}</div>
          <div class="qrow__meta">${esc(b.section || "")} · ${num(b.area_ha, 2)} ha ·
            ${num(b.tree_count)} trees · ${num(b.done)}/${num(b.rounds)} rounds</div>
        </div>
        <div class="qrow__right">${bar(b.pct, b.pct >= 100 ? "good" : b.pct ? "warn" : "")}
          ${pill(b.state, stateKindFor(b.state))}</div>
      </div>`).join("") || `<div class="none">No block matches.</div>`;
  }

  /** One block, opened from either list. */
  async function openBlock(block) {
    let d;
    try { d = await call("get_block_detail", { block, season: state.season || null }); }
    catch (e) { return; }
    const i = d.info, y = d.yield;
    const vsAvg = Number(y.vs_avg_pct) || 0;
    const body = `
      <div class="statline"><span class="statline__k">Section</span>
        <span class="statline__v">${esc(i.section || "—")}</span></div>
      <div class="statline"><span class="statline__k">Area · trees</span>
        <span class="statline__v">${num(i.area_ha, 2)} ha · ${num(i.tree_count)}</span></div>
      <div class="statline"><span class="statline__k">Rounds done</span>
        <span class="statline__v">${num(d.done)} of ${num(d.rounds)}</span></div>
      ${bar(d.pct, d.pct >= 100 ? "good" : d.pct ? "warn" : "")}
      <div class="statline" style="margin-top:14px"><span class="statline__k">Planned · applied</span>
        <span class="statline__v">${num(d.planned_kg)} · ${num(d.actual_kg)} kg</span></div>

      <div style="text-align:center;margin:20px 0">
        <div style="font-size:40px;line-height:1">🌳</div>
        <div style="margin-top:6px">${(d.dose_by_product || []).map((p) =>
          `<div style="font:700 15px var(--sans);color:var(--ink)">
            ${esc(p.product_name)} · ${num(p.dose_per_tree_g, 0)} g/tree</div>`).join("")
          || `<div class="none" style="padding:0">No rounds planned.</div>`}</div>
      </div>

      <div class="card__head" style="margin:22px 0 10px"><h3>Last year's yield</h3></div>
      <div class="statline"><span class="statline__k">This block</span>
        <span class="statline__v">${num(y.block)} kg/ha</span></div>
      ${bar(y.farm_best ? (y.block / y.farm_best) * 100 : 0,
            vsAvg >= 0 ? "good" : "warn")}
      <div class="statline"><span class="statline__k">Farm average · best</span>
        <span class="statline__v">${num(y.farm_avg)} · ${num(y.farm_best)} kg/ha</span></div>
      <div class="none" style="text-align:left;padding:10px 0">
        ${vsAvg >= 0 ? "Above" : "Below"} the farm average by ${num(Math.abs(vsAvg))}% —
        which is what put this block in its yield tier, and so what set these rates.
      </div>

      <div class="card__head" style="margin:18px 0 10px"><h3>Rounds</h3></div>
      <div class="queue queue--5">${d.plans.map((p) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((p.application_month || "?").slice(0, 3))}</div>
          <div><div class="qrow__name">${esc(p.fertilizer_product_name || p.fertilizer_product)}</div>
          <div class="qrow__meta">${esc(p.application_month)}${p.application_year ? " " + p.application_year : ""} ·
            ${num(p.total_kg_required)} kg · ${num(p.dose_per_tree_g, 1)} g/tree
            ${p.times_pushed ? " · pushed " + p.times_pushed + "×" : ""}</div></div>
          <div class="qrow__right">${pill(p.status,
            p.status === "Applied" || p.status === "Verified" ? "good"
            : p.status === "Issued" ? "warn" : "mute")}</div>
        </div>`).join("") || `<div class="none">No rounds planned.</div>`}</div>`;
    modal({ title: block, sub: `${i.farm || ""} · ${i.crop || ""}`, body, size: "wide",
            foot: [{ label: "Close" }] });
  }

  async function loadRequests() {
    const el = $("#requests");
    try {
      const rows = await call("get_desk_store_requests", {});
      state.requests = rows;
      $("#req-meta").textContent = rows.length + " requests";
      el.innerHTML = rows.map((r, idx) => `
        <div class="qrow" data-req="${idx}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.item_code_name || r.item_code || r.name)}</div>
            <div class="qrow__meta">${esc(r.block || "—")} · ${num(r.qty)} kg ·
              ${esc(r.employee_name || "unknown supervisor")} · ${esc(r.transaction_date || "")}</div>
          </div>
          <div class="qrow__right">${pill(r.state || "—",
            r.state === "Approved" || r.state === "Issued" ? "good"
            : r.state === "Rejected" || r.state === "Cancelled" ? "bad" : "warn")}</div>
        </div>`).join("") || `<div class="none">No supervisor has raised a request yet.</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load requests.</div>`; }
  }

  function openRequest(idx) {
    const r = (state.requests || [])[idx];
    if (!r) return;
    const body = `
      <div class="statline"><span class="statline__k">Supervisor</span>
        <span class="statline__v">${esc(r.employee_name || r.employee || "—")}</span></div>
      <div class="statline"><span class="statline__k">Amount requested</span>
        <span class="statline__v">${num(r.qty)} kg</span></div>
      <div class="statline"><span class="statline__k">Product</span>
        <span class="statline__v">${esc(r.item_code_name || r.item_code || "—")}</span></div>
      <div class="statline"><span class="statline__k">Block</span>
        <span class="statline__v">${esc(r.block || "—")}</span></div>
      <div class="statline"><span class="statline__k">Section</span>
        <span class="statline__v">${esc(r.section || "—")}</span></div>
      <div class="statline"><span class="statline__k">For the month of</span>
        <span class="statline__v">${esc(r.application_month || "—")}</span></div>
      <div class="statline"><span class="statline__k">Raised on</span>
        <span class="statline__v">${esc(r.transaction_date || "—")}</span></div>
      <div class="statline"><span class="statline__k">Status</span>
        <span class="statline__v">${esc(r.state || r.status || "—")}</span></div>
      <div class="none" style="text-align:left">Request ${esc(r.name)}${
        r.plan ? ` · plan ${esc(r.plan)}` : ""}</div>`;
    modal({ title: "Store request", sub: r.block || "", body, foot: [{ label: "Close" }] });
  }

  async function loadApplications() {
    try {
      const rows = await call("get_desk_applications",
        { season: state.season || null });
      state.apps = rows;
      $("#apps-meta").textContent = `${rows.length} recorded`;
      $("#apps").innerHTML = rows.map((r, idx) => `
        <div class="qrow" data-app="${idx}" style="cursor:pointer">
          <div class="qrow__mark">${esc((r.block || "?").slice(0, 2))}</div>
          <div>
            <div class="qrow__name">${esc(r.fertilizer_product_name || r.fertilizer_product)}</div>
            <div class="qrow__meta">${esc(r.block)} · ${num(r.actual_quantity_applied_kg, 1)} kg ·
              ${esc(r.application_date || "")} · ${esc(r.supervisor_name || "")}</div>
          </div>
          <div class="qrow__right">${r.applied_in_full ? pill("in full", "good") : pill("partial", "warn")}</div>
        </div>`).join("") || `<div class="none">Nothing recorded yet.</div>`;
    } catch (e) { $("#apps").innerHTML = `<div class="none">Could not load applications.</div>`; }

    // planned against applied, per section
    try {
      const rows = await call("get_variance_by_section",
        { season: state.season || null });
      $("#variance").innerHTML = rows.map((r) => `
        <div class="hb" data-section="${esc(r.section)}" style="cursor:pointer">
          <div class="hb__name">${esc(r.section || "—")}</div>
          <div class="hb__lane">
            <div class="hb__est"></div>
            <div class="hb__act${r.pct >= 100 ? "" : " bad"}"
              style="width:${Math.max(0, Math.min(100, r.pct))}%"></div>
          </div>
          <div class="hb__pct">${num(r.actual)} / ${num(r.planned)} kg</div>
        </div>`).join("") || `<div class="none">Nothing planned yet.</div>`;
    } catch (e) { $("#variance").innerHTML = `<div class="none">Could not load.</div>`; }
  }

  function openApplication(idx) {
    const a = (state.apps || [])[idx];
    if (!a) return;
    const body = `
      <div class="statline"><span class="statline__k">Block</span>
        <span class="statline__v">${esc(a.block)}</span></div>
      <div class="statline"><span class="statline__k">Product</span>
        <span class="statline__v">${esc(a.fertilizer_product_name || a.fertilizer_product)}</span></div>
      <div class="statline"><span class="statline__k">Date</span>
        <span class="statline__v">${esc(a.application_date || "—")}</span></div>
      <div class="statline"><span class="statline__k">Planned · applied</span>
        <span class="statline__v">${num(a.planned_quantity_kg, 1)} · ${num(a.actual_quantity_applied_kg, 1)} kg</span></div>
      <div class="statline"><span class="statline__k">Variance</span>
        <span class="statline__v">${num(a.variance_kg, 1)} kg</span></div>
      ${a.applied_in_full ? "" : `<div class="none" style="text-align:left">
        Partial — ${esc(a.partial_reason || "no reason given")}</div>`}
      <div class="statline"><span class="statline__k">Method · weather</span>
        <span class="statline__v">${esc(a.application_method || "—")} · ${esc(a.weather_conditions || "—")}</span></div>
      <div class="statline"><span class="statline__k">Supervisor</span>
        <span class="statline__v">${esc(a.supervisor_name || a.supervisor || "—")}</span></div>
      <div class="statline"><span class="statline__k">Applicators</span>
        <span class="statline__v">${esc((a.applicators || []).join(", ") || "—")}</span></div>
      <div class="none" style="text-align:left">${esc(a.name)}${
        a.material_request ? ` · request ${esc(a.material_request)}` : ""}</div>`;
    modal({ title: "Application", sub: a.block, body, foot: [{ label: "Close" }] });
  }

  async function openSectionVariance(section) {
    let rows;
    try {
      rows = await call("get_variance_by_block",
        { section, season: state.season || null });
    } catch (e) { return; }
    const body = rows.map((r) => `
      <div class="hb">
        <div class="hb__name">${esc(r.block)}</div>
        <div class="hb__lane">
          <div class="hb__est"></div>
          <div class="hb__act${r.pct >= 100 ? "" : " bad"}"
            style="width:${Math.max(0, Math.min(100, r.pct))}%"></div>
        </div>
        <div class="hb__pct">${num(r.actual)} / ${num(r.planned)} kg</div>
      </div>`).join("") || `<div class="none">Nothing planned in this section.</div>`;
    modal({ title: section, sub: "Planned against applied, per block",
            body, size: "wide", foot: [{ label: "Close" }] });
  }

  async function loadStock() {
    const el = $("#stock");
    try {
      const rows = await call("get_desk_stock",
        { season: state.season || null });
      const inProg = rows.filter((r) => r.in_programme);
      const rest = rows.filter((r) => !r.in_programme);
      const line = (r) => `
        <div class="qrow">
          <div class="qrow__mark">${r.sufficient ? "✓" : "!"}</div>
          <div>
            <div class="qrow__name">${esc(r.item_name || r.item_code)}</div>
            <div class="qrow__meta">${esc(r.item_code)} · ${num(r.stock)} ${esc(r.uom || "kg")} in store${
              r.in_programme ? ` · ${num(r.required)} needed` : ""}</div>
          </div>
          <div class="qrow__right">${r.in_programme
            ? (r.sufficient ? pill("covers it", "good")
                            : pill("short " + num(r.shortfall) + " kg", "bad"))
            : pill("not in the programme", "mute")}</div>
        </div>`;
      el.innerHTML =
        `<div class="card__head"><h3>Needed by this programme</h3>
           <span class="meta">${inProg.length} items</span></div>
         <div class="queue">${inProg.map(line).join("") || `<div class="none">Nothing required yet — calculate the programme first.</div>`}</div>
         <div class="card__head" style="margin-top:22px"><h3>Also in the store</h3>
           <span class="meta">${rest.length} items</span></div>
         <div class="queue queue--5">${rest.map(line).join("") || `<div class="none">—</div>`}</div>`;
    } catch (e) { el.innerHTML = `<div class="none">Could not load stock.</div>`; }
  }

  // ----------------------------------------------------------------- supervisors
  /* What a supervisor was last doing, in words. The endpoint reports the call
   * they made; nobody wants to read "get_pending_plans_for_section". */
  const DOING = {
    record_application: "Recording an application",
    create_store_request: "Requesting fertilizer",
    mark_attendance: "Marking attendance",
    get_attendance_by_block: "On the attendance register",
    add_applicators: "Adding applicators", add_applicator: "Adding an applicator",
    remove_applicator: "Updating the team", assign_block: "Assigning a block",
    get_my_applicators: "Looking at the team", get_my_applicators_by_section: "Looking at the team",
    get_available_employees_for_team: "Choosing applicators",
    get_pending_plans_for_section: "Browsing upcoming work",
    get_pending_plans_for_block: "Browsing upcoming work",
    get_sections_with_pending_work: "Browsing upcoming work",
    get_upcoming_and_overdue: "Checking what is due",
    get_issued_blocks_in_section: "Choosing a block to record",
    get_sections_with_issued_work: "Choosing a block to record",
    get_store_requests: "Checking store requests",
    get_block_progress: "Looking at block progress",
    get_home_metrics: "On the home screen",
    get_field_programmes: "On the home screen",
  };

  const doingText = (m) => (m && (DOING[m] || "Using the app")) || "";

  function agoText(sec) {
    if (sec == null) return "not seen yet";
    if (sec < 60) return "just now";
    const m = Math.round(sec / 60);
    if (m < 60) return m + " min ago";
    const h = Math.floor(m / 60), r = m % 60;
    return h + " h" + (r ? " " + r + " min" : "") + " ago";
  }

  const PRESENCE = {
    online: { label: "Online", kind: "good" },
    today:  { label: "Seen today", kind: "info" },
    away:   { label: "Not seen today", kind: "mute" },
    none:   { label: "Not seen yet", kind: "mute" },
  };

  let supTimer = null;

  async function loadSupervisors() {
    let d;
    try { d = await call("get_active_supervisors", {}, { quiet: true }); }
    catch (e) {
      $("#sup-list").innerHTML = `<div class="none">Could not load supervisors.</div>`;
      return;
    }
    state.sups = d.supervisors || [];
    const sm = d.summary || {};

    const badge = $("#sup-badge");
    if (sm.online) { badge.textContent = sm.online; badge.style.display = ""; }
    else badge.style.display = "none";

    $("#sup-kpis").innerHTML = [
      kpi("Online now", num(sm.online), sm.online ? "good" : "", `active in the last ${d.window} min`),
      kpi("Seen today", num(sm.today), "info", "including those online"),
      kpi("Supervisors", num(sm.total), "", "with a team in the field"),
    ].join("");
    $("#sup-meta").textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · refreshes every 30 seconds`;

    $("#sup-list").innerHTML = state.sups.map((r, i) => {
      const pr = PRESENCE[r.state] || PRESENCE.none;
      const initials = (r.name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
      const doing = r.state === "online" ? doingText(r.last_method) : "";
      return `<div class="qrow" data-sup="${i}" style="cursor:pointer">
        <div class="qrow__mark">${esc(initials)}<span class="pdot pdot--${esc(r.state)}"></span></div>
        <div>
          <div class="qrow__name">${esc(r.name || r.employee)}</div>
          <div class="qrow__meta">${esc(r.number || r.employee)} ·
            ${r.state === "none" ? "not seen yet" : esc(agoText(r.age_seconds))}${
              r.via ? " · " + (r.via === "app" ? "mobile app" : "desk") : ""}${
              doing ? " · " + esc(doing) : ""}</div>
        </div>
        <div class="qrow__right">
          <div class="supstat"><div class="supstat__v">${num(r.apps_today)} applied today</div>
            <div class="supstat__k">${num(r.team_size)} on team · ${num(r.attendance_today)} marked</div></div>
          ${pill(pr.label, pr.kind)}
        </div>
      </div>`;
    }).join("") || `<div class="none">No supervisors to show yet. A supervisor appears here once
      they have a team, or have signed in to the app.</div>`;
  }

  function openSupervisor(idx) {
    const r = (state.sups || [])[idx];
    if (!r) return;
    const pr = PRESENCE[r.state] || PRESENCE.none;
    const seen = r.age_seconds == null ? "not seen yet"
      : `${agoText(r.age_seconds)} (${new Date(Date.now() - r.age_seconds * 1000)
          .toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })})`;
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="statline"><span class="statline__k">Status</span>
        <span class="statline__v">${pill(pr.label, pr.kind)}</span></div>
      <div class="statline"><span class="statline__k">Last request</span>
        <span class="statline__v">${esc(seen)}</span></div>
      <div class="statline"><span class="statline__k">Using</span>
        <span class="statline__v">${r.via ? (r.via === "app" ? "Mobile app" : "Desk") : "—"}</span></div>
      <div class="statline"><span class="statline__k">Last activity</span>
        <span class="statline__v">${esc(doingText(r.last_method) || "—")}</span></div>
      <div class="statline"><span class="statline__k">Employee</span>
        <span class="statline__v">${esc(r.number || r.employee)}${r.user ? " · " + esc(r.user) : ""}</span></div>
      <div class="statline"><span class="statline__k">Farm</span>
        <span class="statline__v">${esc((r.farms || []).join(", ") || "—")}</span></div>

      <div class="card__head" style="margin:20px 0 10px"><h3>Today</h3></div>
      <div class="statline"><span class="statline__k">Applications recorded</span>
        <span class="statline__v">${num(r.apps_today)} · ${num(r.kg_today, 1)} kg</span></div>
      <div class="statline"><span class="statline__k">Attendance marked</span>
        <span class="statline__v">${num(r.attendance_today)} of ${num(r.team_size)}</span></div>
      ${bar(r.team_size ? Math.min(100, r.attendance_today * 100 / r.team_size) : 0,
            r.attendance_today >= r.team_size && r.team_size ? "good" : r.attendance_today ? "warn" : "")}

      <div class="card__head" style="margin:20px 0 10px"><h3>Team · ${num(r.team_size)}</h3>
        <span class="meta">${esc((r.blocks || []).join(", ") || "no block assigned")}</span></div>
      <div class="queue queue--5">${(r.team || []).map((m) => `
        <div class="qrow">
          <div class="qrow__mark">${esc((m.name || "?").slice(0, 2).toUpperCase())}</div>
          <div><div class="qrow__name">${esc(m.name)}</div>
          <div class="qrow__meta">${esc(m.block || "no block assigned")}</div></div>
        </div>`).join("") || `<div class="none">No one on this team yet.</div>`}</div>`;
    modal({ title: r.name || r.employee, sub: `${r.number || r.employee} · supervisor`,
            body, size: "wide", foot: [{ label: "Close" }] });
  }

  function downloadExcel(programme, section) {
    let url = "/api/method/mutaracnp.mutaracnp.api.export_programme_excel?programme="
      + encodeURIComponent(programme);
    if (section) url += "&section=" + encodeURIComponent(section);
    window.open(url, "_blank");
  }

  /** Export Excel - whole programme, or just one section in the same
   *  format. Sections come straight off this programme's own blocks, so
   *  there's nothing to pick when it's scoped to just one already. */
  function openExportChoice(c) {
    const sections = c.sections || [];
    if (sections.length <= 1) {
      downloadExcel(c.name, sections[0]);
      return;
    }

    const body = document.createElement("div");
    const renderChoice = () => {
      body.innerHTML = `
        <div class="queue">
          <div class="qrow" data-export-scope="programme" style="cursor:pointer">
            <div class="qrow__mark" style="background:transparent">📘</div>
            <div><div class="qrow__name">Entire Programme</div>
            <div class="qrow__meta">Every section, ${sections.length} in total</div></div>
          </div>
          <div class="qrow" data-export-scope="section" style="cursor:pointer">
            <div class="qrow__mark" style="background:transparent">📄</div>
            <div><div class="qrow__name">Section</div>
            <div class="qrow__meta">Pick one section to export on its own</div></div>
          </div>
        </div>`;
    };
    const renderSections = () => {
      body.innerHTML = `
        <div class="queue">${sections.map((s) => `
          <div class="qrow" data-export-section="${esc(s)}" style="cursor:pointer">
            <div class="qrow__mark" style="background:transparent">📄</div>
            <div><div class="qrow__name">${esc(s)}</div></div>
          </div>`).join("")}</div>`;
    };
    renderChoice();

    const m = modal({
      title: "Export Excel", sub: c.name,
      body, foot: [{ label: "Cancel" }],
    });
    body.addEventListener("click", (e) => {
      const scope = e.target.closest("[data-export-scope]");
      if (scope) {
        if (scope.dataset.exportScope === "programme") { downloadExcel(c.name); m.close(); }
        else renderSections();
        return;
      }
      const sec = e.target.closest("[data-export-section]");
      if (sec) { downloadExcel(c.name, sec.dataset.exportSection); m.close(); }
    });
  }

  // --------------------------------------------------------------------- actions
  async function act(button) {
    const kind = button.dataset.act;
    const c = state.data && state.data.current;
    if (!c) return;

    if (kind === "export_excel") {
      openExportChoice(c);
      return;
    }
    if (kind === "delete_draft") {
      const sure = await confirmModal("Delete draft?",
        `${c.name} and everything calculated on it will be gone for good. This cannot be undone.`);
      if (!sure) return;
    }

    const label = button.textContent;
    button.disabled = true; button.textContent = "Working…";
    try {
      if (kind === "pull_blocks") {
        const r = await call("desk_pull_blocks", { programme: c.name });
        toast(`${r.blocks} blocks pulled.`, "good");
      } else if (kind === "load_products") {
        const r = await call("load_programme_products", { programme: c.name });
        toast(`${(r.products || []).length} products listed. Choose an item for each.`, "good");
      } else if (kind === "calculate") {
        const r = await call("desk_calculate", { programme: c.name });
        toast(`${r.lines} programme lines generated.`, "good");
      } else if (kind === "delete_draft") {
        await call("desk_delete_draft", { programme: c.name });
        toast(`${c.name} deleted.`, "good");
      } else if (kind === "submit") {
        const r = await call("desk_submit_programme", { programme: c.name });
        toast(r.already ? "Already submitted." :
          "Programme submitted — the block plans are created.", "good");
      }
      await load();
    } catch (e) {
      if (!e.handled) toast(e.message, "bad");
      button.disabled = false; button.textContent = label;
    }
  }

  /** A yes/no confirmation, styled like everything else here instead of a
   *  bare browser confirm(). Resolves true only if Delete was clicked. */
  function confirmModal(title, message) {
    return new Promise((resolve) => {
      let decided = false;
      modal({
        title, body: `<div class="none" style="text-align:left;padding:0">${esc(message)}</div>`,
        foot: [
          { label: "Cancel", onClick: (h) => { decided = true; h.close(); resolve(false); } },
          { label: "Delete", cls: "btn--bad", onClick: (h) => { decided = true; h.close(); resolve(true); } },
        ],
        onClose: () => { if (!decided) resolve(false); },
      });
    });
  }

  /** Every block this programme covers, grouped by section, one Kg/Ha input
   *  per product per block - scrollable as one screen rather than a popup
   *  per block, since the whole point is editing all of them in one sitting. */
  function gridTableHtml(grid) {
    return grid.sections.map((sec) => `
      <div class="card" style="margin-bottom:16px">
        <div class="card__head"><h3>${esc(sec.section || "(No section)")}</h3>
          <span class="meta">${sec.blocks.length} block${sec.blocks.length === 1 ? "" : "s"}</span></div>
        <table class="gridtbl">
          <thead><tr>
            <th>Block</th><th>Tier</th><th>Area (ha)</th><th>Trees</th>
            ${grid.products.map((p) => `<th>${esc(p.product_name)}<br><small>Kg/Ha</small></th>`).join("")}
          </tr></thead>
          <tbody>
            ${sec.blocks.map((b) => `<tr data-row-block="${esc(b.block)}">
              <td>${esc(b.block)}</td><td>${esc(b.yield_tier || "—")}</td>
              <td>${num(b.area_ha, 2)}</td><td>${num(b.tree_count)}</td>
              ${grid.products.map((p) => {
                const r = (b.rates || []).find((x) => x.product === p.product);
                return `<td><input type="number" step="any" data-rate data-product="${esc(p.product)}"
                  value="${r ? r.kg_per_ha : 0}"></td>`;
              }).join("")}
            </tr>`).join("")}
          </tbody>
        </table>
      </div>`).join("") || `<div class="none">No blocks on this programme yet - pull them first.</div>`;
  }

  /** Round Tier / Round Block - the guided rounding tool above the free-form
   * grid. A tier (15T, 18T, ...) is a yield classification, not a per-
   * section thing - a 15T block in one section and a 15T block in another
   * are still both 15T, so Round Tier sets one Kg/Ha across every block
   * carrying that tier farm-wide, not one section at a time. Block rounding
   * sets one block's total Kg directly - the figure the agronomist actually
   * reads off the ground (e.g. "732 kg for this block") - and only that
   * block's dose per tree changes. Tier rounding is meant to be applied
   * first, since a later block rounding simply overrides whatever a tier
   * rounding set. */
  function roundingToolHtml(grid) {
    const tiers = [];
    grid.sections.forEach((sec) => (sec.blocks || []).forEach((b) => {
      if (b.yield_tier && !tiers.includes(b.yield_tier)) tiers.push(b.yield_tier);
    }));
    tiers.sort();
    const blocks = [];
    grid.sections.forEach((sec) => (sec.blocks || []).forEach((b) => blocks.push(b)));

    return `
      <div class="card" style="margin-bottom:16px">
        <div class="card__head"><h3>Round Tier or Round Block</h3>
          <span class="meta">Apply straight away - the grid below updates to match</span></div>
        <div class="field"><label>Product</label>
          <select id="rt-product">${grid.products.map((p) =>
            `<option value="${esc(p.product)}">${esc(p.product_name)}</option>`).join("")}</select>
        </div>
        <div class="field"><label>Scope</label>
          <select id="rt-scope">
            <option value="tier">Round Tier - one Kg/Ha across every block in a tier, farm-wide</option>
            <option value="block">Round Block - one total Kg for a single block</option>
          </select>
        </div>
        <div id="rt-tier-fields" class="field">
          <label>Tier</label>
          <select id="rt-tier">${tiers.map((t) =>
            `<option value="${esc(t)}">${esc(t)}</option>`).join("")
            || `<option value="">No tiers yet - calculate the programme first</option>`}</select>
          <label style="margin-top:10px">New Kg/Ha</label>
          <input type="number" step="any" id="rt-tier-value" placeholder="e.g. 366">
        </div>
        <div id="rt-block-fields" class="field" style="display:none">
          <label>Block</label>
          <select id="rt-block">${blocks.map((b) =>
            `<option value="${esc(b.block)}">${esc(b.block)} (${num(b.area_ha, 2)} ha)</option>`).join("")}</select>
          <label style="margin-top:10px">New total Kg</label>
          <input type="number" step="any" id="rt-block-value" placeholder="e.g. 732">
        </div>
        <button type="button" class="btn btn--ink" id="rt-apply" style="margin-top:12px">Apply</button>
      </div>`;
  }

  function wireRoundingTool(root, name, grid, onApplied) {
    const scopeSel = $("#rt-scope", root);
    scopeSel.addEventListener("change", () => {
      const tier = scopeSel.value === "tier";
      $("#rt-tier-fields", root).style.display = tier ? "" : "none";
      $("#rt-block-fields", root).style.display = tier ? "none" : "";
    });

    $("#rt-apply", root).addEventListener("click", async () => {
      const product = $("#rt-product", root).value;
      const productName = (grid.products.find((p) => p.product === product) || {}).product_name || product;
      const rates = [];
      let confirmMsg;
      if (scopeSel.value === "tier") {
        const yield_tier = $("#rt-tier", root).value;
        const kg_per_ha = Number($("#rt-tier-value", root).value);
        if (!yield_tier || !Number.isFinite(kg_per_ha)) { toast("Choose a tier and a Kg/Ha value.", "bad"); return; }
        const sectionsHit = new Set();
        grid.sections.forEach((sec) => (sec.blocks || []).forEach((b) => {
          if (b.yield_tier === yield_tier) {
            rates.push({ block: b.block, product, kg_per_ha });
            sectionsHit.add(sec.section);
          }
        }));
        confirmMsg = `Set ${productName} to ${kg_per_ha} Kg/Ha for ${rates.length} block`
          + `${rates.length === 1 ? "" : "s"} in tier ${yield_tier} across ${sectionsHit.size} section`
          + `${sectionsHit.size === 1 ? "" : "s"}.`;
      } else {
        const block = $("#rt-block", root).value;
        const total_kg = Number($("#rt-block-value", root).value);
        if (!block || !Number.isFinite(total_kg)) { toast("Choose a block and a total Kg value.", "bad"); return; }
        rates.push({ block, product, total_kg });
        confirmMsg = `Set ${productName} to ${total_kg} kg total for ${block}.`;
      }
      if (!rates.length) { toast("No blocks carry that tier.", "bad"); return; }
      try {
        await call("desk_save_rates", { programme: name, rates });
        toast(confirmMsg, "good");
        await onApplied();
      } catch (e) { /* already surfaced */ }
    });
  }

  async function openRatesGrid(name) {
    let grid;
    try { grid = await call("desk_get_rate_grid", { programme: name }); }
    catch (e) { return; }

    const body = document.createElement("div");
    body.style.maxHeight = "70vh";
    body.style.overflowY = "auto";
    const toolSlot = document.createElement("div");
    const gridSlot = document.createElement("div");
    body.appendChild(toolSlot);
    body.appendChild(gridSlot);

    function renderAll() {
      toolSlot.innerHTML = roundingToolHtml(grid);
      gridSlot.innerHTML = gridTableHtml(grid);
      wireRoundingTool(body, name, grid, async () => {
        grid = await call("desk_get_rate_grid", { programme: name });
        renderAll();
      });
    }
    renderAll();

    modal({
      title: "Edit Programme", sub: `${name} · round by tier or block, or edit any cell directly`,
      size: "wide", body,
      foot: [
        { label: "Cancel" },
        { label: "Save grid", cls: "btn--ink", onClick: async (h) => {
            const rates = [];
            $$("tr[data-row-block]", body).forEach((tr) => {
              const block = tr.dataset.rowBlock;
              $$("input[data-rate]", tr).forEach((inp) => {
                rates.push({ block, product: inp.dataset.product, kg_per_ha: Number(inp.value) || 0 });
              });
            });
            await call("desk_save_rates", { programme: name, rates });
            toast("Rates saved - totals and dose per tree recalculated.", "good");
            h.close();
            load();
          } },
      ],
    });
  }

  /** Choosing the item a product is drawn from, with stock and the rule in view. */
  async function chooseItem(product) {
    const c = state.data && state.data.current;
    if (!c) return;
    let choices;
    try { choices = await call("get_product_choices", { programme: c.name, product }); }
    catch (e) { return; }

    const opts = choices.options || [];
    if (!opts.length) {
      toast(`No item matches the search terms on ${product}.`, "bad");
      return;
    }
    const r = choices.rule;
    const rule = r
      ? `<div class="none" style="text-align:left;background:var(--surface);border-radius:14px;padding:14px">
           <b>The nutrient rule is the same whichever you pick</b><br>
           ${esc(r.nutrient || "-")} · ${num(r.rate_per_tonne)} per tonne ·
           ${num(r.bag_weight_kg)} kg bag · ${num(r.product_nutrient_pct)}% content
           ${r.apply_compost_netting ? " · compost netted" : ""}
         </div>`
      : "";
    const rows = opts.map((o) => `
      <div class="qrow" data-pick="${esc(o.item_code)}" style="cursor:pointer">
        <div class="qrow__mark" style="background:transparent">${o.item_code === choices.current
          ? `<span class="mark mark--yes">✓</span>` : ""}</div>
        <div><div class="qrow__name">${esc(o.item_name || o.item_code)}</div>
        <div class="qrow__meta">${esc(o.item_code)} · ${num(o.stock_qty)} ${esc(o.stock_uom || "kg")} in stock</div></div>
        <div class="qrow__right">${o.stock_qty > 0 ? pill("in stock", "good") : pill("empty", "bad")}</div>
      </div>`).join("");

    const wrap = document.createElement("div");
    wrap.innerHTML = rule + `<div class="queue" style="margin-top:12px">${rows}</div>`;
    const m = modal({
      title: `Which item for ${product}?`,
      sub: "Tap the one this season should be drawn from.",
      body: wrap, foot: [{ label: "Cancel" }],
    });
    wrap.addEventListener("click", async (e) => {
      const row = e.target.closest("[data-pick]");
      if (!row) return;
      try {
        await call("set_product_item",
          { programme: c.name, product, item: row.dataset.pick });
        toast(`${product} will be drawn from ${row.dataset.pick}.`, "good");
        m.close();
        await load();
      } catch (err) { /* already surfaced */ }
    });
  }

  /* The master-data grid. Order is the order someone sets a farm up in:
   * where it is, how it is divided, what grows there, what feeds it, when,
   * and what the lab said. */
  const SETUP_ORDER = ["farm", "section", "block", "crop", "rule", "product",
                       "calendar", "leaf", "norm", "soil", "soilnorm", "settings"];

  function renderSetup() {
    const grid = $("#setup-grid");
    if (!grid) return;
    grid.innerHTML = SETUP_ORDER.map((k) => {
      const sp = SPECS[k];
      if (!sp) return "";
      return `<button class="opentile" data-open-list="${esc(k)}">
        <span class="opentile__ic" style="background:${sp.tint};color:${sp.colour}">${sp.icon}</span>
        <span><span class="opentile__lb">${esc(sp.title)}</span>
        <span class="opentile__sub">${esc(sp.sub)}</span></span>
      </button>`;
    }).join("");
  }

  // ------------------------------------------------------------------ bootstrap
  function tabs() {
    $$(".tab").forEach((t) => t.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("on", x === t));
      $$(".tabpanel").forEach((p) => p.classList.toggle("on", p.id === "tab-" + t.dataset.tab));
      const which = t.dataset.tab;
      if (which === "plans") loadPlans();
      if (which === "requests") loadRequests();
      if (which === "applications") loadApplications();
      if (which === "stock") loadStock();
      if (which === "setup") renderSetup();
      // Poll only while someone is looking: a list that refreshes itself is
      // the point of the tab, but not a reason to hit the server from a hidden
      // one all afternoon.
      clearInterval(supTimer); supTimer = null;
      if (which === "supervisors") {
        loadSupervisors();
        supTimer = setInterval(loadSupervisors, 30000);
      }
    }));
  }

  function fillSelect(el, values, current) {
    el.innerHTML = values.map((v) =>
      `<option value="${esc(v)}"${v === current ? " selected" : ""}>${esc(v)}</option>`).join("");
  }

  async function load() {
    // Mutara is a single farm, so the desk has no farm picker - only season
    // varies, and every record defaults onto the one farm the API returns.
    const d = await call("get_agronomist_desk", { season: state.season || null });
    state.data = d;
    state.scope = d.farm || "";
    if (!$("#season").options.length) {
      fillSelect($("#season"), d.seasons || ["All Seasons"], state.season);
    }
    renderKpis(d);
    renderProgramme(d);
    renderProgrammeList(d);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const u = cfg.user || "";
    $("#avatar").textContent = (u.slice(0, 2) || "--").toUpperCase();
    tabs();
    $("#refresh").addEventListener("click", () => load());
    $("#block-search").addEventListener("input", () => drawBlocks());
    $("#season").addEventListener("change", (e) => { state.season = e.target.value; load(); });

    // One listener for the whole page: the buttons are re-rendered constantly,
    // so binding them individually would leak handlers on every refresh.
    document.addEventListener("click", (e) => {
      const a = e.target.closest("[data-act]");
      if (a) return act(a);
      const ch = e.target.closest("[data-choose]");
      if (ch) return chooseItem(ch.dataset.choose);
      const lst = e.target.closest("[data-open-list]");
      if (lst) return openList(lst.dataset.openList).catch(() => {});
      const nw = e.target.closest("[data-new]");
      if (nw) return openRecord(nw.dataset.new, null, () => load()).catch(() => {});
      const ed = e.target.closest("[data-edit-prog]");
      if (ed) return openRecord("programme", ed.dataset.editProg, () => load()).catch(() => {});
      const er = e.target.closest("[data-edit-rates]");
      if (er) return openRatesGrid(er.dataset.editRates).catch(() => {});
      const sp = e.target.closest("[data-sup]");
      if (sp) return openSupervisor(Number(sp.dataset.sup));
      const pg = e.target.closest("[data-prog]");
      if (pg) return openProgramme(pg.dataset.prog);
      const bl = e.target.closest("[data-block]");
      if (bl) return openBlock(bl.dataset.block);
      const rq = e.target.closest("[data-req]");
      if (rq) return openRequest(Number(rq.dataset.req));
      const ap = e.target.closest("[data-app]");
      if (ap) return openApplication(Number(ap.dataset.app));
      const sv = e.target.closest("[data-section]");
      if (sv) return openSectionVariance(sv.dataset.section);
    });

    load().catch(() => {});
    loadSupervisors().catch(() => {});
  });
})();
