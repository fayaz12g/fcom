#!/usr/bin/env python3
"""
FCOM — Build tool for GCP archives.

Commands
--------
  build <input_folder> <output_dir> --key SECRET [--name archive_name]
      Converts all assets in <input_folder>:
        *.png  → *.gci  (AVIF-compressed image)
        *.mp3  → *.gcs  (Opus-compressed audio)
        *.json → *.gcd  (Brotli-compressed data)
      Bundles them into a RAR, then encrypts the archive into a .gcp file.

  extract <input.gcp> <output_dir> --key SECRET
      Decrypts a .gcp file and extracts its contents.

  # Low-level helpers (still available for individual use):
  image <input> <output.gci> [--quality 60]
  audio <input> <output.gcs> [--bitrate 64]
  text  <input> <output.gcd>
  decompress <input.gcd> <output>

Install deps
------------
  pip install pillow brotli cryptography
  # ffmpeg and rar/unrar must be on PATH

Encryption
----------
  AES-256-GCM with a key derived from your password via PBKDF2-SHA256
  (600k iterations, random 128-bit salt per build). The .gcp file format
  is proprietary: a 4-byte magic header followed by salt, nonce, and
  GCM ciphertext+tag. Without the password the file is opaque.
"""

import argparse
import brotli
import os
from dotenv import load_dotenv
import secrets
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ── GCP format constants ──────────────────────────────────────────────────────

_GCP_MAGIC      = b"GCP\x01"   # 4 bytes — proprietary magic, version 1
_SALT_LEN       = 16           # 128-bit random salt  (bytes 4–19)
_NONCE_LEN      = 12           # 96-bit AES-GCM nonce (bytes 20–31)
_HEADER_LEN     = len(_GCP_MAGIC) + _SALT_LEN + _NONCE_LEN  # 32 bytes total
_KDF_ITERATIONS = 600_000      # PBKDF2 work factor

# ── helpers ───────────────────────────────────────────────────────────────────

def _file_kb(path) -> float:
    return os.path.getsize(path) / 1024

def resolve_key(cli_key):
    load_dotenv()

    env_key = os.getenv("FCOM_PKI")

    if env_key:
        return env_key
    if cli_key:
        return cli_key

    print("Error: No encryption key provided via .env or --key")
    sys.exit(1)

def _print_stats(label_in: str, size_in: float,
                 label_out: str, size_out: float) -> None:
    saved = size_in - size_out
    pct   = saved / size_in * 100 if size_in else 0
    w     = max(len(label_in), len(label_out))
    print(f"    {label_in:<{w}}  {size_in:>8.1f} KB")
    print(f"    {label_out:<{w}}  {size_out:>8.1f} KB")
    print(f"    {'Saved':<{w}}  {saved:>8.1f} KB  ({pct:.1f}% reduction)")


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a password using PBKDF2-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(password.encode())

# ── low-level: image ──────────────────────────────────────────────────────────

def cmd_image(args: argparse.Namespace) -> None:
    src, dst, q = args.input, args.output, args.quality
    img = Image.open(src)
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "PA") else img.convert("RGB")
    img.save(dst, format="AVIF", quality=q, speed=4)
    size_in, size_out = _file_kb(src), _file_kb(dst)
    print(f"\nImage: {Path(src).name} → {Path(dst).name}")
    _print_stats(Path(src).suffix.upper().lstrip("."), size_in, "GCI/AVIF", size_out)

# ── low-level: audio ──────────────────────────────────────────────────────────

def cmd_audio(args: argparse.Namespace) -> None:
    src, dst, bitrate = args.input, args.output, f"{args.bitrate}k"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", src,
         "-vn", "-c:a", "libopus", "-b:a", bitrate, "-application", "audio",
         "-f", "ogg", dst],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ffmpeg error:\n", result.stderr, file=sys.stderr)
        sys.exit(1)
    size_in, size_out = _file_kb(src), _file_kb(dst)
    print(f"\nAudio: {Path(src).name} → {Path(dst).name}")
    _print_stats(Path(src).suffix.upper().lstrip("."), size_in, "GCS/Opus", size_out)

