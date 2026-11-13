#!/usr/bin/env bash
# 下载 FreeTSA 证书并与 pins.json 的 SHA-256 比对；任何不符都会删除下载的文件并失败。
# 用法：bash tsa/download_and_check.sh   （成功后把 cacert.pem、tsa.crt 随仓库一起提交）
set -euo pipefail
cd "$(dirname "$0")"
curl -fsSL https://freetsa.org/files/cacert.pem -o cacert.pem
curl -fsSL https://freetsa.org/files/tsa.crt -o tsa.crt
python3 - <<'PY'
import hashlib, json, os, sys
pins = json.load(open("pins.json", encoding="utf-8")); bad = []
for f, exp in pins.items():
    if f.startswith("_"): continue
    got = hashlib.sha256(open(f, "rb").read()).hexdigest()
    print(f"{f}: {got} {'OK' if got == exp.lower() else 'MISMATCH'}")
    if got != exp.lower(): bad.append(f)
if bad:
    for f in bad: os.remove(f)
    sys.exit("哈希不符，已删除下载文件: " + ", ".join(bad))
print("证书哈希与钉扎一致")
PY
