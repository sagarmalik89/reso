// printer_agent/web/static/js/dashboard.js

let currentOrders = [];

function playChime() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(523.25, ctx.currentTime);
    osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.6);
  } catch (err) {
    console.warn("Audio chime prevented by browser autoplay policy:", err);
  }
}

function showToast(title, message, isSuccess = true) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<div style="font-size:1.5rem">${isSuccess ? "🔔" : "⚠️"}</div><div><div style="font-weight:600;font-size:.95rem">${title}</div><div style="font-size:.85rem;color:var(--text-muted)">${message}</div></div>`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; toast.style.transition = "opacity .4s"; setTimeout(() => toast.remove(), 400); }, 4500);
}

function getShop() {
  return new URLSearchParams(window.location.search).get("shop") || "";
}

async function loadAnalytics() {
  try {
    const shop = getShop();
    const url = shop ? `/api/analytics?shop=${encodeURIComponent(shop)}` : "/api/analytics";
    const res = await fetch(url);
    if (!res.ok) return;
    const d = await res.json();
    const todayEl = document.getElementById("stat-today-revenue");
    const totalEl = document.getElementById("stat-total-revenue");
    const todayOrdEl = document.getElementById("stat-today-orders");
    const unpaidEl = document.getElementById("stat-unpaid-hint");
    if (todayEl) todayEl.innerText = `₹${d.today_revenue.toFixed(2)}`;
    if (totalEl) totalEl.innerText = `₹${d.total_revenue.toFixed(2)}`;
    if (todayOrdEl) todayOrdEl.innerText = `${d.today_orders} orders today`;
    if (unpaidEl) unpaidEl.innerText = `${d.unpaid_count} unpaid orders`;
  } catch (err) { console.error("Analytics load error:", err); }
}

async function loadOrders() {
  try {
    const shop = getShop();
    const fetchUrl = shop ? `/api/orders?shop=${encodeURIComponent(shop)}` : "/api/orders";
    const res = await fetch(fetchUrl);
    if (!res.ok) {
      if (res.status === 401 || res.status === 303) { window.location.href = "/login"; return; }
      throw new Error("Failed to load orders");
    }
    const data = await res.json();
    currentOrders = data.orders || [];
    renderOrders();
    loadAnalytics();
  } catch (err) { console.error(err); }
}

function renderOrders() {
  const tbody = document.getElementById("orders-tbody");
  if (!tbody) return;
  let pendingCount = 0, completedCount = 0;

  if (currentOrders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:3rem">No print orders yet. Customer files uploaded via QR code will appear here instantly!</td></tr>`;
    document.getElementById("stat-pending").innerText = "0";
    document.getElementById("stat-completed").innerText = "0";
    document.getElementById("order-count-badge").innerText = "0 New";
    return;
  }

  tbody.innerHTML = currentOrders.map((order) => {
    if (order.status === "pending") pendingCount++;
    if (order.status === "completed") completedCount++;

    const dateStr = new Date(order.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const badgeClass = order.status === "completed" ? "badge-completed" : order.status === "printing" ? "badge-printing" : order.status === "failed" ? "badge-failed" : "badge-pending";
    const sizeKb = (order.file_size_bytes / 1024).toFixed(1);
    const amount = (order.total_amount || 0).toFixed(2);
    const isPaid = order.payment_status === "paid";

    const payBadge = isPaid
      ? `<span class="pay-badge-paid" style="cursor:pointer;" onclick="openPaymentModal('${order.order_id}')" title="Click to view payment receipt">✅ PAID</span><div style="font-size:.72rem;color:var(--text-muted);margin-top:2px">${(order.payment_method || "cash").toUpperCase()}${order.payment_ref ? ` (${escapeHtml(order.payment_ref)})` : ''}</div>`
      : `<span class="pay-badge-unpaid" style="cursor:pointer;" onclick="openPaymentModal('${order.order_id}')" title="Click to open UPI QR code or mark paid">⏳ Unpaid</span>`;

    const markPaidBtn = isPaid
      ? ""
      : `<div style="display:flex;gap:4px;margin-top:4px">
           <button class="btn btn-secondary btn-sm" style="padding:.2rem .45rem;font-size:.72rem;border-color:rgba(16,185,129,.5);color:#10b981;" onclick="openPaymentModal('${order.order_id}')" title="Open Dynamic UPI QR Code">🪙 UPI QR</button>
           <button class="btn btn-secondary btn-sm" style="padding:.2rem .45rem;font-size:.72rem;" onclick="markPaid('${order.order_id}')" title="Fast cash payment">💵 Cash</button>
         </div>`;

    return `
      <tr id="row-${order.order_id}">
        <td><code style="font-weight:700">${order.order_id}</code></td>
        <td>
          <div style="font-weight:600">${escapeHtml(order.customer_name)}</div>
          ${order.phone ? `<div style="font-size:.8rem;color:var(--text-muted)">📞 ${escapeHtml(order.phone)}</div>` : ""}
        </td>
        <td>
          <div style="display:flex;align-items:center;gap:.5rem">
            <span style="cursor:pointer" onclick="openPreviewModal('${order.order_id}')">📄</span>
            <a href="javascript:void(0)" onclick="openPreviewModal('${order.order_id}')" style="color:var(--accent);text-decoration:none;font-weight:600" title="Click to preview document">${escapeHtml(order.filename)}</a>
            <span style="font-size:.75rem;color:var(--text-muted)">(${sizeKb} KB)</span>
          </div>
        </td>
        <td>
          <span style="font-weight:600">${order.copies}x</span>
          <span style="font-size:.75rem;color:var(--text-muted);text-transform:uppercase">(${order.color_mode})</span>
          ${order.page_range ? `<div style="font-size:.72rem;color:#a78bfa;font-weight:600;margin-top:2px;">📄 pgs: ${escapeHtml(order.page_range)}</div>` : ""}
        </td>
        <td class="amount-cell">
          <div style="display:flex;align-items:center;gap:.25rem">
            <span style="font-weight:700;color:var(--text-muted);font-size:.9rem">₹</span>
            <input type="number" step="1" min="0" value="${amount}" 
                   class="amount-input" id="amount-input-${order.order_id}"
                   onchange="updateOrderAmount('${order.order_id}', this.value)"
                   onkeydown="if(event.key==='Enter')this.blur()"
                   title="Click to edit live price">
          </div>
          <div style="font-size:.72rem;color:var(--text-muted);margin-top:3px">${order.page_count || 1} pg${(order.page_count || 1) > 1 ? 's' : ''} × ${order.copies || 1}x</div>
        </td>
        <td>${payBadge}${markPaidBtn}</td>
        <td>
          <span class="badge ${badgeClass}">${order.status}</span>
          ${order.printer_used ? `<div style="font-size:.7rem;color:var(--text-muted);margin-top:.2rem">${order.printer_used}</div>` : ""}
        </td>
        <td style="font-size:.85rem;color:var(--text-muted)">${dateStr}</td>
        <td style="text-align:right">
          <div style="display:inline-flex;flex-direction:column;gap:.35rem">
            <button class="btn btn-secondary btn-sm" style="padding:.25rem .6rem;font-size:.8rem" onclick="openPreviewModal('${order.order_id}')">👁️ Preview</button>
            <button class="btn btn-success btn-sm" style="padding:.25rem .6rem;font-size:.8rem" onclick="printOrder('${order.order_id}', { pageRange: '${escapeHtml(order.page_range || '')}' })" ${order.status === "printing" ? "disabled" : ""}>🖨️ Print Now</button>
            <button class="btn btn-danger btn-sm" style="padding:.2rem .5rem;font-size:.75rem;opacity:.8" onclick="deleteOrder('${order.order_id}')">🗑️ Delete</button>
          </div>
        </td>
      </tr>`;
  }).join("");

  document.getElementById("stat-pending").innerText = pendingCount;
  document.getElementById("stat-completed").innerText = completedCount;
  document.getElementById("order-count-badge").innerText = `${pendingCount} Pending`;
}

