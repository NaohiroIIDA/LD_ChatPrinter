import { LXD02, PrinterError } from "./lxd02.js";
import { characterFromImage, loadFonts, render } from "./render.js";

const FEED = 40;
const $ = (id) => document.getElementById(id);

const printer = new LXD02();
let characters = []; // [{key, label, mouthY, img}]
let selection = "random"; // "random" | character key | "custom"
let randomKey = null; // the character currently standing in for "random"
let custom = null; // canvas from a user image
let busy = false;

// --- tiny persistence for per-viewer conveniences ----------------------------

const store = {
  get(k) {
    try { return localStorage.getItem(k); } catch { return null; }
  },
  set(k, v) {
    try { localStorage.setItem(k, v); } catch {}
  },
};

// --- UI helpers ---------------------------------------------------------------

let toastTimer;
function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = isError ? "show error" : "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), isError ? 5000 : 2500);
}

function updateStatus() {
  const btn = $("connect");
  btn.classList.toggle("on", printer.connected);
  if (!printer.connected) {
    $("status").textContent = "プリンタに接続";
    return;
  }
  const s = printer.status;
  const battery = s ? ` · 電池 ${s.battery}%${s.charging ? "（充電中）" : ""}` : "";
  $("status").textContent = `${printer.device.name}${battery}`;
}

function setBusy(b) {
  busy = b;
  $("print").disabled = b;
  $("connect").disabled = b;
}

function setProgress(fraction) {
  const bar = $("progress");
  bar.classList.toggle("on", fraction !== null);
  bar.firstElementChild.style.width = `${Math.round((fraction ?? 0) * 100)}%`;
}

// --- characters ---------------------------------------------------------------

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

async function loadCharacters() {
  const list = await (await fetch("characters/characters.json")).json();
  characters = await Promise.all(
    list.map(async (c) => ({ ...c, img: await loadImage(`characters/${c.key}.png`) })),
  );
}

function rollRandom() {
  const others = characters.filter((c) => c.key !== randomKey);
  randomKey = others[Math.floor(Math.random() * others.length)].key;
}

function currentCharacter() {
  if (selection === "custom" && custom) return { img: custom, mouthY: 82 };
  const key = selection === "random" ? randomKey : selection;
  return characters.find((c) => c.key === key);
}

function buildPicker() {
  const box = $("chars");
  const tiles = [
    { key: "random", label: "おまかせ", icon: "🎲" },
    ...characters.map((c) => ({ key: c.key, label: c.label, src: c.img.src })),
    { key: "custom", label: "画像…", icon: "🖼️" },
  ];
  for (const t of tiles) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.key = t.key;
    b.title = t.label;
    b.innerHTML = t.src ? `<img alt="" src="${t.src}">` : `<div class="icon" aria-hidden="true">${t.icon}</div>`;
    const span = document.createElement("span");
    span.textContent = t.label;
    b.append(span);
    b.addEventListener("click", () => select(t.key));
    box.append(b);
  }
}

function select(key) {
  if (key === "custom") {
    $("file").click();
    return;
  }
  selection = key;
  store.set("character", key);
  refreshPicker();
  updatePreview();
}

function refreshPicker() {
  for (const b of $("chars").children) b.setAttribute("aria-pressed", String(b.dataset.key === selection));
  $("reroll").hidden = selection !== "random";
}

$("file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const url = URL.createObjectURL(file);
    custom = characterFromImage(await loadImage(url));
    URL.revokeObjectURL(url);
    selection = "custom";
    refreshPicker();
    updatePreview();
  } catch {
    toast("画像を読み込めませんでした", true);
  }
  e.target.value = "";
});

// --- rendering ----------------------------------------------------------------

function renderReceipt(feed) {
  const c = currentCharacter();
  return render({
    username: $("user").value,
    message: $("message").value,
    character: c?.img,
    mouthY: c?.mouthY,
    fontSize: Number($("fontsize").value),
    feed,
  });
}

function updatePreview() {
  if (!characters.length) return;
  const src = renderReceipt(0);
  const dst = $("preview");
  dst.width = src.width;
  dst.height = src.height;
  dst.getContext("2d").drawImage(src, 0, 0);
}

// --- printer ------------------------------------------------------------------

printer.onstatus = updateStatus;
printer.ondisconnect = () => {
  updateStatus();
  if (!busy) toast("プリンタとの接続が切れました", true);
};

async function connect() {
  $("status").textContent = "接続中…";
  try {
    const name = await printer.connect();
    toast(`${name} に接続しました`);
  } catch (e) {
    if (e.name !== "NotFoundError") toast(e.message || String(e), true); // NotFoundError = chooser cancelled
  }
  updateStatus();
}

async function doPrint() {
  if (busy) return;
  if (!$("message").value.trim()) {
    toast("メッセージを入力してください", true);
    $("message").focus();
    return;
  }
  setBusy(true);
  try {
    if (!printer.connected) await connect();
    if (!printer.connected) return;
    const canvas = renderReceipt(FEED);
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
    $("print").textContent = "印刷中…";
    setProgress(0);
    await printer.print(data, {
      density: Number($("density").value),
      onprogress: (sent, total) => setProgress(sent / total),
    });
    toast("印刷しました");
    if (selection === "random") {
      rollRandom();
      updatePreview();
    }
  } catch (e) {
    toast(e instanceof PrinterError ? e.message : `エラー: ${e.message || e}`, true);
  } finally {
    $("print").textContent = "印刷する";
    setProgress(null);
    setBusy(false);
    updateStatus();
  }
}

// --- wiring -------------------------------------------------------------------

async function init() {
  if (!navigator.bluetooth) $("banner").style.display = "block";

  $("user").value = store.get("user") ?? "";
  const density = store.get("density");
  if (density) $("density").value = density;
  $("density-out").textContent = $("density").value;

  await Promise.all([loadFonts(), loadCharacters()]);
  rollRandom();
  buildPicker();
  const saved = store.get("character");
  if (saved && characters.some((c) => c.key === saved)) selection = saved;
  refreshPicker();
  updatePreview();

  for (const id of ["user", "message", "fontsize"]) $(id).addEventListener("input", updatePreview);
  $("user").addEventListener("change", () => store.set("user", $("user").value));
  $("density").addEventListener("input", () => {
    $("density-out").textContent = $("density").value;
    store.set("density", $("density").value);
  });
  $("reroll").addEventListener("click", () => {
    rollRandom();
    updatePreview();
  });
  $("connect").addEventListener("click", () => {
    if (printer.connected) printer.disconnect();
    else connect();
  });
  $("print").addEventListener("click", doPrint);
  $("message").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) doPrint();
  });
}

init().catch((e) => toast(`初期化に失敗しました: ${e.message || e}`, true));
