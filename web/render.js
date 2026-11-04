// "Character speaking in a speech bubble" receipt image on a canvas (384 px, black/white).
// Same layout as render.py.

import { WIDTH } from "./lxd02.js";

export const CHAR_W = 120;
export const CHAR_H = 160;
const MARGIN = 6;
const BORDER = 3;
const PAD = 12;
const TAIL_W = 16;
const NAME_H = 30;

const FONT_FAMILY = `"Zen Maru Gothic", "Hiragino Maru Gothic ProN", "Hiragino Sans", sans-serif`;
export const DEFAULT_USER = "ナナシさん";

// Characters that must not start a line (simple kinsoku).
const NO_LINE_START = new Set("、。，．・：；？！ー～…‥）」』】〕〉》’”ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ!?.,:;)]}");

export async function loadFonts() {
  await Promise.all([
    document.fonts.load(`500 24px ${FONT_FAMILY}`, "あ"),
    document.fonts.load(`700 20px ${FONT_FAMILY}`, "あ"),
  ]).catch(() => {});
}

function wrapText(ctx, text, maxWidth) {
  const lines = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const ch of para) {
      if (line && ctx.measureText(line + ch).width > maxWidth && !NO_LINE_START.has(ch)) {
        lines.push(line);
        line = ch === " " ? "" : ch;
      } else {
        line += ch;
      }
    }
    lines.push(line);
  }
  return lines;
}

function bubblePath(ctx, x, y, w, h, tailY, inset) {
  const x0 = x + TAIL_W + inset;
  const r = 16 - inset;
  const right = x + w - inset;
  const bottom = y + h - inset;
  const top = y + inset;
  const ty = y + tailY;
  ctx.beginPath();
  ctx.moveTo(x0 + r, top);
  ctx.arcTo(right, top, right, bottom, r);
  ctx.arcTo(right, bottom, x0, bottom, r);
  ctx.arcTo(x0, bottom, x0, top, r);
  ctx.lineTo(x0, ty + 6 - inset);
  ctx.lineTo(x + inset * 2.4, ty);
  ctx.lineTo(x0, ty - 10 + inset);
  ctx.arcTo(x0, top, right, top, r);
  ctx.closePath();
}

const pad2 = (n) => String(n).padStart(2, "0");

/**
 * Draw the receipt. character: an image/canvas of CHAR_W x CHAR_H; mouthY: where the tail points.
 * Returns a canvas WIDTH wide, thresholded to pure black and white, with `feed` blank rows at the end.
 */
