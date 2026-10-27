#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image decoders used by the NPK mode-3 extractor.

KTX1 DXT1/DXT5 is delegated to ``ktx_to_png``.  This module adds DDS
support (legacy fourCC and DX10 headers) and simple Pillow-backed formats.
Only the first mip / base image is exported.
"""

from __future__ import annotations

import io
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))

import ktx_to_png

try:
    import texture2ddecoder
except ImportError:  # pragma: no cover
    texture2ddecoder = None

KTX1_ID = ktx_to_png.KTX1_IDENTIFIER
KTX2_ID = b"\xABKTX 20\xBB\r\n\x1A\n"
PNG_ID = b"\x89PNG\r\n\x1a\n"
JPEG_ID = b"\xff\xd8\xff"

DDS_MAGIC = b"DDS "
DDPF_FOURCC = 0x4
DDSCAPS2_CUBEMAP = 0x0000FE00

# DXGI formats
DXGI_R32G32B32A32_FLOAT = 2
DXGI_R16G16B16A16_FLOAT = 10
DXGI_R8G8B8A8_UNORM = 28
DXGI_R8G8B8A8_UNORM_SRGB = 29
DXGI_BC1_UNORM = 71
DXGI_BC2_UNORM = 74
DXGI_BC3_UNORM = 77
DXGI_BC5_UNORM = 83
DXGI_BC7_UNORM = 98
DXGI_B8G8R8A8_UNORM = 87
DXGI_B8G8R8X8_UNORM = 88


def classify(payload: bytes, suffix: str = "") -> str:
    suffix = suffix.lower()
    # Some game path dictionaries incorrectly label KTX files as .kta.
    # Detect by file magic first, then use the extension only as a fallback hint.
    if payload.startswith(KTX1_ID):
        return "ktx1"
    if payload.startswith(KTX2_ID):
        return "ktx2"
    if suffix in (".ktx", ".kta"):
        return "ktx1"
    if payload.startswith(DDS_MAGIC):
        return "dds"
    if payload.startswith(PNG_ID):
        return "png"
    if payload.startswith(JPEG_ID):
        return "jpeg"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WAVE":
        return "wem"
    if suffix in (".tga", ".bmp", ".webp", ".gif"):
        return suffix[1:]
    return "other"


def _decode_bc(data: bytes, width: int, height: int, kind: int) -> Image.Image:
    if texture2ddecoder is None:
        raise ValueError("texture2ddecoder is required for BC textures")
    if kind == 1:
        raw = texture2ddecoder.decode_bc1(data, width, height)
    elif kind == 3:
        raw = texture2ddecoder.decode_bc3(data, width, height)
    elif kind == 5:
        raw = texture2ddecoder.decode_bc5(data, width, height)
    elif kind == 7:
        raw = texture2ddecoder.decode_bc7(data, width, height)
    else:
        raise ValueError(f"unsupported BC kind {kind}")
    return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")


def _decode_dxt3(data: bytes, width: int, height: int) -> Image.Image:
    """Decode BC2/DXT3: 8-byte explicit 4-bit alpha + 8-byte DXT1 color."""
    out = bytearray(width * height * 4)
    bw = (width + 3) // 4
    bh = (height + 3) // 4
    offset = 0
    for by in range(bh):
        for bx in range(bw):
            block = data[offset:offset + 16]
            offset += 16
            if len(block) < 16:
                raise ValueError("truncated DXT3 block")
            alpha_bits = int.from_bytes(block[0:8], "little")
            colors = ktx_to_png._decode_color_block(block[8:16], allow_transparent=False)
            for py in range(4):
                y = by * 4 + py
                if y >= height:
                    continue
                for px in range(4):
                    x = bx * 4 + px
                    if x >= width:
                        continue
                    i = py * 4 + px
                    a = (alpha_bits >> (4 * i)) & 0xF
                    r, g, b, _ = colors[i]
                    p = (y * width + x) * 4
                    out[p:p + 4] = bytes((r, g, b, a * 17))
    return Image.frombytes("RGBA", (width, height), bytes(out))


def _half_to_byte(value: int) -> int:
    try:
        f = struct.unpack("<e", struct.pack("<H", value))[0]
    except Exception:
        return 0
    if f != f:
        return 0
    f = max(0.0, min(1.0, f))
    return int(f * 255.0 + 0.5)


def _decode_float_rgba16(data: bytes, width: int, height: int, stride: int | None = None) -> Image.Image:
    bpp = 8
    stride = stride or width * bpp
    out = bytearray(width * height * 4)
    for y in range(height):
        row = data[y * stride:y * stride + width * bpp]
        o = y * width * 4
        for x in range(width):
            p = x * bpp
            out[o + x * 4 + 0] = _half_to_byte(struct.unpack_from("<H", row, p)[0])
            out[o + x * 4 + 1] = _half_to_byte(struct.unpack_from("<H", row, p + 2)[0])
            out[o + x * 4 + 2] = _half_to_byte(struct.unpack_from("<H", row, p + 4)[0])
            out[o + x * 4 + 3] = _half_to_byte(struct.unpack_from("<H", row, p + 6)[0])
    return Image.frombytes("RGBA", (width, height), bytes(out))


def _dds_format_info(payload: bytes):
    """Return (data_offset, dxgi, fourcc, bits_per_pixel) for a DDS payload."""
    fourcc = payload[84:88]
    bit_count = struct.unpack_from("<I", payload, 88)[0]
    dxgi = None
    data_offset = 128
    if fourcc == b"DX10":
        if len(payload) < 148:
            raise ValueError("truncated DX10 header")
        dxgi = struct.unpack_from("<I", payload, 128)[0]
        data_offset = 148
    return data_offset, dxgi, fourcc, bit_count


def _dds_level_size(width: int, height: int, dxgi, fourcc: bytes, bits: int) -> int:
    bw, bh = (width + 3) // 4, (height + 3) // 4
    if dxgi in (DXGI_BC1_UNORM,) or fourcc == b"DXT1":
        return bw * bh * 8
    if dxgi in (DXGI_BC2_UNORM, DXGI_BC3_UNORM, DXGI_BC5_UNORM, DXGI_BC7_UNORM) or fourcc in (b"DXT3", b"DXT5"):
        return bw * bh * 16
    if dxgi == DXGI_R16G16B16A16_FLOAT or bits == 64:
        return width * height * 8
    if dxgi in (DXGI_R8G8B8A8_UNORM, DXGI_R8G8B8A8_UNORM_SRGB,
                DXGI_B8G8R8A8_UNORM, DXGI_B8G8R8X8_UNORM) or bits == 32:
        return width * height * 4
    if bits == 8:
        return width * height
    raise ValueError(f"无法计算 DDS mip 数据大小：DXGI={dxgi}, fourCC={fourcc!r}, bits={bits}")


def dds_to_images(payload: bytes) -> list[Image.Image]:
    """Decode the base mip of all six faces of a DDS cubemap, or one normal DDS image."""
    if len(payload) < 128 or not payload.startswith(DDS_MAGIC):
        raise ValueError("not a DDS file")
    caps2 = struct.unpack_from("<I", payload, 112)[0]
    is_cube = bool(caps2 & DDSCAPS2_CUBEMAP)
    if not is_cube:
        return [dds_to_image(payload)]
    width, height = struct.unpack_from("<II", payload, 16)[0], struct.unpack_from("<I", payload, 12)[0]
    mip_count = max(1, struct.unpack_from("<I", payload, 28)[0])
    data_offset, dxgi, fourcc, bits = _dds_format_info(payload)
    faces = []
    face_offset = data_offset
    for _face in range(6):
        first_level = payload[face_offset:face_offset + _dds_level_size(width, height, dxgi, fourcc, bits)]
        if len(first_level) != _dds_level_size(width, height, dxgi, fourcc, bits):
            raise ValueError("cubemap DDS 数据不完整")
        header = bytearray(payload[:data_offset])
        struct.pack_into("<I", header, 112, caps2 & ~DDSCAPS2_CUBEMAP)
        struct.pack_into("<I", header, 28, 1)
        one_face = bytes(header) + first_level
        faces.append(dds_to_image(one_face))
        for level in range(mip_count):
            mw, mh = max(1, width >> level), max(1, height >> level)
            face_offset += _dds_level_size(mw, mh, dxgi, fourcc, bits)
    return faces


def dds_to_image(payload: bytes) -> Image.Image:
    if len(payload) < 128 or not payload.startswith(DDS_MAGIC):
        raise ValueError("not a DDS file")
    height, width, pitch, depth, mips = struct.unpack_from("<5I", payload, 12)
    pf_flags = struct.unpack_from("<I", payload, 80)[0]
    fourcc = payload[84:88]
    bit_count = struct.unpack_from("<I", payload, 88)[0]
    caps2 = struct.unpack_from("<I", payload, 112)[0]
    if depth > 1:
        raise ValueError("volume DDS not supported")
    if width == 0 or height == 0 or width > 16384 or height > 16384:
        raise ValueError("invalid DDS dimensions")

    if fourcc == b"DX10":
        if len(payload) < 148:
            raise ValueError("truncated DX10 header")
        dxgi = struct.unpack_from("<I", payload, 128)[0]
        data = payload[148:]
        if dxgi == DXGI_R16G16B16A16_FLOAT:
            return _decode_float_rgba16(data, width, height)
        if dxgi in (DXGI_R8G8B8A8_UNORM, DXGI_R8G8B8A8_UNORM_SRGB):
            return Image.frombytes("RGBA", (width, height), data[:width * height * 4])
        if dxgi in (DXGI_B8G8R8A8_UNORM, DXGI_B8G8R8X8_UNORM):
            return Image.frombytes("RGBA", (width, height), data[:width * height * 4], "raw", "BGRA")
        if dxgi in (DXGI_BC1_UNORM, DXGI_BC2_UNORM, DXGI_BC3_UNORM, DXGI_BC5_UNORM, DXGI_BC7_UNORM):
            bw = (width + 3) // 4
            bh = (height + 3) // 4
            if dxgi == DXGI_BC1_UNORM:
                size = bw * bh * 8
                return _decode_bc(data[:size], width, height, 1)
            if dxgi == DXGI_BC2_UNORM:
                return _decode_dxt3(data[:bw * bh * 16], width, height)
            if dxgi == DXGI_BC3_UNORM:
                return _decode_bc(data[:bw * bh * 16], width, height, 3)
            if dxgi == DXGI_BC5_UNORM:
                return _decode_bc(data[:bw * bh * 16], width, height, 5)
            return _decode_bc(data[:bw * bh * 16], width, height, 7)
        raise ValueError(f"unsupported DXGI format {dxgi}")

    data = payload[128:]
    if fourcc == b"DXT1":
        bw = (width + 3) // 4
        bh = (height + 3) // 4
        return _decode_bc(data[:bw * bh * 8], width, height, 1)
    if fourcc == b"DXT3":
        bw = (width + 3) // 4
        bh = (height + 3) // 4
        return _decode_dxt3(data[:bw * bh * 16], width, height)
    if fourcc == b"DXT5":
        bw = (width + 3) // 4
        bh = (height + 3) // 4
        return _decode_bc(data[:bw * bh * 16], width, height, 3)
    if fourcc == b"DX10":
        raise ValueError("handled above")
    # A16B16G16R16F uses fourCC 0x71 (113) in this client's DDS writer.
    if int.from_bytes(fourcc, "little") == 0x71 or bit_count == 64:
        return _decode_float_rgba16(data, width, height)
    if pf_flags & 0x20000 or bit_count == 8:
        stride = pitch if pitch >= width else width
        return Image.frombytes("L", (width, height), data[:stride * height], "raw", "L", stride, 1)
    if bit_count == 32:
        stride = pitch if pitch >= width * 4 else width * 4
        # Most legacy 32-bit DDS files in this build are BGRA/RGBA masks.
        return Image.frombytes("RGBA", (width, height), data[:stride * height], "raw", "BGRA", stride, 1)
    raise ValueError(f"unsupported legacy DDS fourCC={fourcc!r} bits={bit_count}")


def _ktx1_internal_format(payload: bytes) -> int | None:
    """Return KTX1 glInternalFormat from the file header, if valid."""
    if len(payload) < 64 or not payload.startswith(KTX1_ID):
        return None
    try:
        if struct.unpack_from("<I", payload, 12)[0] != 0x04030201:
            return None
        return struct.unpack_from("<I", payload, 28)[0]
    except struct.error:
        return None


def _decode_astc_ktx(payload: bytes, output: Path, astcenc_path: str | None = None) -> None:
    """Decode ASTC KTX1 by extracting its first mip into a raw .astc bitstream."""
    from ktx_to_png import _ASTC_BLOCKS, read_ktx1_bytes
    width, height, internal, compressed = read_ktx1_bytes(payload)
    if internal not in _ASTC_BLOCKS:
        raise ValueError(f"不是受支持的 ASTC KTX1 格式：0x{internal:04X}")
    block_w, block_h = _ASTC_BLOCKS[internal]
    exe = astcenc_path or os.environ.get("NOTX_ASTCENC")
    if not exe or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        raise ValueError(f"ASTC 贴图格式 0x{internal:04X} 已识别，但 APK 未包含可运行的 ASTC 解码器")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # astcenc expects the 16-byte ASTC file header, not a KTX container.
    astc_header = (b"\x13\xAB\xA1\x5C" + bytes((block_w, block_h, 1)) +
                   width.to_bytes(3, "little") + height.to_bytes(3, "little") +
                   (1).to_bytes(3, "little"))
    with tempfile.TemporaryDirectory(prefix="notx_astc_") as td:
        source = Path(td) / "input.astc"
        decoded = Path(td) / "decoded.png"
        source.write_bytes(astc_header + compressed)
        errors = []
        for mode in ("-ds", "-dl", "-dh", "-dH"):
            try:
                proc = subprocess.run([exe, mode, str(source), str(decoded)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
            except Exception as exc:
                errors.append(f"{mode}: {exc}")
                continue
            if proc.returncode == 0 and decoded.exists() and decoded.stat().st_size > 8:
                output.write_bytes(decoded.read_bytes())
                return
            errors.append(f"{mode}: {(proc.stderr or proc.stdout or str(proc.returncode))[-240:]}")
            try:
                decoded.unlink()
            except FileNotFoundError:
                pass
    raise ValueError("ASTC 解码失败；" + " | ".join(errors))


def convert_image(payload: bytes, src_suffix: str, output: Path, astcenc_path: str | None = None) -> tuple[str, str]:
    """Convert a payload to PNG when possible.

    Returns (status, final_suffix).  On unsupported content raises ValueError
    so the caller can preserve the original bytes.
    """
    kind = classify(payload, src_suffix)
    output = Path(output)
    if kind == "ktx1":
        # Prefer the KTX-aware decoder. If ASTC support isn't bundled in
        # texture2ddecoder, extract the compressed mip to a valid raw .astc file
        # before invoking astcenc (never pass the KTX container directly).
        try:
            ktx_to_png.convert_bytes(payload, output)
        except Exception as ktx_exc:
            internal = _ktx1_internal_format(payload)
            astc_formats = set(range(0x93B0, 0x93BE)) | set(range(0x93D0, 0x93DE))
            if internal not in astc_formats:
                raise ktx_exc
            _decode_astc_ktx(payload, output, astcenc_path)
        return "converted_png", ".png"
    if kind == "dds":
        images = dds_to_images(payload)
        if len(images) == 1:
            images[0].save(output, "PNG")
        else:
            # Cubemap faces are emitted separately with stable face suffixes.
            for suffix, image in zip(("px", "nx", "py", "ny", "pz", "nz"), images):
                face_path = output.with_name(output.stem + "_" + suffix + ".png")
                image.save(face_path, "PNG")
        return "converted_png", ".png"
    if kind == "png":
        if output.suffix.lower() == ".png":
            output.write_bytes(payload)
        else:
            output.with_suffix(".png").write_bytes(payload)
        return "copied_png", ".png"
    if kind in ("jpeg", "tga", "bmp", "webp", "gif"):
        image = Image.open(io.BytesIO(payload))
        image.load()
        image.save(output.with_suffix(".png") if output.suffix.lower() != ".png" else output, "PNG")
        return "converted_png", ".png"
    raise ValueError(f"payload is not a supported image ({kind})")


def image_extension(payload: bytes, src_suffix: str) -> str:
    """Best-effort extension for an unnamed payload."""
    kind = classify(payload, src_suffix)
    if kind in ("ktx1", "ktx2"):
        return ".ktx"
    if kind == "dds":
        return ".dds"
    if kind == "png":
        return ".png"
    if kind == "jpeg":
        return ".jpg"
    if kind == "wem":
        return ".wem"
    if payload[:4] == b"BKHD":
        return ".bnk"
    if payload[:4] == b"\x34\x80\xc8\xbb":
        return ".mesh"
    if payload[:4] == b"AKPK":
        return ".npk"
    return ".bin"
