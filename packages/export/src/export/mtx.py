"""Embedded .pptx fonts (EOT, MicroType Express compressed) -> plain TrueType.

PowerPoint and Google Slides embed a deck's fonts as `ppt/fonts/*.fntdata`:
Embedded OpenType (EOT) files whose font data is MicroType Express (MTX)
compressed. Neither LibreOffice (its libeot has no MTX support) nor a browser
can read that, so the deck renders in a substitute font — usually wider, so
titles wrap and overlap the template's artwork. This decodes them back to TTF.

Ported from the reference decoder in the W3C MTX submission
(https://www.w3.org/Submission/MTX/): LZCOMP (LZ77 + three adaptive Huffman
trees) unpacks three blocks, then Compact Table Format (CTF) is turned back
into TrueType — `glyf` rebuilt from triplet-encoded points with its push data
and instructions re-joined, `loca` recreated, `cvt ` un-deltaed. The device
metric tables `hdmx`/`VDMX` are dropped rather than decoded: they are optional
hints for bitmap sizes that no renderer we feed needs.
"""

from __future__ import annotations

import io
import struct

from fontTools.ttLib.sfnt import SFNTWriter

_TTEMBED_TTCOMPRESSED = 0x4
_TTEMBED_XORENCRYPTDATA = 0x10000000


class FontDecodeError(ValueError):
    """Not a font we can decode (malformed EOT/MTX, or an unknown variant)."""


def eot_to_ttf(eot: bytes) -> bytes:
    """The TrueType font inside an EOT file, decompressing MTX if needed."""
    if len(eot) < 16:
        raise FontDecodeError("too short for an EOT header")
    eot_size, data_size, _version, flags = struct.unpack_from("<IIII", eot)
    if eot_size > len(eot) or data_size > eot_size:
        raise FontDecodeError("EOT sizes don't match the file")
    data = eot[eot_size - data_size : eot_size]
    if flags & _TTEMBED_XORENCRYPTDATA:
        data = bytes(b ^ 0x50 for b in data)
    if flags & _TTEMBED_TTCOMPRESSED:
        return mtx_to_ttf(data)
    return data


# --- LZCOMP ---------------------------------------------------------------


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.index = 0
        self.count = 0
        self.buffer = 0

    def bit(self) -> int:
        if self.count == 0:
            if self.index >= len(self.data):
                raise FontDecodeError("LZCOMP stream ended early")
            self.buffer = self.data[self.index]
            self.index += 1
            self.count = 8
        self.count -= 1
        return (self.buffer >> self.count) & 1

    def value(self, bits: int) -> int:
        v = 0
        for _ in range(bits):
            v = (v << 1) | self.bit()
        return v


class _AdaptiveHuffman:
    """AHUFF from the reference code: nodes 1..2*range-1, root 1, leaves range..2*range-1."""

    def __init__(self, bits: _BitReader, symbol_range: int) -> None:
        self.bits = bits
        n = 2 * symbol_range
        self.up = [0] * n
        self.left = [0] * n
        self.right = [0] * n
        self.code = [-1] * n
        self.weight = [0] * n
        self.index = [0] * symbol_range
        for i in range(2, n):
            self.up[i] = i // 2
            self.weight[i] = 1
        for i in range(1, symbol_range):
            self.left[i] = 2 * i
            self.right[i] = 2 * i + 1
        for i in range(symbol_range):
            self.code[symbol_range + i] = i
            self.left[symbol_range + i] = self.right[symbol_range + i] = -1
            self.index[i] = symbol_range + i
        self._init_weight(1)

        bit_count2 = 0
        if 256 < symbol_range < 512:
            bit_count2 = (symbol_range - 256 - 1).bit_length() + 1
        if bit_count2:
            self._update(self.index[256])
            self._update(self.index[257])
            for _ in range(12):
                self._update(self.index[symbol_range - 3])  # DUP2
            for _ in range(6):
                self._update(self.index[symbol_range - 2])  # DUP4
        else:
            for _ in range(2):
                for i in range(symbol_range):
                    self._update(self.index[i])

    def _init_weight(self, root: int) -> None:
        # Post-order sum of children, iteratively (the tree is ~1000 nodes deep at most).
        stack = [(root, False)]
        while stack:
            a, done = stack.pop()
            if self.code[a] >= 0:
                continue
            if done:
                self.weight[a] = self.weight[self.left[a]] + self.weight[self.right[a]]
            else:
                stack += [(a, True), (self.left[a], False), (self.right[a], False)]

    def _swap(self, a: int, b: int) -> None:
        upa, upb = self.up[a], self.up[b]
        for arr in (self.left, self.right, self.code, self.weight):
            arr[a], arr[b] = arr[b], arr[a]
        self.up[a], self.up[b] = upa, upb
        for node in (a, b):
            code = self.code[node]
            if code < 0:
                self.up[self.left[node]] = node
                self.up[self.right[node]] = node
            else:
                self.index[code] = node

    def _update(self, a: int) -> None:
        weight = self.weight
        while a != 1:
            wa = weight[a]
            b = a - 1
            if weight[b] == wa:
                while weight[b] == wa:
                    b -= 1
                b += 1
                if b > 1:
                    self._swap(a, b)
                    a = b
            weight[a] = wa + 1
            a = self.up[a]
        weight[a] += 1

    def read(self) -> int:
        a = 1
        while True:
            a = self.right[a] if self.bits.bit() else self.left[a]
            symbol = self.code[a]
            if symbol >= 0:
                break
        self._update(a)  # may move the leaf, so the symbol is read first
        return symbol


