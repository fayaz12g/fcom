#!/usr/bin/env python3
"""
FCOM - Fayaz Compress
---------------------
Inline-definition pointer compression with recursive pattern encoding.

Encoding scheme
---------------
Tokens occupy bytes 0x80-0xFE (126 slots, safe for ASCII input).
Each token has two forms in the stream:

  DEFINITION  (first occurrence):  TOKEN  LEN  <def_bytes>
  POINTER     (later occurrences):  TOKEN

def_bytes are themselves encoded using already-defined tokens (lower-index
patterns), so pattern definitions compress each other recursively.

Example
-------
  text: "banananananananananaana"
  token 0x80 -> "ana"  (def: 61 6e 61, 3 raw bytes)
  token 0x81 -> "anananana"  (def: 80 80 80, 3 bytes instead of 9)

Decoder reads TOKEN:
  - unseen -> read LEN, read def_bytes, decode def_bytes through current
              token map, store result, emit
  - seen   -> emit stored string

Savings formula  (pattern length L, frequency F, def_bytes length D)
-----------------------------------------------------------
  D = compressed definition length (may be << L)
  cost    = (2 + D) + (F-1)*1   = D + F + 1
  without = F * L
  savings = F*L - D - F - 1  =  F*(L-1) - D - 1
"""

from collections import Counter

MIN_PATTERN_LEN = 2
MAX_PATTERN_LEN = 32      # higher ceiling — recursive defs make long patterns cheap
TOKEN_BASE      = 0x80    # 0x80-0xFE = 126 token slots
MAX_TOKENS      = 0xFE - TOKEN_BASE


# ── helpers -------------------------------------------------------------------

def _encode_with_tokens(text, token_of, available_tokens):
    """
    Encode `text` (a str) as bytes, substituting any pattern in
    available_tokens (a subset of token_of) with its token byte.
    Literals are emitted as raw bytes.  Longest-match, left to right.
    """
    if not available_tokens:
        return text.encode("utf-8")

    # sort longest-first for greedy match
    ordered = sorted(available_tokens, key=lambda p: -len(p))
    out = bytearray()
    i = 0
    while i < len(text):
        for pat in ordered:
            if text.startswith(pat, i):
                out.append(token_of[pat])
                i += len(pat)
                break
        else:
            out.append(ord(text[i]))
            i += 1
    return bytes(out)


def _decode_def_bytes(def_bytes, defs):
    """
    Expand a definition's raw bytes into the pattern string using the
    already-decoded token map `defs`.
    """
    result = []
    i = 0
    while i < len(def_bytes):
        b = def_bytes[i]; i += 1
        if b >= TOKEN_BASE:
            result.append(defs[b])   # already resolved (lower-index token)
        else:
            result.append(chr(b))
    return "".join(result)


# ── core encoder --------------------------------------------------------------

def _encode_raw(text, patterns):
    """
    Greedy longest-match encoder.  When writing a pattern definition for the
    first time, compresses that definition using all already-defined tokens.
    """
    if not patterns:
        return text.encode("utf-8")

    token_of   = {pat: TOKEN_BASE + i for i, pat in enumerate(patterns)}
    # sort longest-first for the main scan
    by_length  = sorted(patterns, key=len, reverse=True)
    defined    = set()   # set of pattern strings already written to stream
    out        = bytearray()
    i = 0

    while i < len(text):
        for pat in by_length:
            if text.startswith(pat, i):
                tok = token_of[pat]
                if pat not in defined:
                    # Compress the definition using already-defined patterns
                    def_bytes = _encode_with_tokens(pat, token_of, defined)
                    out += bytes([tok, len(def_bytes)]) + def_bytes
                    defined.add(pat)
                else:
                    out.append(tok)
                i += len(pat)
                break
        else:
            out.append(ord(text[i]))
            i += 1

    return bytes(out)


# ── pattern detection ---------------------------------------------------------