async function updateOrderAmount(orderId, newAmount) {
  const val = parseFloat(newAmount);
  if (isNaN(val) || val < 0) {
    showToast("Invalid Amount ⚠️", "Please enter a valid positive price.", false);
    return;
  }
  try {
    const fd = new FormData();
    fd.append("amount", val);
    const res = await fetch(`/api/orders/${orderId}/amount`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to update price");

    showToast("Price Updated 💵", `Order ${orderId} amount set to ₹${val.toFixed(2)}`, true);
    const ord = currentOrders.find((o) => o.order_id === orderId);
    if (ord) ord.total_amount = val;
    loadAnalytics();
  } catch (err) {
    console.error("Failed to update order amount", err);
    showToast("Update Failed ❌", err.message, false);
  }
}

async function markPaid(orderId) {
  const order = currentOrders.find((o) => o.order_id === orderId);
  const defaultAmount = order && order.total_amount ? order.total_amount : "";
  const amountStr = prompt(`Enter amount charged to customer in ₹:`, defaultAmount);
  if (amountStr === null) return;
  const amount = parseFloat(amountStr) || 0;

  const method = prompt("Payment method — type  cash  or  upi:", "cash");
  if (!method) return;
  const ref = method.trim().toLowerCase() === "upi" ? (prompt("UPI Reference / Transaction ID (optional):") || "") : "";
  try {
    const fd = new FormData();
    fd.append("payment_method", method.trim().toLowerCase());
    fd.append("payment_ref", ref);
    if (!isNaN(amount) && amount >= 0) fd.append("amount", amount);
    const res = await fetch(`/api/orders/${orderId}/pay`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    playChime();
    showToast("Payment Recorded 💵", `Order ${orderId} marked paid (₹${(data.total_amount || 0).toFixed(2)}) via ${method}`, true);
    await loadOrders();
  } catch (err) { showToast("Payment Failed", err.message, false); }
}

async function printOrder(orderId, options = {}) {
  const printer = options.printer || document.getElementById("global-printer-select").value;
  const copies = options.copies || null;
  const pageRange = options.pageRange || "";
  const row = document.getElementById(`row-${orderId}`);
  if (row) { const btn = row.querySelector(".btn-success"); if (btn) { btn.innerText = "⏳ Printing..."; btn.disabled = true; } }
  try {
    const fd = new FormData();
    fd.append("printer_name", printer);
    if (copies) fd.append("copies", copies);
    if (pageRange) fd.append("page_range", pageRange);
    const res = await fetch(`/api/orders/${orderId}/print`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    showToast("Print Submitted!", data.message, true);
    await loadOrders();
  } catch (err) { showToast("Print Failed", err.message, false); await loadOrders(); }
}

async function deleteOrder(orderId) {
  if (!confirm(`Delete order ${orderId}?`)) return;
  try {
    if ((await fetch(`/api/orders/${orderId}`, { method: "DELETE" })).ok) { showToast("Order Deleted", `Order ${orderId} removed`, true); await loadOrders(); }
  } catch (err) { console.error(err); }
}

function openQrModal() {
  const m = document.getElementById("qr-modal");
  if (m) m.classList.add("active");
}

function closeQrModal() {
  const m = document.getElementById("qr-modal");
  if (m) m.classList.remove("active");
}

let activePreviewOrderId = null;

function openPreviewModal(orderId) {
  const order = currentOrders.find((o) => o.order_id === orderId);
  if (!order) return;
  activePreviewOrderId = orderId;

  const modal = document.getElementById("preview-modal");
  const filenameEl = document.getElementById("preview-filename");
  const chipsContainer = document.getElementById("preview-chips-container");
  const bodyEl = document.getElementById("preview-body");
  const downloadLink = document.getElementById("preview-download-link");
  const printBtn = document.getElementById("preview-modal-print-btn");
  const pageRangeInput = document.getElementById("preview-page-range");
  const copiesInput = document.getElementById("preview-copies");
  const printerSelect = document.getElementById("preview-printer-select");

  if (!modal || !bodyEl) return;

  if (filenameEl) filenameEl.innerText = order.filename;
  if (downloadLink) {
    downloadLink.href = `/api/files/${order.order_id}`;
    downloadLink.setAttribute("download", order.filename);
  }

  if (printBtn) {
    printBtn.disabled = order.status === "printing";
    printBtn.innerText = order.status === "printing" ? "⏳ Printing..." : "🖨️ Print Now";
  }

  // Pre-fill print options bar
  if (pageRangeInput) pageRangeInput.value = order.page_range || "";
  if (copiesInput) {
    copiesInput.value = order.copies || 1;
    copiesInput.oninput = () => {
      const fb = document.getElementById("fallback-copies-val");
      if (fb) fb.innerText = copiesInput.value || 1;
    };
  }
  if (printerSelect && document.getElementById("global-printer-select")) {
    printerSelect.value = document.getElementById("global-printer-select").value;
  }

  const isPaid = order.payment_status === "paid";
  if (chipsContainer) {
    chipsContainer.innerHTML = `
      <span class="preview-chip">Customer: <strong>${escapeHtml(order.customer_name)}</strong></span>
      ${order.phone ? `<span class="preview-chip">📞 ${escapeHtml(order.phone)}</span>` : ""}
      <span class="preview-chip preview-chip-accent"><strong>${order.copies}x</strong> Copies (${escapeHtml(order.color_mode.toUpperCase())})</span>
      ${order.page_range ? `<span class="preview-chip" style="border-color:#8b5cf6;color:#a78bfa">Pages: <strong>${escapeHtml(order.page_range)}</strong></span>` : ""}
      <span class="preview-chip">Amount: <strong>₹${(order.total_amount || 0).toFixed(2)}</strong></span>
      <span class="preview-chip ${isPaid ? "preview-chip-success" : ""}" style="cursor:pointer;" onclick="openPaymentModal('${order.order_id}')" title="Click to view/collect UPI or Cash payment">Payment: <strong>${isPaid ? "PAID (" + (order.payment_method || "cash").toUpperCase() + ")" : "UNPAID 🪙"}</strong></span>
      <span class="preview-chip">Status: <strong>${escapeHtml(order.status.toUpperCase())}</strong></span>
    `;
  }

  // Render preview based on extension
  const ext = (order.filename.split(".").pop() || "").toLowerCase();
  const fileUrl = `/api/files/${order.order_id}`;

  if (ext === "pdf") {
    bodyEl.innerHTML = `<iframe src="${fileUrl}" title="${escapeHtml(order.filename)}"></iframe>`;
  } else if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "svg"].includes(ext)) {
    bodyEl.innerHTML = `<img src="${fileUrl}" alt="${escapeHtml(order.filename)}">`;
  } else if (["txt", "log", "csv", "json"].includes(ext)) {
    bodyEl.innerHTML = `<iframe src="${fileUrl}" style="background:#0f172a;color:#f8fafc;padding:1rem;font-family:monospace" title="${escapeHtml(order.filename)}"></iframe>`;
  } else {
    const fileIcons = {
      doc: "📘",
      docx: "📘",
      xls: "📗",
      xlsx: "📗",
      ppt: "📙",
      pptx: "📙",
    };
    const icon = fileIcons[ext] || "📄";
    bodyEl.innerHTML = `
      <div class="preview-fallback-card">
        <span class="preview-fallback-icon">${icon}</span>
        <h4>${escapeHtml(order.filename)}</h4>
        <p>This is a <strong>${ext.toUpperCase()}</strong> document. Office documents are automatically formatted and printed directly by the local print engine.</p>
        
        <div class="preview-fallback-quick-options" style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 10px; padding: 0.85rem 1.15rem; margin: 1.25rem auto; max-width: 380px; text-align: left;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; font-size: 0.85rem;">
            <span style="color: var(--text-muted); display: flex; align-items: center; gap: 0.35rem;">📑 Copies:</span>
            <div style="display: flex; gap: 0.4rem; align-items: center;">
              <button type="button" class="btn btn-secondary" style="padding: 2px 9px; font-size: 0.85rem; line-height: 1;" onclick="adjustFallbackCopies(-1)">−</button>
              <strong id="fallback-copies-val" style="min-width: 28px; text-align: center; color: var(--accent); font-size: 1rem;">${order.copies || 1}</strong>
              <button type="button" class="btn btn-secondary" style="padding: 2px 9px; font-size: 0.85rem; line-height: 1;" onclick="adjustFallbackCopies(1)">+</button>
            </div>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
            <span style="color: var(--text-muted);">Color Mode:</span>
            <span class="preview-chip preview-chip-accent" style="margin: 0; padding: 2px 8px; font-size: 0.75rem;">${escapeHtml((order.color_mode || "bw").toUpperCase())}</span>
          </div>
          ${order.page_range ? `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.6rem; font-size: 0.85rem;">
            <span style="color: var(--text-muted);">Pages:</span>
            <span style="font-family: monospace; color: #a78bfa; font-weight: 600;">${escapeHtml(order.page_range)}</span>
          </div>` : ""}
        </div>

        <div style="display: flex; gap: 0.75rem; justify-content: center; align-items: center; flex-wrap: wrap; margin-top: 1rem;">
          <button type="button" id="fallback-print-btn" class="btn btn-success" style="padding: 0.6rem 1.4rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.4rem; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);" onclick="printFromPreview()">
            🖨️ Print Now
          </button>
          <a href="${fileUrl}" target="_blank" class="btn btn-secondary" style="padding: 0.6rem 1.2rem; display: inline-flex; align-items: center; gap: 0.4rem;">
            ⬇️ Open / Download
          </a>
        </div>
      </div>
    `;
  }

  modal.classList.add("active");
}

function adjustFallbackCopies(delta) {
  const copiesInput = document.getElementById("preview-copies");
  const fallbackVal = document.getElementById("fallback-copies-val");
  let current = copiesInput ? parseInt(copiesInput.value, 10) || 1 : 1;
  current = Math.max(1, Math.min(99, current + delta));
  if (copiesInput) copiesInput.value = current;
  if (fallbackVal) fallbackVal.innerText = current;
}

function closePreviewModal() {
  const modal = document.getElementById("preview-modal");
  if (modal) {
    modal.classList.remove("active");
    const bodyEl = document.getElementById("preview-body");
    if (bodyEl) bodyEl.innerHTML = "";
  }
  activePreviewOrderId = null;
}

function handlePreviewBackdropClick(e) {
  if (e.target && e.target.id === "preview-modal") {
    closePreviewModal();
  }
}

async function printFromPreview() {
  if (!activePreviewOrderId) return;
  const orderId = activePreviewOrderId;
  const printBtn = document.getElementById("preview-modal-print-btn");
  const fallbackBtn = document.getElementById("fallback-print-btn");
  const pageRangeInput = document.getElementById("preview-page-range");
  const copiesInput = document.getElementById("preview-copies");
  const printerSelect = document.getElementById("preview-printer-select");

  const pageRange = pageRangeInput ? pageRangeInput.value.trim() : "";
  const copies = copiesInput ? parseInt(copiesInput.value, 10) || 1 : 1;
  const printer = printerSelect ? printerSelect.value : "";

  if (printBtn) {
    printBtn.disabled = true;
    printBtn.innerText = "⏳ Printing...";
  }
  if (fallbackBtn) {
    fallbackBtn.disabled = true;
    fallbackBtn.innerText = "⏳ Printing...";
  }
  await printOrder(orderId, { printer, copies, pageRange });
  closePreviewModal();
}

let activePaymentOrderId = null;

async function openPaymentModal(orderId) {
  const order = currentOrders.find((o) => o.order_id === orderId);
  if (!order) return;
  activePaymentOrderId = orderId;

  const modal = document.getElementById("payment-modal");
  document.getElementById("pay-modal-customer").innerText = `${order.customer_name} (${order.filename})`;
  document.getElementById("pay-modal-order-id").innerText = order.order_id;
  document.getElementById("pay-modal-amount-input").value = (order.total_amount || 0).toFixed(2);
  document.getElementById("pay-modal-ref").value = order.payment_ref || "";

  refreshModalUpiQr();

  try {
    const res = await fetch(`/api/orders/${orderId}/payment`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById("pay-modal-vpa").innerText = `UPI: ${data.vpa}`;
    }
  } catch (e) {}

  if (modal) modal.classList.add("active");
}

function refreshModalUpiQr() {
  if (!activePaymentOrderId) return;
  const qrImg = document.getElementById("pay-modal-qr-img");
  if (qrImg) {
    qrImg.src = `/api/orders/${activePaymentOrderId}/upi-qr.png?_t=${Date.now()}`;
  }
}

function closePaymentModal() {
  const modal = document.getElementById("payment-modal");
  if (modal) modal.classList.remove("active");
  activePaymentOrderId = null;
}

function handlePaymentBackdropClick(e) {
  if (e.target && e.target.id === "payment-modal") {
    closePaymentModal();
  }
}

async function confirmPaymentInModal(method = "upi") {
  if (!activePaymentOrderId) return;
  const orderId = activePaymentOrderId;
  const amountInput = document.getElementById("pay-modal-amount-input");
  const refInput = document.getElementById("pay-modal-ref");
  const amount = parseFloat(amountInput.value) || 0;
  const ref = refInput ? refInput.value.trim() : "";

  try {
    const fd = new FormData();
    fd.append("payment_method", method);
    fd.append("payment_ref", ref);
    if (!isNaN(amount) && amount >= 0) fd.append("amount", amount);
    const res = await fetch(`/api/orders/${orderId}/pay`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");

    playChime();
    showToast("Payment Recorded 💵", `Order ${orderId} marked paid (₹${(data.total_amount || 0).toFixed(2)}) via ${method.toUpperCase()}`, true);
    closePaymentModal();
    await loadOrders();
  } catch (err) {
    showToast("Payment Failed ❌", err.message, false);
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closePreviewModal();
    closeQrModal();
    closePaymentModal();
  }
});

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function setupSSE() {
  const evtSource = new EventSource("/api/events");
  evtSource.onmessage = function (e) {
    try {
      const payload = JSON.parse(e.data);
      if (payload.event === "new_order") {
        playChime();
        showToast("New Customer Upload! 📄", `${payload.data.customer_name} uploaded '${payload.data.filename}' (${payload.data.copies} copies)`);
        loadOrders();
      } else if (payload.event === "order_updated" || payload.event === "order_deleted") { loadOrders(); }
    } catch (err) { console.error("SSE parse error", err); }
  };
  evtSource.onerror = function () { console.warn("SSE interrupted. Reconnecting..."); setTimeout(setupSSE, 3000); };
}

async function triggerQuickTestPrint() {
  const shop = getShop() || "counter-1";
  showToast("Testing Printer 🖨️", "Sending hardware test page...", true);
  try {
    const res = await fetch(`/api/agent/test-print?shop=${encodeURIComponent(shop)}`, { method: "POST" });
    const data = await res.json();
    if (res.ok && data.success) { playChime(); showToast("Success! ✅", data.message || "Test page printed!", true); }
    else { showToast("Print Failed ⚠️", data.detail || "Could not print test page.", false); }
  } catch (err) { showToast("Error ❌", err.message, false); }
}

document.addEventListener("DOMContentLoaded", () => { loadOrders(); setupSSE(); });
