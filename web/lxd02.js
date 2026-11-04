// LX-D02 / LX-D2 (FunnyPrint) driver over Web Bluetooth.
// Port of lxd02.py; protocol per cicloid/printable docs/PROTOCOL.md.

export const WIDTH = 384;
const ROW_BYTES = WIDTH / 8;

const SERVICE = 0xffe6;
const WRITE = 0xffe1;
const NOTIFY = 0xffe2;

const INTER_PACKET_DELAY = 15;
const COOLDOWN = 100;
const HELLO_TIMEOUT = 4000;
const NOTIFICATION_TIMEOUT = 10000;
const STALL_TIMEOUT = 60000;

export class PrinterError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- packets -----------------------------------------------------------------

export function crc16xmodem(data) {
  let crc = 0;
  for (const b of data) {
    crc ^= b << 8;
    for (let i = 0; i < 8; i++) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc;
}

export function authResponse(challenge, mac) {
  return Uint8Array.from(challenge, (c) => crc16xmodem([c, ...mac]) >> 8);
}

const pktHello = () => Uint8Array.of(0x5a, 0x01, ...new Uint8Array(10));
const pktChallenge = (c) => Uint8Array.of(0x5a, 0x0a, ...c);
const pktAuth = (r) => Uint8Array.of(0x5a, 0x0b, ...r);
const pktDensity = (level) => Uint8Array.of(0x5a, 0x0c, level);
const pktPrint = (count, end) => Uint8Array.of(0x5a, 0x04, count >> 8, count & 0xff, end ? 1 : 0, 0);

function pktRaster(index, payload) {
  const p = new Uint8Array(100);
  p[0] = 0x55;
  p[1] = index >> 8;
  p[2] = index & 0xff;
  p.set(payload, 3);
  return p;
}

/** Canvas ImageData (384 wide, already black/white) -> 96-byte payloads, two rows each. */
export function imageToPayloads(imageData) {
  const { width, height, data } = imageData;
  if (width !== WIDTH) throw new Error(`image width must be ${WIDTH}`);
  const rows = height + (height % 2);
  const raw = new Uint8Array(rows * ROW_BYTES);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < WIDTH; x++) {
      if (data[(y * WIDTH + x) * 4] < 128) raw[y * ROW_BYTES + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  const out = [];
  for (let i = 0; i < raw.length; i += ROW_BYTES * 2) out.push(raw.subarray(i, i + ROW_BYTES * 2));
  return out;
}

// --- notifications -----------------------------------------------------------

function parseNotification(d) {
  if (d.length < 2 || d[0] !== 0x5a) return null;
  const op = d[1];
  if (op === 0x01 && d.length >= 10) return { op, value: d.slice(4, 10) };
  if (op === 0x02 && d.length >= 5) {
    return {
      op,
      value: { battery: d[2], paperOut: d[3] !== 0, charging: d[4] === 1, overheat: d.length > 5 && d[5] !== 0 },
    };
  }
  if ((op === 0x05 || op === 0x06) && d.length >= 4) return { op, value: (d[2] << 8) | d[3] };
  if (op === 0x07 || op === 0x08 || op === 0x0a) return { op, value: null };
  if (op === 0x0b && d.length >= 3) return { op, value: d[2] === 0x01 };
  return null;
}

// --- transport ---------------------------------------------------------------

export class LXD02 {
  constructor() {
    this.device = null;
    this.writeChar = null;
    this.status = null;
    this.queue = [];
    this.waiter = null;
    this.onstatus = () => {};
    this.ondisconnect = () => {};
  }

  get connected() {
    return !!this.device?.gatt.connected;
  }

  async connect() {
    if (!navigator.bluetooth) throw new PrinterError("このブラウザは Web Bluetooth に対応していません（Chrome / Edge を使ってください）");
    this.device = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: "LX" }],
      optionalServices: [SERVICE],
    });
    this.device.addEventListener("gattserverdisconnected", () => this.ondisconnect());
    const server = await this.device.gatt.connect();
    const svc = await server.getPrimaryService(SERVICE);
    this.writeChar = await svc.getCharacteristic(WRITE);
    const notify = await svc.getCharacteristic(NOTIFY);
    notify.addEventListener("characteristicvaluechanged", (e) => this._onNotify(e));
    await notify.startNotifications();

    // GATT may be answered from cache while the printer is off: only the hello reply proves it's there.
    this.queue = [];
    await this._send(pktHello());
    try {
      await this._waitFor(0x01, HELLO_TIMEOUT);
    } catch {
      this.disconnect();
      throw new PrinterError(`${this.device.name} が応答しません。電源が入っているか確認してください`);
    }
    return this.device.name;
  }

  disconnect() {
    if (this.device?.gatt.connected) this.device.gatt.disconnect();
  }

  _onNotify(e) {
    const v = e.target.value;
    const parsed = parseNotification(new Uint8Array(v.buffer, v.byteOffset, v.byteLength));
    if (!parsed) return;
    if (parsed.op === 0x02) {
      this.status = parsed.value;
      this.onstatus(parsed.value);
    }
    this.queue.push(parsed);
    if (this.waiter) {
      this.waiter();
      this.waiter = null;
    }
  }

  async _send(bytes) {
    if (this.writeChar.writeValueWithoutResponse) await this.writeChar.writeValueWithoutResponse(bytes);
    else await this.writeChar.writeValue(bytes);
  }

  /** Next notification, or null on timeout. */
  async _next(timeout) {
    if (this.queue.length) return this.queue.shift();
    let timer;
    await Promise.race([
      new Promise((r) => (this.waiter = r)),
      new Promise((r) => (timer = setTimeout(r, timeout))),
    ]);
    clearTimeout(timer);
    this.waiter = null;
    return this.queue.shift() ?? null;
  }

  async _waitFor(opcode, timeout) {
    const deadline = performance.now() + timeout;
    for (;;) {
      const remaining = deadline - performance.now();
      if (remaining <= 0) throw new PrinterError(`プリンタからの応答 (5A ${opcode.toString(16).padStart(2, "0")}) がタイムアウトしました`);
      const n = await this._next(remaining);
      if (n && n.op === opcode) return n.value;
    }
  }

  _checkPaper() {
    if (this.status?.paperOut) throw new PrinterError("用紙切れです");
  }

  /** imageData: 384-wide black/white canvas ImageData. onprogress(sent, total). */
  async print(imageData, { density = 3, onprogress = () => {} } = {}) {
    const payloads = imageToPayloads(imageData);
    const count = payloads.length;
    if (count > 0xffff) throw new PrinterError("画像が長すぎます");

    this.queue = [];
    await this._send(pktHello());
    const mac = await this._waitFor(0x01, HELLO_TIMEOUT);

    const challenge = crypto.getRandomValues(new Uint8Array(10));
    await this._send(pktChallenge(challenge));
    await this._waitFor(0x0a, NOTIFICATION_TIMEOUT);
    await this._send(pktAuth(authResponse(challenge, mac)));
    if (!(await this._waitFor(0x0b, NOTIFICATION_TIMEOUT))) throw new PrinterError("認証に失敗しました");
    this._checkPaper();

    await this._send(pktDensity(density));
    await this._send(pktPrint(count, false));

    let idx = 0;
    let holding = false;
    let finished = false;
    let lastProgress = performance.now();
    while (!finished) {
      // Drain flow-control notifications.
      while (this.queue.length) {
        const { op, value } = this.queue.shift();
        if (op === 0x02) this._checkPaper();
        else if (op === 0x05) {
          idx = Math.max(value - 1, 0); // the printer wants a rewind to n-1
          holding = false;
        } else if (op === 0x06) finished = true;
        else if (op === 0x07) await sleep(COOLDOWN);
        else if (op === 0x08) holding = true;
      }
      if (finished) break;
      if (performance.now() - lastProgress > STALL_TIMEOUT) throw new PrinterError("印刷が停止しました");

      if (holding || idx >= count) {
        const n = await this._next(NOTIFICATION_TIMEOUT);
        if (!n) throw new PrinterError("印刷完了の通知がタイムアウトしました");
        this.queue.unshift(n);
        continue;
      }

      await this._send(pktRaster(idx, payloads[idx]));
      idx++;
      lastProgress = performance.now();
      onprogress(idx, count);
      if (idx < count) await sleep(INTER_PACKET_DELAY);
    }

    await this._send(pktPrint(count, true));
    await sleep(200);
  }
}