_PRELOAD_SIZE = 2 * 32 * 96 + 4 * 256
_MAX_2BYTE_DIST = 512


def _preload() -> bytearray:
    buf = bytearray()
    for k in range(32):
        for j in range(96):
            buf += bytes((k, j))
    j = 0
    while len(buf) < _PRELOAD_SIZE and j < 256:
        buf += bytes((j, j, j, j))
        j += 1
    return buf


def lzcomp_decompress(data: bytes) -> bytes:
    bits = _BitReader(data)
    run_length = bits.bit()
    dist_coder = _AdaptiveHuffman(bits, 8)
    len_coder = _AdaptiveHuffman(bits, 8)
    out_len = bits.value(24)
    dist_ranges = 1
    while 1 + (1 << (3 * dist_ranges)) - 1 < out_len:
        dist_ranges += 1
    dup2 = 256 + 8 * dist_ranges
    sym_coder = _AdaptiveHuffman(bits, dup2 + 3)

    window = _preload()
    base = len(window)
    while len(window) - base < out_len:
        symbol = sym_coder.read()
        if symbol < 256:
            window.append(symbol)
        elif symbol == dup2:
            window.append(window[-2])
        elif symbol == dup2 + 1:
            window.append(window[-4])
        elif symbol == dup2 + 2:
            window.append(window[-6])
        else:
            # Length: 3-bit chunks, top bit = "more follows", 2 payload bits each.
            chunk = symbol - 256
            n_dist = chunk // 8 + 1
            chunk %= 8
            length = 0
            while True:
                length = (length << 2) | (chunk & 3)
                if not chunk & 4:
                    break
                chunk = len_coder.read()
            length += 2
            distance = 0
            for _ in range(n_dist):
                distance = (distance << 3) | dist_coder.read()
            distance += 1
            if distance >= _MAX_2BYTE_DIST:
                length += 1
            start = len(window) - distance - length + 1
            for j in range(length):
                window.append(window[start + j])
    raw = bytes(window[base : base + out_len])
    return _undo_run_length(raw) if run_length else raw


def _undo_run_length(data: bytes) -> bytes:
    if not data:
        return data
    escape = data[0]
    out = bytearray()
    i = 1
    while i < len(data):
        b = data[i]
        i += 1
        if b != escape:
            out.append(b)
            continue
        count = data[i]
        i += 1
        if count == 0:
            out.append(escape)
        else:
            out += bytes([data[i]]) * count
            i += 1
    return bytes(out)


