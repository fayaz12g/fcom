Usage:

```bash
python3 fcom.py text       test.json     test.gcd
python3 fcom.py decompress test.gcd  test.json
python3 fcom.py image      test.png    test.gci
python3 fcom.py audio      test.mp3     test.gcs
```

*Note: Images save as `AVIF`, and sound files save as `OPUS`, which is an `OGG` container type.*
*`GCD` files are compressed with Brotli and not directly readable unless decompressed into `JSON` data*