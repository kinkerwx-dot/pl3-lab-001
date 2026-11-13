"""第三方时间戳（RFC 3161）：对预测链尾哈希请求时间戳令牌，并用 openssl 验证签名与证书链。
未配置 TSA 或验证失败时，该批预测只能是观察记录（失败即关闭）。"""
import hashlib, json, os, re, subprocess, tempfile, urllib.request
from datetime import datetime, timezone


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def status(base):
    """返回 (cfg|None, 原因)。config.json 里 pinned=true 时，证书文件必须与 tsa/pins.json 的 SHA-256 完全一致，
    缺文件或不一致都返回 None（失败即关闭：只能产生观察记录）。"""
    p = os.path.join(base, "tsa", "config.json")
    if not os.path.exists(p): return None, "未配置TSA"
    c = dict(json.load(open(p, encoding="utf-8")))
    rel = [c["cafile"]] + ([c["untrusted"]] if c.get("untrusted") else [])
    absf = {f: os.path.join(base, f) for f in rel}
    miss = [f for f, a in absf.items() if not os.path.exists(a)]
    if miss: return None, "TSA证书文件缺失: " + ",".join(miss)
    if c.get("pinned"):
        pf = os.path.join(base, "tsa", "pins.json")
        pins = json.load(open(pf, encoding="utf-8")) if os.path.exists(pf) else {}
        for f, a in absf.items():
            exp = pins.get(os.path.basename(f))
            if not exp or _sha(a) != exp.lower(): return None, "TSA证书哈希与钉扎不符: " + os.path.basename(f)
    c["cafile"] = absf[c["cafile"]]
    if c.get("untrusted"): c["untrusted"] = absf[c["untrusted"]]
    return c, ""


def config(base):
    return status(base)[0]


def _ssl(*args):
    return subprocess.run(["openssl", *args], capture_output=True, timeout=60)


def stamp(url, digest_hex, timeout=30):
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "q.tsq")
        if _ssl("ts", "-query", "-digest", digest_hex, "-sha256", "-cert", "-out", q).returncode:
            raise RuntimeError("构造时间戳请求失败")
        req = urllib.request.Request(url, data=open(q, "rb").read(), headers={"Content-Type": "application/timestamp-query"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()


def _gentime(f):
    text = _ssl("ts", "-reply", "-in", f, "-text").stdout.decode("utf-8", "replace")
    m = re.search(r"Time stamp:\s+(\w{3})\s+(\d{1,2})\s+(\d\d):(\d\d):(\d\d)(?:\.\d+)?\s+(\d{4})\s+GMT", text)
    if not m: raise ValueError("无法解析时间戳时间")
    mon, day, hh, mm, ss, yy = m.groups()
    return datetime.strptime(f"{yy} {mon} {day} {hh}:{mm}:{ss}", "%Y %b %d %H:%M:%S").replace(tzinfo=timezone.utc)


def verify(tsr, digest_hex, cafile, untrusted=None):
    """验证令牌签名、证书链与摘要一致，且证书在【令牌签发时刻】有效（-attime）；返回 UTC 生成时间。失败抛 ValueError。
    注意：不检查吊销状态（OCSP/CRL）——这是已披露的局限。"""
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "r.tsr"); open(f, "wb").write(tsr)
        gt = _gentime(f)
        args = ["ts", "-verify", "-digest", digest_hex, "-in", f, "-CAfile", cafile, "-attime", str(int(gt.timestamp()))]
        if untrusted: args += ["-untrusted", untrusted]
        r = _ssl(*args)
        if r.returncode or b"Verification: OK" not in (r.stdout + r.stderr): raise ValueError("时间戳验证失败")
    return gt
