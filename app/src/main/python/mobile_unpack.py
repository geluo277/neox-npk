# Android adaptation for texture-only extraction from Eggy Party PC NXPK files.
import os, gzip, shutil, zipfile
from pathlib import Path
import zstandard
from PIL import Image
import nxpk_mode3 as N
import image_convert

IMAGE_EXTS = {".kta", ".dds", ".ktx", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".webp", ".gif"}

def _safe_rel(path, signature, package_name):
    if not path:
        return f"_unresolved/{package_name}/{signature:08x}"
    path = path.replace("\\", "/").lstrip("/")
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    if not parts:
        return f"_unresolved/{package_name}/{signature:08x}"
    return "/".join(parts)

def extract_images(npk_path, output_dir, pathdict_path, jpg=False):
    """Extract only texture-like payloads. Returns a JSON-serializable summary."""
    npk_path = Path(npk_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolver = N.PathResolver.from_file(pathdict_path)
    # Fail early when the header/index does not match the supported NXPK mode-3 format.
    # Without this validation, an incompatible package can be silently skipped entry-by-entry,
    # producing a misleading 22-byte empty ZIP.
    header, entries = N.read_index(npk_path, validate=True, resolver=resolver)
    count_ok = count_fail = count_skip = 0
    dctx = zstandard.ZstdDecompressor()
    with open(npk_path, "rb") as src:
        for i, entry in enumerate(entries):
            try:
                if entry.packed_size == 0 and entry.unpacked_size == 0:
                    count_skip += 1
                    continue
                src.seek(entry.offset)
                packed = src.read(entry.packed_size)
                if len(packed) != entry.packed_size:
                    raise ValueError("NPK 数据不完整")
                if entry.compression == 3:
                    payload = dctx.decompress(packed, max_output_size=max(1, entry.unpacked_size))
                elif entry.compression == 0:
                    payload = packed
                else:
                    count_skip += 1
                    continue
                if len(payload) != entry.unpacked_size:
                    raise ValueError("解压后大小不匹配")
                real_path, _ = resolver.resolve(entry.signature)
                suffix = Path(real_path or "").suffix.lower()
                kind = image_convert.classify(payload, suffix)
                if kind not in ("ktx1", "ktx2", "dds", "png", "jpeg", "tga", "bmp", "webp", "gif"):
                    count_skip += 1
                    continue
                if kind == "ktx2":
                    # Keep unsupported KTX2 intact rather than silently corrupting it.
                    rel = _safe_rel(real_path, entry.signature, npk_path.name)
                    target = out / (rel + ".ktx2")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    count_skip += 1
                    continue
                rel = _safe_rel(real_path, entry.signature, npk_path.name)
                target_ext = ".jpg" if jpg else ".png"
                target = out / str(Path(rel).with_suffix(target_ext))
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.stem + ".tmp.png")
                try:
                    image_convert.convert_image(payload, suffix, tmp)
                    with Image.open(tmp) as im:
                        if jpg:
                            if im.mode not in ("RGB", "L"):
                                bg = Image.new("RGB", im.size, (255,255,255))
                                if "A" in im.getbands():
                                    bg.paste(im, mask=im.getchannel("A"))
                                else:
                                    bg.paste(im.convert("RGB"))
                                bg.save(target, "JPEG", quality=95, optimize=True)
                            else:
                                im.convert("RGB").save(target, "JPEG", quality=95, optimize=True)
                        else:
                            im.save(target, "PNG")
                    tmp.unlink(missing_ok=True)
                    count_ok += 1
                except Exception:
                    tmp.unlink(missing_ok=True)
                    # Preserve original bytes for unsupported texture formats.
                    fallback = out / str(Path(rel).with_suffix(suffix or ".bin"))
                    fallback.parent.mkdir(parents=True, exist_ok=True)
                    fallback.write_bytes(payload)
                    count_fail += 1
            except Exception:
                count_fail += 1
    # Do not report success if nothing was written. This commonly indicates an unsupported
    # package format/version, a wrong index key, or a path/texture recognition mismatch.
    written_files = [p for p in out.rglob("*") if p.is_file()]
    if not written_files:
        raise RuntimeError(
            "没有提取出任何文件。该 NPK 可能不兼容当前内置的 NXPK Mode 3 索引格式/密钥，"
            "也可能没有可识别的贴图。请使用支持的 PC 版 NXPK 包测试，并检查游戏版本。"
        )
    return {"total": len(entries), "exported": count_ok, "fallback_or_failed": count_fail,
            "skipped": count_skip, "written_files": len(written_files), "output": str(out)}

