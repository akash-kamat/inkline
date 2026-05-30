#!/usr/bin/env python3
"""
Wembley Mini Thermal Printer — Bluetooth LE
pip install bleak Pillow
"""

import asyncio
from bleak import BleakClient, BleakScanner
from PIL import Image, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────────
ADDRESS    = "16:3B:5B:3B:37:D5"
PRINT_CHAR = "0000ae01-0000-1000-8000-00805f9b34fb"
WIDTH_PX   = 384
WIDTH_BYTES = 48

# Best fonts to try in order (script auto-picks first available)
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",      # Windows Arial Bold
    "C:/Windows/Fonts/arial.ttf",        # Windows Arial
    "C:/Windows/Fonts/calibrib.ttf",     # Windows Calibri Bold
    "C:/Windows/Fonts/verdana.ttf",      # Windows Verdana
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",   # Linux
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",    # Linux fallback
]

def get_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    print("⚠️  No TTF font found, using tiny default. Install Pillow fonts for better results.")
    return ImageFont.load_default()

# ── Protocol ──────────────────────────────────────────────────────────────────
def packet(cmd, data):
    n = len(data)
    chk = sum(data) & 0xff
    return bytes([0x51, 0x78, cmd, 0x00, n & 0xff, n >> 8]) + data + bytes([chk, 0xff])

CMD_STATUS   = packet(0xa3, b'\x00')
CMD_VERSION  = packet(0xa8, b'\x00')
CMD_SPEED    = packet(0xaf, bytes([0x52, 0x1c]))
CMD_PAPER    = packet(0xbe, b'\x00')
CMD_START    = packet(0xa1, bytes([0x30, 0x00]))
CMD_END      = packet(0xa3, b'\x00')

def cmd_darkness(level=0x40):  return packet(0xa4, bytes([level]))
def cmd_feed(lines=40):        return packet(0xbd, bytes([lines]))
def cmd_row(row48):            return packet(0xa2, row48)

# ── BLE send ──────────────────────────────────────────────────────────────────
async def send(client, data, chunk=100):
    for i in range(0, len(data), chunk):
        await client.write_gatt_char(PRINT_CHAR, data[i:i+chunk], response=False)
        await asyncio.sleep(0.02)

# ── Rendering ─────────────────────────────────────────────────────────────────
def render_text(text, font_size=40, align="left"):
    """Render text to list of 48-byte bitmap rows."""
    font = get_font(font_size)

    # Measure height needed
    probe = Image.new("L", (WIDTH_PX, 1), 255)
    bbox  = ImageDraw.Draw(probe).multiline_textbbox((4, 4), text, font=font, spacing=6)
    h = max(bbox[3] + 20, 60)

    img  = Image.new("L", (WIDTH_PX, h), 255)
    draw = ImageDraw.Draw(img)
    draw.multiline_text((4, 4), text, font=font, fill=0, spacing=6, align=align)
    return image_to_rows(img)

def render_image(path):
    """Load any image and convert to printer rows."""
    img = Image.open(path).convert("L")
    w, h = img.size
    new_h = int(h * WIDTH_PX / w)
    img = img.resize((WIDTH_PX, new_h), Image.LANCZOS)
    return image_to_rows(img)

def image_to_rows(img):
    rows = []
    for y in range(img.height):
        row = bytearray(WIDTH_BYTES)
        for x in range(WIDTH_PX):
            if img.getpixel((x, y)) < 128:
                row[x // 8] |= (0x80 >> (x % 8))
        rows.append(bytes(row))
    return rows

# ── Print engine ──────────────────────────────────────────────────────────────
async def _print(rows, darkness=0x40):
    print(f"🔗 Connecting to {ADDRESS}...")
    async with BleakClient(ADDRESS, timeout=15) as client:
        print(f"✅ Connected — sending {len(rows)} rows")
        await send(client, CMD_STATUS);    await asyncio.sleep(0.3)
        await send(client, CMD_VERSION);   await asyncio.sleep(0.3)
        await send(client, cmd_darkness(darkness))
        await send(client, CMD_SPEED)
        await send(client, CMD_PAPER)
        await send(client, CMD_START)
        await asyncio.sleep(0.1)
        for i, row in enumerate(rows):
            await send(client, cmd_row(row))
            if i % 40 == 39:
                await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)
        await send(client, cmd_feed(40))
        await send(client, CMD_END)
        print("✅ Done!")

# ── Public API ────────────────────────────────────────────────────────────────
def print_text(text, font_size=40, darkness=0x40, align="left"):
    """Print text. font_size in pixels. darkness 0x00–0x7f."""
    rows = render_text(text, font_size=font_size, align=align)
    ink_rows = sum(1 for r in rows if any(b for b in r))
    print(f"🖨️  Rendered: {len(rows)} rows, {ink_rows} have ink")
    asyncio.run(_print(rows, darkness=darkness))

def print_image(path, darkness=0x50):
    """Print an image file (PNG, JPG, etc.)."""
    rows = render_image(path)
    print(f"🖨️  Image: {len(rows)} rows")
    asyncio.run(_print(rows, darkness=darkness))

def feed(lines=40):
    """Feed blank paper."""
    async def _feed():
        async with BleakClient(ADDRESS, timeout=15) as client:
            await send(client, cmd_feed(lines))
    asyncio.run(_feed())
    print(f"✅ Fed {lines} lines")

def scan():
    """Scan for nearby BLE devices."""
    async def _scan():
        print("🔍 Scanning...")
        devs = await BleakScanner.discover(timeout=8, return_adv=True)
        for dev, adv in sorted(devs.values(), key=lambda x: x[1].rssi or -999, reverse=True):
            name = dev.name or adv.local_name or "Unknown"
            print(f"  {dev.address}  {name:<28}  {adv.rssi} dBm")
    asyncio.run(_scan())

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # ── Print text ────────────────────────────────────────────────────────────
    print_text(
        "Hello from\nmy laptop!\n\n2025-05-30\n\nIt works!",
        font_size=48,
        darkness=0x40,
    )

    # ── Print centred receipt ─────────────────────────────────────────────────
    # print_text(
    #     "MY SHOP\n"
    #     "────────────────\n"
    #     "Coffee      £2.50\n"
    #     "Croissant   £1.80\n"
    #     "────────────────\n"
    #     "TOTAL       £4.30\n"
    #     "\nThank you!",
    #     font_size=32,
    #     darkness=0x40,
    # )

    # ── Print an image ────────────────────────────────────────────────────────
    # print_image("photo.jpg", darkness=0x55)

    # ── Feed paper ────────────────────────────────────────────────────────────
    # feed(30)
