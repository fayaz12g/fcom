## FCOM - Powerfull compression for `GCP` file data.

### Text, Audio, and Image
Some Example outputs below:
```bash
Text compressed: test.json → test.gcd
  Before       4,271 bytes
  After          892 bytes
  Saved        3,379 bytes  (79.1% reduction)

Image compressed: test.png → test.gci
  PNG     1469.1 KB
  AVIF      14.2 KB
  Saved    1454.9 KB  (99.0% reduction)

Audio compressed: test.mp3 → test.gcs
  MP3     6268.9 KB
  Opus    2027.6 KB
  Saved    4241.3 KB  (67.7% reduction)
```

Usage:

```bash
python3 fcom.py text       test.json     test.gcd
python3 fcom.py decompress test.gcd  test.json
python3 fcom.py image      test.png    test.gci
python3 fcom.py audio      test.mp3     test.gcs

fcom build ./my_assets ./dist --key "mysecret"
fcom build ./my_assets ./dist --key "mysecret" --name pack

fcom extract pack.gcp ./out --key "mysecret"
```

*Note: Images save as `AVIF`, and sound files save as `OPUS`, which is an `OGG` container type.*
*`GCD` files are compressed with Brotli and not directly readable unless decompressed into `JSON` data*