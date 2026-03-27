# FCOM — Powerful compression for `GCP` file data

Converts and compresses assets into GCP archives — a proprietary encrypted container format used for
GCP file data. PNG images become `.gci`, MP3 audio becomes `.gcs`, and JSON data becomes `.gcd`. All
files are bundled and encrypted into a single `.gcp` archive.

---

## Setup

```bash
python -m venv .venv
```

Activate the virtual environment:
- **PowerShell:** `.venv\Scripts\Activate.ps1`
- **Mac/Linux:** `source .venv/bin/activate`

Then install dependencies:

```bash
pip install -r requirements.txt
```

> **Note:** `ffmpeg` must also be on your PATH for audio conversion.
> - Windows: `choco install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
> - Mac: `brew install ffmpeg`
> - Linux: `sudo apt install ffmpeg`

---


## Encryption Key via .env (Recommended)

FCOM automatically reads the encryption key from a `.env` file if present.

Create a `.env` file in the project root:

```bash
FCOM_PKI=your_super_secret_key
```

Then you can run commands without specifying `--key`. If `.env` is not present, the `--key` argument
 is still supported

## Build a GCP archive

The `build` command recursively scans a folder for `*.png`, `*.mp3`, and `*.json` files (across all
subfolders), compresses each one, and packs them flat into an encrypted `.gcp` archive.

```bash
python fcom.py build <input_folder> <output_dir> --key "privatekey"
python fcom.py build <input_folder> <output_dir> --key "privatekey" --name "pack"
```

Example:
```bash
python fcom.py build .\test_files\pack\pop .\test_files\dist\"
python fcom.py build .\test_files\pack\schools .\test_files\dist\ --name "schools --key "fayazpp"
```
> The default name of the archive is the root folder name.

## Extract a GCP archive

```bash
python fcom.py extract pack.gcp .\out\ --key "privatekey"
```

Example:
```bash
python fcom.py extract .\test_files\dist\pop.gcp .\test_files\out --key "fayazpp"
python fcom.py extract .\test_files\dist\pop.gcp .\test_files\out
```

---

## Low-level helpers

Individual file conversion commands are also available:

```bash
python fcom.py text        input.json   output.gcd
python fcom.py decompress  input.gcd    output.json

python fcom.py image       input.png    output.gci
python fcom.py audio       input.mp3    output.gcs
```

---

## Example output

### JSON → GCD
```
Text compressed: test.json → test.gcd
    Before       4,271 bytes
    After          892 bytes
    Saved        3,379 bytes  (79.1% reduction)
```

### PNG → GCI
```
Image: test.png → test.gci
    PNG       1469.1 KB
    GCI/AVIF    14.2 KB
    Saved     1454.9 KB  (99.0% reduction)
```

### MP3 → GCS
```
Audio: test.mp3 → test.gcs
    MP3       6268.9 KB
    GCS/Opus  2027.6 KB
    Saved     4241.3 KB  (67.7% reduction)
```

---

## File formats

| Extension | Container | Codec   | Notes                                      |
|-----------|-----------|---------|--------------------------------------------|
| `.gci`    | AVIF      | AV1     | Lossily compressed image, quality 60       |
| `.gcs`    | OGG/Opus  | Opus    | Lossily compressed audio, 64 kbps          |
| `.gcd`    | —         | Brotli  | Losslessly compressed JSON, quality 11     |
| `.gcp`    | Proprietary | AES-256-GCM | Encrypted archive containing the above |

> `.gcd` files are Brotli-compressed and not directly readable — use `decompress` to restore the
> original JSON. `.gcp` files are opaque without the correct key; the internal structure is not
> publicly documented.