def find_best_patterns(text):
    """
    Phase 1 - count all substrings, filter by rough savings estimate.
    Phase 2 - greedy validation: add a candidate only when it actually
              shrinks the real simulated encoded length.

    Patterns are sorted so shorter ones (likely sub-patterns) come first;
    this maximises definition compression for longer patterns.
    """
    counts = Counter()
    n = len(text)
    for length in range(MIN_PATTERN_LEN, MAX_PATTERN_LEN + 1):
        for i in range(n - length + 1):
            counts[text[i : i + length]] += 1

    # Phase 1: conservative filter - (F-1)*(L-1) > 2
    candidates = []
    for pat, freq in counts.items():
        L, F = len(pat), freq
        if F < 2:
            continue
        if (F - 1) * (L - 1) > 2:
            candidates.append((L, -F, pat))   # (length asc, freq desc)
    # Short, frequent patterns first — they become sub-patterns that compress
    # the definitions of longer patterns, enabling bottom-up hierarchy.
    candidates.sort()

    # Phase 2: greedy empirical validation
    selected  = []
    best_len  = len(text.encode("utf-8"))

    for _, _, pat in candidates[: MAX_TOKENS * 4]:
        trial     = selected + [pat]
        trial_len = len(_encode_raw(text, trial))
        if trial_len < best_len:
            selected.append(pat)
            best_len = trial_len
        if len(selected) >= MAX_TOKENS:
            break

    return selected


# ── public encode / decode ----------------------------------------------------

def encode(text, patterns):
    return _encode_raw(text, patterns)


def decode(data):
    """Decode a compressed byte stream back to the original text."""
    defs = {}
    out  = []
    i    = 0
    while i < len(data):
        b = data[i]; i += 1
        if b >= TOKEN_BASE:
            if b not in defs:
                length    = data[i];   i += 1
                def_bytes = data[i : i + length]; i += length
                # Recursively decode the definition through already-known tokens
                pat       = _decode_def_bytes(def_bytes, defs)
                defs[b]   = pat
            out.append(defs[b])
        else:
            out.append(chr(b))
    return "".join(out)


# ── compress / decompress -----------------------------------------------------

def compress(infile, outfile):
    text = open(infile, "r", encoding="utf-8").read()
    raw  = text.encode("utf-8")

    patterns = find_best_patterns(text)
    encoded  = encode(text, patterns)

    if len(encoded) + 1 >= len(raw) + 1:
        with open(outfile, "wb") as f:
            f.write(b"\x00" + raw)
        print(f"Input:  {len(raw)} bytes")
        print(f"Output: {len(raw)+1} bytes  (stored uncompressed - no gain)")
        return

    with open(outfile, "wb") as f:
        f.write(b"\x01" + encoded)

    saved = len(raw) - len(encoded)
    token_of = {pat: TOKEN_BASE + i for i, pat in enumerate(patterns)}
    print(f"Input:    {len(raw)} bytes")
    print(f"Output:   {len(encoded)+1} bytes  ({saved} bytes saved, "
          f"{saved/len(raw)*100:.1f}% reduction)")
    print(f"Patterns: {len(patterns)}")

    # show hierarchy: compute compressed def for each pattern
    defined = set()
    for i, pat in enumerate(patterns):
        def_bytes = _encode_with_tokens(pat, token_of, defined)
        defined.add(pat)
        raw_def   = pat.encode("utf-8")
        freq      = text.count(pat)
        if len(def_bytes) < len(raw_def):
            def_disp = f"{def_bytes.hex()} (compressed from {len(raw_def)}B)"
        else:
            def_disp = f"{def_bytes.hex()}"
        print(f"  token 0x{TOKEN_BASE+i:02X} -> {repr(pat):24s}  "
              f"x{freq}  def={def_disp}")


def decompress(infile, outfile):
    data = open(infile, "rb").read()
    if data[0] == 0:
        text = data[1:].decode("utf-8")
    else:
        text = decode(data[1:])
    open(outfile, "w", encoding="utf-8").write(text)
    print(f"Output: {len(text)} bytes")


# ── CLI ----------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p   = argparse.ArgumentParser(description="FCOM - Fayaz Compress")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compress");   c.add_argument("input"); c.add_argument("output")
    d = sub.add_parser("decompress"); d.add_argument("input"); d.add_argument("output")

    args = p.parse_args()
    (compress if args.cmd == "compress" else decompress)(args.input, args.output)