export function render({ username, message, character, mouthY = 82, fontSize = 24, feed = 0, date = new Date() }) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const fMsg = `500 ${fontSize}px ${FONT_FAMILY}`;
  const fName = `700 20px ${FONT_FAMILY}`;
  const fSmall = `500 16px ${FONT_FAMILY}`;

  const bubbleX = MARGIN + CHAR_W;
  let bubbleW = WIDTH - MARGIN - bubbleX;
  const textW = bubbleW - TAIL_W - BORDER * 2 - PAD * 2;
  ctx.font = fMsg;
  const lines = wrapText(ctx, message.replace(/\\n/g, "\n"), textW);
  const longest = Math.max(...lines.map((l) => Math.ceil(ctx.measureText(l).width)));
  bubbleW = Math.max(Math.min(bubbleW, longest + TAIL_W + BORDER * 2 + PAD * 2 + 2), 120);
  const lineH = Math.round(fontSize * 1.5);
  const bubbleH = Math.max(lines.length * lineH + PAD * 2 + BORDER * 2, 64);

  const nameTop = MARGIN + 2;
  const bubbleTop = nameTop + NAME_H + 6;
  const tailY = Math.min(36, Math.floor(bubbleH / 2));
  const charTop = Math.max(MARGIN, bubbleTop + tailY - mouthY);
  const bodyBottom = Math.max(bubbleTop + bubbleH, charTop + CHAR_H);
  const footerTop = bodyBottom + 10;
  const contentH = footerTop + 30;

  canvas.width = WIDTH;
  canvas.height = contentH + feed;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (character) ctx.drawImage(character, MARGIN, charTop, CHAR_W, CHAR_H);

  // name tag (white on black) above the bubble
  ctx.font = fName;
  let name = username.trim() || DEFAULT_USER;
  const nameX = bubbleX + TAIL_W;
  const maxNameW = WIDTH - MARGIN - nameX - 20;
  while (ctx.measureText(name).width > maxNameW && name.length > 1) name = name.slice(0, -2) + "…";
  const nw = Math.ceil(ctx.measureText(name).width);
  ctx.fillStyle = "#000";
  ctx.beginPath();
  ctx.roundRect(nameX, nameTop, nw + 20, NAME_H, NAME_H / 2);
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.textBaseline = "middle";
  ctx.fillText(name, nameX + 10, nameTop + NAME_H / 2 + 1);

  // bubble: black outer shape, white inner shape
  ctx.fillStyle = "#000";
  bubblePath(ctx, bubbleX, bubbleTop, bubbleW, bubbleH, tailY, 0);
  ctx.fill();
  ctx.fillStyle = "#fff";
  bubblePath(ctx, bubbleX, bubbleTop, bubbleW, bubbleH, tailY, BORDER);
  ctx.fill();

  ctx.font = fMsg;
  ctx.fillStyle = "#000";
  ctx.textBaseline = "middle";
  const tx = bubbleX + TAIL_W + BORDER + PAD;
  const ty = bubbleTop + BORDER + PAD;
  lines.forEach((line, i) => ctx.fillText(line, tx, ty + i * lineH + lineH / 2));

  // footer: dashed rule + timestamp
  for (let x = MARGIN; x < WIDTH - MARGIN; x += 10) ctx.fillRect(x, footerTop - 1, 6, 2);
  ctx.font = fSmall;
  ctx.textAlign = "right";
  ctx.textBaseline = "top";
  const ts = `${date.getFullYear()}/${pad2(date.getMonth() + 1)}/${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  ctx.fillText(ts, WIDTH - MARGIN, footerTop + 8);
  ctx.textAlign = "left";

  threshold(ctx, canvas.width, canvas.height);
  return canvas;
}

function threshold(ctx, w, h) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114 >= 128 ? 255 : 0;
    d[i] = d[i + 1] = d[i + 2] = v;
    d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}

/** A user photo -> CHAR_W x CHAR_H canvas, fitted bottom-centre and Floyd-Steinberg dithered. */
export function characterFromImage(img) {
  const c = document.createElement("canvas");
  c.width = CHAR_W;
  c.height = CHAR_H;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, CHAR_W, CHAR_H);
  const k = Math.min(CHAR_W / img.width, CHAR_H / img.height);
  const w = img.width * k;
  const h = img.height * k;
  ctx.drawImage(img, (CHAR_W - w) / 2, CHAR_H - h, w, h);

  const data = ctx.getImageData(0, 0, CHAR_W, CHAR_H);
  const d = data.data;
  const g = new Float32Array(CHAR_W * CHAR_H);
  for (let i = 0; i < g.length; i++) g[i] = d[i * 4] * 0.299 + d[i * 4 + 1] * 0.587 + d[i * 4 + 2] * 0.114;
  for (let y = 0; y < CHAR_H; y++) {
    for (let x = 0; x < CHAR_W; x++) {
      const i = y * CHAR_W + x;
      const v = g[i] >= 128 ? 255 : 0;
      const err = g[i] - v;
      g[i] = v;
      if (x + 1 < CHAR_W) g[i + 1] += (err * 7) / 16;
      if (y + 1 < CHAR_H) {
        if (x > 0) g[i + CHAR_W - 1] += (err * 3) / 16;
        g[i + CHAR_W] += (err * 5) / 16;
        if (x + 1 < CHAR_W) g[i + CHAR_W + 1] += err / 16;
      }
    }
  }
  for (let i = 0; i < g.length; i++) {
    d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = g[i];
    d[i * 4 + 3] = 255;
  }
  ctx.putImageData(data, 0, 0);
  return c;
}