# --- CTF -> TrueType --------------------------------------------------------


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def u8(self) -> int:
        if self.pos >= len(self.data):
            raise FontDecodeError("CTF stream ended early")
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from(">H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def i16(self) -> int:
        v = struct.unpack_from(">h", self.data, self.pos)[0]
        self.pos += 2
        return v

    def take(self, n: int) -> bytes:
        v = self.data[self.pos : self.pos + n]
        if len(v) != n:
            raise FontDecodeError("CTF stream ended early")
        self.pos += n
        return v

    def u255(self) -> int:
        code = self.u8()
        if code == 253:
            return self.u16()
        if code == 255:
            return self.u8() + 253
        if code == 254:
            return self.u8() + 506
        return code

    def s255(self) -> int:
        code = self.u8()
        if code == 253:
            return self.i16()
        sign = 1
        if code == 250:
            sign = -1
            code = self.u8()
        if code == 255:
            value = self.u8() + 250
        elif code == 254:
            value = self.u8() + 500
        else:
            value = code
        return sign * value


def _triplets() -> list[tuple[int, int, int, int, int, int, int]]:
    """(byte count, x bits, y bits, dx base, dy base, x sign, y sign) per flag index."""
    table = []
    for i in range(10):  # dy only
        table.append((2, 0, 8, 0, (i // 2) * 256, 0, -1 if i % 2 == 0 else 1))
    for i in range(10):  # dx only
        table.append((2, 8, 0, (i // 2) * 256, 0, -1 if i % 2 == 0 else 1, 0))
    signs = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    for dx in (1, 17, 33, 49):
        for dy in (1, 17, 33, 49):
            for sx, sy in signs:
                table.append((2, 4, 4, dx, dy, sx, sy))
    for dx in (1, 257, 513):
        for dy in (1, 257, 513):
            for sx, sy in signs:
                table.append((3, 8, 8, dx, dy, sx, sy))
    for sx, sy in signs:
        table.append((4, 12, 12, 0, 0, sx, sy))
    for sx, sy in signs:
        table.append((5, 16, 16, 0, 0, sx, sy))
    return table


_TRIPLETS = _triplets()


def _push_instructions(values: list[int]) -> bytes:
    """TrueType PUSH instructions for `values` (the CTF stores just the values)."""
    out = bytearray()
    i = 0
    while i < len(values):
        # Longest run that fits in bytes, else in words, capped at 255 per NPUSH.
        j = i
        byte_run = all(0 <= v <= 255 for v in values[i : i + 1])
        while j < len(values) and j - i < 255 and (0 <= values[j] <= 255) == byte_run:
            j += 1
        run = values[i:j]
        if byte_run:
            out += bytes([0x40, len(run)]) + bytes(run)  # NPUSHB
        else:
            out += bytes([0x41, len(run)]) + b"".join(struct.pack(">h", v) for v in run)  # NPUSHW
        i = j
    return bytes(out)


def _read_push_data(push: _Reader, count: int) -> list[int]:
    values: list[int] = []
    while len(values) < count:
        code = push.data[push.pos]
        if code == 251:  # Hop3
            push.pos += 1
            a = values[-2]
            values += [a, push.s255(), a]
        elif code == 252:  # Hop4
            push.pos += 1
            a = values[-2]
            x2 = push.s255()
            x3 = push.s255()
            values += [a, x2, a, x3, a]
        else:
            values.append(push.s255())
    return values[:count]


def _instructions(glyf: _Reader, push: _Reader, code: _Reader) -> bytes:
    push_count = glyf.u255()
    code_size = glyf.u255()
    values = _read_push_data(push, push_count)
    return _push_instructions(values) + code.take(code_size)


def _glyph(glyf: _Reader, push: _Reader, code: _Reader) -> bytes:
    num_contours = glyf.i16()
    if num_contours == 0:
        return b""
    if num_contours == -1:  # composite
        bbox = struct.unpack(">hhhh", glyf.take(8))
        start = glyf.pos
        has_instructions = False
        while True:
            flags = glyf.u16()
            glyf.u16()  # glyph index
            glyf.take(4 if flags & 0x1 else 2)
            if flags & 0x8:
                glyf.take(2)
            elif flags & 0x40:
                glyf.take(4)
            elif flags & 0x80:
                glyf.take(8)
            has_instructions |= bool(flags & 0x100)
            if not flags & 0x20:
                break
        components = glyf.data[start : glyf.pos]
        out = struct.pack(">hhhhh", -1, *bbox) + components
        if has_instructions:
            instructions = _instructions(glyf, push, code)
            out += struct.pack(">H", len(instructions)) + instructions
        return out

    bbox = None
    if num_contours == 0x7FFF:
        num_contours = glyf.i16()
        bbox = struct.unpack(">hhhh", glyf.take(8))
    # First contour's end point, then each later contour's point count.
    end_points = [glyf.u255()]
    for _ in range(num_contours - 1):
        end_points.append(end_points[-1] + glyf.u255())
    total = end_points[-1]
    num_points = total + 1
    flags = glyf.take(num_points)
    xs, ys, on_curve = [], [], []
    x = y = 0
    for flag in flags:
        count, xbits, ybits, dx0, dy0, sx, sy = _TRIPLETS[flag & 0x7F]
        n = count - 1
        data = int.from_bytes(glyf.take(n), "big")
        dx = (data >> (n * 8 - xbits)) & ((1 << xbits) - 1) if xbits else 0
        dy = (data >> (n * 8 - xbits - ybits)) & ((1 << ybits) - 1) if ybits else 0
        x += sx * (dx + dx0) if sx else dx + dx0
        y += sy * (dy + dy0) if sy else dy + dy0
        xs.append(x)
        ys.append(y)
        on_curve.append(not flag & 0x80)
    instructions = _instructions(glyf, push, code)
    if bbox is None:
        bbox = (min(xs), min(ys), max(xs), max(ys))

    out = bytearray(struct.pack(">hhhhh", num_contours, *bbox))
    out += struct.pack(f">{num_contours}H", *end_points)
    out += struct.pack(">H", len(instructions)) + instructions
    # Plain encoding: one flag per point, every coordinate a signed word delta.
    out += bytes(1 if on else 0 for on in on_curve)
    px = py = 0
    for v in xs:
        out += struct.pack(">h", v - px)
        px = v
    for v in ys:
        out += struct.pack(">h", v - py)
        py = v
    return bytes(out)


def _decode_cvt(data: bytes) -> bytes:
    r = _Reader(data)
    count = r.u16()
    out = bytearray()
    last = 0
    for _ in range(count):
        c = r.u8()
        if c < 238:
            delta = c
        elif c == 238:
            delta = r.i16()
        elif c >= 248:
            delta = r.u8() + 238 * (c - 247)
        else:  # 239..247
            delta = -(r.u8() + 238 * (c - 239))
        last = (last + delta) & 0xFFFF
        out += struct.pack(">H", last)
    return bytes(out)


def mtx_to_ttf(mtx: bytes) -> bytes:
    if len(mtx) < 10 or mtx[0] != 3:
        raise FontDecodeError("not a MicroType Express 1.0 stream")
    offset2 = int.from_bytes(mtx[4:7], "big")
    offset3 = int.from_bytes(mtx[7:10], "big")
    if not 10 <= offset2 <= offset3 <= len(mtx):
        raise FontDecodeError("bad MTX block offsets")
    ctf = lzcomp_decompress(mtx[10:offset2])
    push = _Reader(lzcomp_decompress(mtx[offset2:offset3]))
    code = _Reader(lzcomp_decompress(mtx[offset3:]))

    num_tables = struct.unpack_from(">H", ctf, 4)[0]
    tables: dict[str, bytes] = {}
    for i in range(num_tables):
        tag, _checksum, offset, length = struct.unpack_from(">4sIII", ctf, 12 + 16 * i)
        tables[tag.decode("latin-1")] = ctf[offset : offset + length]

    num_glyphs = struct.unpack_from(">H", tables["maxp"], 4)[0]
    glyf_in = _Reader(tables["glyf"])
    glyf_out = bytearray()
    offsets = [0]
    for _ in range(num_glyphs):
        glyf_out += _glyph(glyf_in, push, code)
        glyf_out += b"\0" * (-len(glyf_out) % 4)
        offsets.append(len(glyf_out))

    tables["glyf"] = bytes(glyf_out)
    tables["loca"] = struct.pack(f">{len(offsets)}I", *offsets)
    head = bytearray(tables["head"])
    struct.pack_into(">h", head, 50, 1)  # indexToLocFormat: long offsets
    tables["head"] = bytes(head)
    if "cvt " in tables:
        tables["cvt "] = _decode_cvt(tables["cvt "])
    for tag in ("hdmx", "VDMX", "DSIG"):
        tables.pop(tag, None)

    buffer = io.BytesIO()
    writer = SFNTWriter(buffer, len(tables))
    for tag in sorted(tables):
        writer[tag] = tables[tag]
    writer.close()
    return buffer.getvalue()