# ── low-level: text ───────────────────────────────────────────────────────────

def cmd_text(args: argparse.Namespace) -> None:
    data       = open(args.input,  "rb").read()
    compressed = brotli.compress(data, quality=11)
    open(args.output, "wb").write(compressed)
    before, after = len(data), len(compressed)
    pct = (before - after) / before * 100 if before else 0
    print(f"\nText: {Path(args.input).name} → {Path(args.output).name}")
    print(f"    Before  {before:>10,} bytes")
    print(f"    After   {after:>10,} bytes")
    print(f"    Saved   {before - after:>10,} bytes  ({pct:.1f}% reduction)")


def cmd_decompress(args: argparse.Namespace) -> None:
    data         = open(args.input, "rb").read()
    decompressed = brotli.decompress(data)
    open(args.output, "wb").write(decompressed)
    print(f"\nDecompressed: {Path(args.input).name} → {Path(args.output).name}")
    print(f"    Before  {len(data):>10,} bytes")
    print(f"    After   {len(decompressed):>10,} bytes")

# ── build ─────────────────────────────────────────────────────────────────────

def cmd_build(args: argparse.Namespace) -> None:
    folder  = Path(args.input)
    out_dir = Path(args.output)
    key     = resolve_key(args.key)
    name    = args.name or folder.name

    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as _tmp:
        tmp       = Path(_tmp)
        converted = []

        # ── PNG → GCI  (recursive) ───────────────────────────────────────────
        pngs = sorted(folder.rglob("*.png"))
        if pngs:
            print("\n[images]")
        for png in pngs:
            dst = tmp / (png.stem + ".gci")
            try:
                img = Image.open(png)
                img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "PA") else img.convert("RGB")
                img.save(str(dst), format="AVIF", quality=60, speed=4)
                rel = png.relative_to(folder)
                print(f"  {str(rel):<35} {_file_kb(png):>7.1f} KB  →  {_file_kb(dst):>7.1f} KB")
                converted.append(dst)
            except Exception as e:
                print(f"  WARNING: skipping {png} — {e}", file=sys.stderr)

        # ── MP3 → GCS  (recursive) ───────────────────────────────────────────
        mp3s = sorted(folder.rglob("*.mp3"))
        if mp3s:
            print("\n[audio]")
        for mp3 in mp3s:
            dst = tmp / (mp3.stem + ".gcs")
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(mp3),
                 "-vn", "-c:a", "libopus", "-b:a", "64k", "-application", "audio",
                 "-f", "ogg", str(dst)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR: ffmpeg failed on {mp3.relative_to(folder)}:\n{result.stderr}", file=sys.stderr)
                sys.exit(1)
            rel = mp3.relative_to(folder)
            print(f"  {str(rel):<35} {_file_kb(mp3):>7.1f} KB  →  {_file_kb(dst):>7.1f} KB")
            converted.append(dst)

        # ── JSON → GCD  (recursive) ──────────────────────────────────────────
        jsons = sorted(folder.rglob("*.json"))
        if jsons:
            print("\n[data]")
        for jf in jsons:
            dst = tmp / (jf.stem + ".gcd")
            try:
                raw = jf.read_bytes()
                dst.write_bytes(brotli.compress(raw, quality=11))
                rel = jf.relative_to(folder)
                print(f"  {str(rel):<35} {_file_kb(jf):>7.1f} KB  →  {_file_kb(dst):>7.1f} KB")
                converted.append(dst)
            except Exception as e:
                print(f"  WARNING: skipping {jf} — {e}", file=sys.stderr)

        if not converted:
            print("No convertible files found (*.png, *.mp3, *.json). Nothing to build.")
            sys.exit(0)

        # ── Bundle into ZIP (stored — files are already compressed) ─────────
        print(f"\n[archive]  packing {len(converted)} file(s) …")
        zip_path = tmp / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            for f in converted:
                zf.write(f, arcname=f.name)

        # ── Encrypt → .gcp ───────────────────────────────────────────────────
        print("[encrypt]  AES-256-GCM …")
        zip_bytes  = zip_path.read_bytes()
        salt       = secrets.token_bytes(_SALT_LEN)
        nonce      = secrets.token_bytes(_NONCE_LEN)
        derived    = _derive_key(key, salt)
        ciphertext = AESGCM(derived).encrypt(nonce, zip_bytes, None)

        gcp_path = out_dir / f"{name}.gcp"
        with open(gcp_path, "wb") as f:
            f.write(_GCP_MAGIC)   # 4 bytes
            f.write(salt)          # 16 bytes
            f.write(nonce)         # 12 bytes
            f.write(ciphertext)    # len(rar) + 16-byte GCM auth tag

        total_in  = sum(_file_kb(p) for p in pngs + mp3s + jsons)
        total_out = _file_kb(gcp_path)
        print(f"\n✓  {gcp_path}")
        print(f"   {total_in:.1f} KB  →  {total_out:.1f} KB total  "
              f"({(total_in - total_out) / total_in * 100:.1f}% reduction)")