# Resource type signatures used by the full-resource exporter.
def _detect_resource(payload: bytes, suffix: str = ""):
    head = payload[:16]
    s = (suffix or "").lower()
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "贴图", ".png"
    if head.startswith(b"\xff\xd8\xff"): return "贴图", ".jpg"
    if head.startswith(b"DDS "): return "贴图", ".dds"
    if head.startswith(b"\xabKTX 11\xbb\r\n\x1a\n"): return "贴图", ".ktx"
    if head.startswith(b"\xabKTX 20\xbb\r\n\x1a\n"): return "贴图", ".ktx2"
    if head.startswith(b"\x13\xab\xa1\x5c"): return "贴图", ".astc"
    if head.startswith(b"\x1f\x8b"): return "其他", ".gz"
    if head.startswith(b"OggS"): return "音频", ".ogg"
    if head.startswith(b"fLaC"): return "音频", ".flac"
    if head.startswith(b"RIFF") and len(payload) >= 12:
        if payload[8:12] == b"WEBP": return "贴图", ".webp"
        if payload[8:12] == b"WAVE": return "音频", ".wav"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xff and (head[1] & 0xe0) == 0xe0): return "音频", ".mp3"
    if head.startswith(b"glTF"): return "3D模型", ".glb"
    if head.startswith(b"Kaydara FBX Binary"): return "3D模型", ".fbx"
    if head.startswith(b"PK\x03\x04"): return "其他", ".zip"
    if head.startswith(b"UnityFS") or head.startswith(b"UnityRaw"): return "3D模型", ".unity3d"
    # Use path extension as a hint only when the payload does not contradict it.
    ext_map = {
        ".ktx": ("贴图", ".ktx"), ".ktx2": ("贴图", ".ktx2"), ".dds": ("贴图", ".dds"),
        ".png": ("贴图", ".png"), ".jpg": ("贴图", ".jpg"), ".jpeg": ("贴图", ".jpg"),
        ".tga": ("贴图", ".tga"), ".astc": ("贴图", ".astc"), ".wav": ("音频", ".wav"),
        ".ogg": ("音频", ".ogg"), ".mp3": ("音频", ".mp3"), ".fbx": ("3D模型", ".fbx"),
        ".obj": ("3D模型", ".obj"), ".gltf": ("3D模型", ".gltf"), ".glb": ("3D模型", ".glb"),
        ".json": ("代码与配置", ".json"), ".lua": ("代码与配置", ".lua"), ".bytes": ("代码与配置", ".bytes"),
        ".txt": ("代码与配置", ".txt"), ".xml": ("UI", ".xml"), ".prefab": ("UI", ".prefab"),
        ".bank": ("音频", ".bank"), ".wem": ("音频", ".wem"), ".bnk": ("音频", ".bnk"),
    }
    if s in ext_map: return ext_map[s]
    # Unknown data stays byte-for-byte intact; do not guess a conversion.
    return "其他", (s if s and len(s) <= 12 else ".bin")


def extract_all_resources(npk_path, output_dir, pathdict_path):
    """Export every indexed entry without converting its payload.

    Supports the known NXPK Mode-3 index with stored (0) and Zstandard (3)
    payloads. Unknown compression values are preserved as packed bytes so that
    extraction does not silently discard an indexed resource.
    """
    npk_path = Path(npk_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolver = N.PathResolver.from_file(pathdict_path)
    header, entries = N.read_index(npk_path, validate=False, resolver=resolver)
    file_size = npk_path.stat().st_size
    dctx = zstandard.ZstdDecompressor()
    exported = 0
    decompressed = 0
    preserved_packed = 0
    errors = []
    used_names = set()
    with open(npk_path, "rb") as src:
        for index, entry in enumerate(entries, 1):
            try:
                start, end = entry.offset, entry.offset + entry.packed_size
                if start < 24 or end > file_size or end > header.index_offset:
                    raise ValueError("资源偏移超出数据区")
                src.seek(start)
                packed = src.read(entry.packed_size)
                if len(packed) != entry.packed_size:
                    raise ValueError("资源数据不完整")
                if entry.compression == 3:
                    payload = dctx.decompress(packed, max_output_size=max(1, entry.unpacked_size))
                    if len(payload) != entry.unpacked_size:
                        raise ValueError("Zstandard 解压后大小不匹配")
                    decompressed += 1
                elif entry.compression == 0:
                    payload = packed
                    if len(payload) != entry.unpacked_size:
                        raise ValueError("原始数据大小不匹配")
                else:
                    # Preserve unsupported compression payload rather than losing it.
                    payload = packed
                    preserved_packed += 1
                real_path, _ = resolver.resolve(entry.signature)
                suffix = Path(real_path or "").suffix.lower()
                category, detected_ext = _detect_resource(payload, suffix)
                rel = _safe_rel(real_path, entry.signature, npk_path.stem)
                original = Path(rel)
                # Keep useful resolved filenames; unknown hash-only names get a detected extension.
                if not original.suffix:
                    original = original.with_suffix(detected_ext)
                elif not suffix:
                    original = original.with_suffix(detected_ext)
                rel_out = Path(category) / original
                target = out / rel_out
                key = str(rel_out).lower()
                if key in used_names or target.exists():
                    target = target.with_name(f"{target.stem}_{index:04d}{target.suffix}")
                    key = str(target.relative_to(out)).lower()
                used_names.add(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                exported += 1

                # Also create a PNG companion for preview/export when a texture decoder
                # supports the payload. Keep the original bytes unchanged beside it.
                if category == "贴图" and image_convert.classify(payload, suffix) in (
                    "ktx1", "dds", "png", "jpeg", "tga", "bmp", "webp", "gif"
                ):
                    try:
                        png_target = target.with_suffix(".png")
                        if png_target.resolve() != target.resolve():
                            # Avoid overwriting an existing PNG resource with the same name.
                            if png_target.exists():
                                png_target = target.with_name(target.stem + "_converted.png")
                            image_convert.convert_image(payload, suffix, png_target)
                    except Exception as convert_exc:
                        # Unsupported texture encodings remain available as original files.
                        errors.append({"entry": index, "signature": f"{entry.signature:08x}",
                                       "error": "PNG 转换未成功：" + str(convert_exc)})
            except Exception as exc:
                errors.append({"entry": index, "signature": f"{entry.signature:08x}", "error": str(exc)})
    if exported == 0:
        raise RuntimeError("没有导出任何资源。该文件可能使用了不兼容的索引格式或索引密钥。")
    return {
        "entries": len(entries), "exported": exported, "zstd_decompressed": decompressed,
        "packed_preserved": preserved_packed, "failed": len(errors),
        "failures": errors[:10], "output": str(out),
        "note": "所有成功导出的条目均保留原始解压后数据；分类依据文件头和路径后缀，未知资源放入‘其他’。"
    }
