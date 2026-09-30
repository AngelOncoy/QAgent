// HU-01 — Abrir un proyecto desde una carpeta local.
// Toda la lógica vive en Python (window.pywebview.api); aquí solo se pinta la UI.
"use strict";

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview.api;

let pendingPath = null; // carpeta mostrada en el modal
let busy = false;

// ---------- utilidades ----------
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function toast(msg, bad = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("bad", bad);
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 3200);
}

function plural(n, uno, varios) {
  return `${n} ${n === 1 ? uno : varios}`;
}

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(diff) || diff < 60) return "hace un momento";
  if (diff < 3600) return `hace ${plural(Math.floor(diff / 60), "minuto", "minutos")}`;
  if (diff < 86400) return `hace ${plural(Math.floor(diff / 3600), "hora", "horas")}`;
  return `hace ${plural(Math.floor(diff / 86400), "día", "días")}`;
}

function initials(name) {
  const parts = name.split(/[^A-Za-z0-9ÁÉÍÓÚáéíóúÑñ]+/).filter(Boolean);
  const text = parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return text.toUpperCase();
}

async function guarded(fn) {
  if (busy) return;
  busy = true;
  try {
    await fn();
  } catch (err) {
    console.error(err);
    toast("Ocurrió un error inesperado.", true);
  } finally {
    busy = false;
  }
}

// ---------- navegación ----------
function showWelcome() {
  $("s-preview").classList.add("hide");
  $("s-welcome").classList.remove("hide");
  loadRecent();
}

function showPreview(p) {
  $("pvChip").textContent = p.nombre;
  $("pvName").textContent = p.nombre;
  $("pvPath").textContent = p.ruta;
  $("pvCount").textContent = plural(p.py_count, "archivo .py", "archivos .py");
  const req = $("pvReq");
  req.textContent = `requirements.txt ${p.has_requirements ? "✓" : "✗"}`;
  req.className = `pill ${p.has_requirements ? "p-green" : "p-grey"}`;
  $("s-welcome").classList.add("hide");
  $("s-preview").classList.remove("hide");
  if (p.aviso) toast(p.aviso, true);
}

// ---------- recientes ----------
async function loadRecent() {
  renderRecent(await api().list_recent());
}

function renderRecent(items) {
  const list = $("recentList");
  list.replaceChildren();
  if (!items.length) {
    list.append(el("div", "empty", "Aún no has abierto proyectos"));
    return;
  }
  for (const p of items) {
    const row = el("div", "proj");
    const av = el("div", "av", initials(p.nombre));
    av.style.background = "var(--blue-s)";
    const info = el("div");
    info.style.minWidth = "0";
    const title = el("div", "", p.nombre + " ");
    title.style.fontWeight = "600";
    title.append(el("span", "pill p-blue", "Local"));
    info.append(title, el("div", "pth", p.ruta));
    const meta = el("div", "meta");
    meta.append(`Abierto ${timeAgo(p.ultimo_uso)}`, el("br"), plural(p.py_count, "archivo .py", "archivos .py"));
    row.append(av, info, meta);
    row.addEventListener("click", () => guarded(() => openRecent(p, info)));
    list.append(row);
  }
}

async function openRecent(p, infoNode) {
  const res = await api().open_project(p.ruta);
  if (res.ok) {
    showPreview(res);
    return;
  }
  infoNode.querySelector(".warn")?.remove();
  const warn = el("div", "warn");
  warn.append(el("span", "errmsg", res.error));
  const btn = el("button", "btn", "Quitar de recientes");
  btn.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    renderRecent(await api().remove_recent(p.ruta));
    toast("Proyecto quitado de recientes");
  });
  warn.append(btn);
  infoNode.append(warn);
}

// ---------- abrir proyecto ----------
function closeModal() {
  $("m-open").classList.remove("show");
  pendingPath = null;
}

async function pickFolder() {
  const res = await api().pick_folder();
  if (res.cancelado) return;
  await showFolder(res.ruta);
}

async function showFolder(ruta) {
  const res = await api().inspect_folder(ruta);
  pendingPath = res.ruta || ruta;
  $("mPath").textContent = pendingPath;
  $("mCount").textContent = res.py_count === undefined ? "—" : String(res.py_count);
  const error = $("mError");
  error.textContent = res.error || "";
  error.classList.toggle("hide", !res.error);
  $("btnConfirm").disabled = !res.ok;
  $("m-open").classList.add("show");
}

async function confirmOpen() {
  if (!pendingPath) return;
  const res = await api().open_project(pendingPath);
  if (!res.ok) {
    await showFolder(pendingPath); // la carpeta cambió desde que se inspeccionó
    return;
  }
  closeModal();
  showPreview(res);
}

// ---------- eventos ----------
$("btnOpen").addEventListener("click", () => guarded(pickFolder));
$("btnOtra").addEventListener("click", () => guarded(pickFolder));
$("btnConfirm").addEventListener("click", () => guarded(confirmOpen));
$("btnBack").addEventListener("click", showWelcome);
$("navHome").addEventListener("click", showWelcome);
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

if (window.pywebview && window.pywebview.api) {
  loadRecent();
} else {
  window.addEventListener("pywebviewready", loadRecent);
}