# ── extract ───────────────────────────────────────────────────────────────────

def cmd_extract(args: argparse.Namespace) -> None:
    gcp_path = Path(args.input)
    out_dir  = Path(args.output)
    key      = args.key

    if not gcp_path.is_file():
        print(f"Error: '{gcp_path}' not found.", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    data = gcp_path.read_bytes()

    # Validate magic
    if len(data) < _HEADER_LEN or data[:4] != _GCP_MAGIC:
        print("Error: not a valid .gcp file (bad magic bytes).", file=sys.stderr)
        sys.exit(1)

    salt       = data[4:20]
    nonce      = data[20:32]
    ciphertext = data[32:]

    # Decrypt
    derived = _derive_key(key, salt)
    try:
        zip_bytes = AESGCM(derived).decrypt(nonce, ciphertext, None)
    except Exception:
        print("Error: decryption failed — wrong key or corrupted file.", file=sys.stderr)
        sys.exit(1)

    # Extract ZIP into a subfolder named after the archive
    extract_dir = out_dir / gcp_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as _tmp:
        tmp      = Path(_tmp)
        zip_path = tmp / "archive.zip"
        zip_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

    print(f"✓  Extracted to {extract_dir}")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p   = argparse.ArgumentParser(description="fcom — GCP archive build tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    # build
    b = sub.add_parser("build", help="Compress a folder into a .gcp archive")
    b.add_argument("input",  help="Source folder (flat; contains *.png, *.mp3, *.json)")
    b.add_argument("output", help="Output directory")
    b.add_argument("--key",  required=False, help="Encryption password")
    b.add_argument("--name", default=None,  help="Archive base name (default: folder name)")

    # extract
    x = sub.add_parser("extract", help="Decrypt and extract a .gcp archive")
    x.add_argument("input",  help="Input .gcp file")
    x.add_argument("output", help="Output directory")
    x.add_argument("--key",  required=False, help="Encryption password")

    # image (low-level helper)
    img = sub.add_parser("image", help="Single image → GCI/AVIF")
    img.add_argument("input");  img.add_argument("output")
    img.add_argument("--quality", type=int, default=60)

    # audio (low-level helper)
    aud = sub.add_parser("audio", help="Single audio file → GCS/Opus")
    aud.add_argument("input");  aud.add_argument("output")
    aud.add_argument("--bitrate", type=int, default=64)

    # text (low-level helper)
    txt = sub.add_parser("text", help="Single file → GCD/Brotli")
    txt.add_argument("input");  txt.add_argument("output")

    # decompress (low-level helper)
    dec = sub.add_parser("decompress", help="GCD/Brotli → original")
    dec.add_argument("input");  dec.add_argument("output")

    args = p.parse_args()
    {
        "build":      cmd_build,
        "extract":    cmd_extract,
        "image":      cmd_image,
        "audio":      cmd_audio,
        "text":       cmd_text,
        "decompress": cmd_decompress,
    }[args.cmd](args)


if __name__ == "__main__":
    main()