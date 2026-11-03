"""LX-D02 / LX-D2 (FunnyPrint) thermal printer driver over BLE.

Protocol follows cicloid/printable docs/PROTOCOL.md:
  hello (5A 01) -> MAC, host-side challenge/response auth (5A 0A / 5A 0B),
  density (5A 0C), print start (5A 04 .. 00 00), raster (55 <idx> <96B> 00),
  printer finish (5A 06), print end (5A 04 .. 01 00).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from PIL import Image

WIDTH = 384
ROW_BYTES = WIDTH // 8

WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

INTER_PACKET_DELAY = 0.015
COOLDOWN = 0.1
HELLO_TIMEOUT = 4.0
NOTIFICATION_TIMEOUT = 10.0
STALL_TIMEOUT = 60.0


class PrinterError(Exception):
    pass


# --- packets -----------------------------------------------------------------

def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def auth_response(challenge: bytes, mac: bytes) -> bytes:
    return bytes(crc16_xmodem(bytes([c]) + mac) >> 8 for c in challenge)


def pkt_hello() -> bytes:
    return bytes([0x5A, 0x01]) + bytes(10)


def pkt_challenge(challenge: bytes) -> bytes:
    return bytes([0x5A, 0x0A]) + challenge


def pkt_auth(response: bytes) -> bytes:
    return bytes([0x5A, 0x0B]) + response


def pkt_density(level: int) -> bytes:
    return bytes([0x5A, 0x0C, level])


def pkt_print(count: int, end: bool) -> bytes:
    return bytes([0x5A, 0x04, count >> 8, count & 0xFF, 1 if end else 0, 0])


def pkt_raster(index: int, payload: bytes) -> bytes:
    return bytes([0x55, index >> 8, index & 0xFF]) + payload + b"\x00"


def image_to_packets(img: Image.Image) -> list[bytes]:
    """1-bit image (384 wide) -> list of 96-byte payloads, two rows each."""
    if img.width != WIDTH:
        raise ValueError(f"image width must be {WIDTH}, got {img.width}")
    # PIL mode "1": 0 = black. Printer: 1 = burn. Invert, then pack MSB-first.
    mono = img.convert("1")
    raw = bytes(b ^ 0xFF for b in mono.tobytes())
    if mono.height % 2:
        raw += bytes(ROW_BYTES)
    chunk = ROW_BYTES * 2
    return [raw[i:i + chunk] for i in range(0, len(raw), chunk)]


# --- notifications -----------------------------------------------------------

@dataclass
class Status:
    battery: int
    paper_out: bool
    charging: bool
    overheat: bool


def parse_notification(data: bytes):
    """Returns (opcode, value) or None."""
    if len(data) < 2 or data[0] != 0x5A:
        return None
    op = data[1]
    if op == 0x01 and len(data) >= 10:
        return op, bytes(data[4:10])
    if op == 0x02 and len(data) >= 5:
        return op, Status(
            battery=data[2],
            paper_out=data[3] != 0,
            charging=data[4] == 1,
            overheat=len(data) > 5 and data[5] != 0,
        )
    if op in (0x05, 0x06) and len(data) >= 4:
        return op, (data[2] << 8) | data[3]
    if op in (0x07, 0x08, 0x0A):
        return op, None
    if op == 0x0B and len(data) >= 3:
        return op, data[2] == 0x01
    return None


# --- transport ---------------------------------------------------------------

async def find_printer(address: str | None = None, timeout: float = 10.0):
    if address:
        dev = await BleakScanner.find_device_by_address(address, timeout=timeout)
    else:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.name or ad.local_name or "").startswith("LX"),
            timeout=timeout,
        )
    if dev is None:
        raise PrinterError("LX プリンタが見つかりません。電源とBluetoothを確認してください。")
    return dev


class LXD02:
    def __init__(self, client: BleakClient, log=print):
        self.client = client
        self.queue: asyncio.Queue = asyncio.Queue()
        self.status: Status | None = None
        self.log = log

    def _on_notify(self, _char, data: bytearray):
        parsed = parse_notification(bytes(data))
        if parsed is None:
            return
        op, value = parsed
        if op == 0x02:
            self.status = value
        self.queue.put_nowait(parsed)

    async def start(self):
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)

    async def _send(self, data: bytes):
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)

    async def _wait_for(self, opcode: int, timeout: float):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PrinterError(f"プリンタからの応答 (5A {opcode:02X}) がタイムアウトしました")
            try:
                op, value = await asyncio.wait_for(self.queue.get(), remaining)
            except asyncio.TimeoutError:
                continue
            if op == opcode:
                return value

    def _check_paper(self):
        if self.status and self.status.paper_out:
            raise PrinterError("用紙切れです")

    async def print_image(self, img: Image.Image, density: int = 3):
        payloads = image_to_packets(img)
        count = len(payloads)
        if count > 0xFFFF:
            raise PrinterError("画像が長すぎます")

        await self._send(pkt_hello())
        mac = await self._wait_for(0x01, HELLO_TIMEOUT)
        self.log(f"接続OK (MAC {mac.hex(':')})")

        challenge = os.urandom(10)
        await self._send(pkt_challenge(challenge))
        await self._wait_for(0x0A, NOTIFICATION_TIMEOUT)
        await self._send(pkt_auth(auth_response(challenge, mac)))
        if not await self._wait_for(0x0B, NOTIFICATION_TIMEOUT):
            raise PrinterError("認証に失敗しました")
        self._check_paper()
        if self.status:
            self.log(f"バッテリー {self.status.battery}%")

        await self._send(pkt_density(density))
        await self._send(pkt_print(count, end=False))

        idx = 0
        holding = False
        finished = False
        last_progress = time.monotonic()
        while not finished:
            # Drain flow-control notifications.
            while not self.queue.empty():
                op, value = self.queue.get_nowait()
                if op == 0x02:
                    self._check_paper()
                elif op == 0x05:
                    idx = max(value - 1, 0)
                    holding = False
                elif op == 0x06:
                    finished = True
                elif op == 0x07:
                    await asyncio.sleep(COOLDOWN)
                elif op == 0x08:
                    holding = True
            if finished:
                break

            now = time.monotonic()
            if now - last_progress > STALL_TIMEOUT:
                raise PrinterError("印刷が停止しました")

            if holding or idx >= count:
                try:
                    item = await asyncio.wait_for(self.queue.get(), NOTIFICATION_TIMEOUT)
                except asyncio.TimeoutError:
                    raise PrinterError("印刷完了の通知がタイムアウトしました")
                self.queue.put_nowait(item)
                continue

            await self._send(pkt_raster(idx, payloads[idx]))
            idx += 1
            last_progress = time.monotonic()
            if idx < count:
                await asyncio.sleep(INTER_PACKET_DELAY)

        await self._send(pkt_print(count, end=True))
        # Leave a moment for the final write to flush before disconnect.
        await asyncio.sleep(0.2)


async def print_image(img: Image.Image, density: int = 3, address: str | None = None, log=print):
    log("プリンタを探しています…")
    dev = await find_printer(address)
    log(f"{dev.name} ({dev.address}) に接続中…")
    async with BleakClient(dev, timeout=15.0) as client:
        printer = LXD02(client, log=log)
        await printer.start()
        await printer.print_image(img, density=density)
    log("印刷完了")
