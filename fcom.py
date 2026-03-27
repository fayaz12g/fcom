#!/usr/bin/env python3
"""
FCOM — Image, audio, and text compression for GCP files.

Commands
--------
  image       <input.png>  <output.avif>  [--quality 60]
              Converts PNG (or any image) to AVIF via Pillow.
              Quality 0-100; default 60 matches Squoosh's "good" preset.
              Lower = smaller file, higher = better fidelity.

  audio       <input.mp3>  <output.opus>  [--bitrate 64]
              Re-encodes audio to Opus via ffmpeg.
              Bitrate in kbps; default 64k.
              Opus at 64k sounds better than MP3 at 128k.

  text        <input>  <output>
              Compresses any file with Brotli at quality 11 (optimal).

  decompress  <input>  <output>
              Decompresses a Brotli-compressed file.

Install deps (once)
-------------------
  pip install pillow brotli
  # ffmpeg must be on PATH (brew install ffmpeg / apt install ffmpeg)
"""

import argparse
import brotli
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image


# ── helpers -------------------------------------------------------------------

def _file_kb(path: str) -> float:
    return os.path.getsize(path) / 1024


def _print_stats(label_in: str, size_in: float,
                 label_out: str, size_out: float) -> None:
    saved = size_in - size_out
    pct   = saved / size_in * 100 if size_in else 0
    width = max(len(label_in), len(label_out))
    print(f"  {label_in:<{width}}  {size_in:>8.1f} KB")
    print(f"  {label_out:<{width}}  {size_out:>8.1f} KB")
    print(f"  {'Saved':<{width}}  {saved:>8.1f} KB  ({pct:.1f}% reduction)")


# ── image ---------------------------------------------------------------------

def cmd_image(args: argparse.Namespace) -> None:
    src  = args.input
    dst  = args.output
    q    = args.quality    # 0-100

    img = Image.open(src).convert("RGBA")

    # Pillow AVIF quality maps 0-100 where 100 = best quality / largest file.
    # speed=4 is a good encode-speed/compression trade-off (0=slowest/best).
    img.save(dst, format="AVIF", quality=q, speed=4)

    size_in  = _file_kb(src)
    size_out = _file_kb(dst)

    print(f"\nImage compressed: {Path(src).name} → {Path(dst).name}")
    _print_stats(Path(src).suffix.upper().lstrip("."), size_in,
                 "AVIF", size_out)


# ── audio ---------------------------------------------------------------------

def cmd_audio(args: argparse.Namespace) -> None:
    src     = args.input
    dst     = args.output
    bitrate = f"{args.bitrate}k"

    # ffmpeg flags:
    #   -vn          strip any video/album-art stream
    #   -c:a libopus use Opus encoder
    #   -b:a         target bitrate
    #   -application audio  optimise for generic audio (not voice)
    #   -y           overwrite output without asking
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", src,
         "-vn", "-c:a", "libopus",
         "-b:a", bitrate,
         "-application", "audio",
         dst],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print("ffmpeg error:\n", result.stderr, file=sys.stderr)
        sys.exit(1)

    size_in  = _file_kb(src)
    size_out = _file_kb(dst)

    print(f"\nAudio compressed: {Path(src).name} → {Path(dst).name}")
    _print_stats("MP3", size_in, "Opus", size_out)


# ── text (brotli) -------------------------------------------------------------

def cmd_text(args: argparse.Namespace) -> None:
    data       = open(args.input, "rb").read()
    compressed = brotli.compress(data, quality=11)
    open(args.output, "wb").write(compressed)

    before = len(data)
    after  = len(compressed)
    saved  = before - after
    pct    = saved / before * 100 if before else 0

    print(f"\nText compressed: {Path(args.input).name} → {Path(args.output).name}")
    print(f"  Before  {before:>10,} bytes")
    print(f"  After   {after:>10,} bytes")
    print(f"  Saved   {saved:>10,} bytes  ({pct:.1f}% reduction)")


def cmd_decompress(args: argparse.Namespace) -> None:
    data         = open(args.input, "rb").read()
    decompressed = brotli.decompress(data)
    open(args.output, "wb").write(decompressed)

    print(f"\nDecompressed: {Path(args.input).name} → {Path(args.output).name}")
    print(f"  Before  {len(data):>10,} bytes")
    print(f"  After   {len(decompressed):>10,} bytes")


# ── CLI ----------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="mediapress — AVIF image, Opus audio, and Brotli text compression"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    img = sub.add_parser("image", help="PNG → AVIF")
    img.add_argument("input",  help="Input image (PNG, JPG, …)")
    img.add_argument("output", help="Output AVIF file")
    img.add_argument("--quality", type=int, default=60,
                     help="AVIF quality 0-100 (default 60)")

    aud = sub.add_parser("audio", help="MP3 → Opus")
    aud.add_argument("input",  help="Input audio (MP3, WAV, …)")
    aud.add_argument("output", help="Output .opus file")
    aud.add_argument("--bitrate", type=int, default=64,
                     help="Opus bitrate in kbps (default 64)")

    txt = sub.add_parser("text", help="Any file → Brotli (quality 11)")
    txt.add_argument("input",  help="Input file")
    txt.add_argument("output", help="Output .br file")

    dec = sub.add_parser("decompress", help="Brotli → original")
    dec.add_argument("input",  help="Input .br file")
    dec.add_argument("output", help="Output file")

    args = p.parse_args()
    {
        "image":      cmd_image,
        "audio":      cmd_audio,
        "text":       cmd_text,
        "decompress": cmd_decompress,
    }[args.cmd](args)


if __name__ == "__main__":
    main()