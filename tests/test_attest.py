"""时间戳与审计测试：用【本地自建】测试 TSA（不是真实第三方）演练验证逻辑。需要 openssl。python tests/test_attest.py"""
import base64, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import attest, models, sources, pl3_lab as L

def ssl(*a, cwd):
    r = subprocess.run(["openssl", *a], cwd=cwd, capture_output=True)
    assert r.returncode == 0, r.stderr.decode()
    return r

def make_tsa(d):
    open(f"{d}/ext.cnf", "w").write("basicConstraints=CA:FALSE\nextendedKeyUsage=critical,timeStamping\n")
    open(f"{d}/ts.cnf", "w").write("[tsa]\ndefault_tsa=t\n[t]\ndir=.\nserial=./serial\ncrypto_device=builtin\nsigner_cert=./tsa.crt\ncerts=./tsa.crt\nsigner_key=./tsa.key\nsigner_digest=sha256\ndefault_policy=1.2.3.4.1\ndigests=sha256\naccuracy=secs:1\nordering=yes\ntsa_name=yes\ness_cert_id_alg=sha256\n")
    open(f"{d}/serial", "w").write("01\n")
    ssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem", "-subj", "/CN=TestCA", "-days", "2", cwd=d)
    ssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "tsa.key", "-out", "tsa.csr", "-subj", "/CN=TestTSA", cwd=d)
    ssl("x509", "-req", "-in", "tsa.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial", "-out", "tsa.crt", "-days", "2", "-extfile", "ext.cnf", cwd=d)

def local_stamp(d, digest):
    ssl("ts", "-query", "-digest", digest, "-sha256", "-cert", "-out", "q.tsq", cwd=d)
    ssl("ts", "-reply", "-queryfile", "q.tsq", "-config", "ts.cnf", "-out", "r.tsr", cwd=d)
    return open(f"{d}/r.tsr", "rb").read()

d = tempfile.mkdtemp(); make_tsa(d)
dig = "ab" * 32; tsr = local_stamp(d, dig)
gt = attest.verify(tsr, dig, f"{d}/ca.pem"); assert abs((datetime.now(gt.tzinfo) - gt).total_seconds()) < 120
for bad, why in ((lambda: attest.verify(tsr, "cd" * 32, f"{d}/ca.pem"), "摘要不符"),
                 (lambda: attest.verify(tsr[:-5] + b"xxxxx", dig, f"{d}/ca.pem"), "令牌被改"),
                 (lambda: attest.verify(tsr, dig, f"{d}/tsa.crt"), "不信任的CA")):
    try: bad(); raise SystemExit("应失败: " + why)
    except ValueError: pass

# 审计分类：TSA 令牌早于/晚于截止、缺失、无配置、单源
full = json.load(open(os.path.join(L.BASE, "data", "pl3_history.json"), encoding="utf-8"))
tmp = tempfile.mkdtemp(); os.makedirs(tmp + "/data"); os.makedirs(tmp + "/records"); os.makedirs(tmp + "/tsa")
json.dump(full[:-2], open(tmp + "/data/pl3_history.json", "w"), ensure_ascii=False)
L.BASE = tmp
ff = sources.parse_ff(json.dumps(full[-2:]).encode()); sources.fetch_ff = lambda *a, **k: ff; sources.fetch_500 = lambda p: ({"period": p, **ff[p]} if p in ff else None)
d0 = date.fromisoformat(full[-1]["date"]); L.now_bj = lambda: datetime(d0.year, d0.month, d0.day, 15, 0, tzinfo=L.BJ)
L.sync(lambda s: None); rows = L.load_history(); nxt = L.succ(rows[-1])
L.now_bj = lambda: datetime(d0.year, d0.month, d0.day, 15, 0, tzinfo=L.BJ) + timedelta(days=1)
tip = L.predict(nxt, rows, "t"); today = L.now_bj().date()
# 假设开奖日=明天，写入对应的双源结果（同一天 + 数字取真实数据形态）
rec = {"type": "result", "issue_no": nxt, "date": today.isoformat(), "numbers": [3, 2, 9], "sources": ["500.com", "futurefortune"], "agree": "dual", "retrieved_at": "x"}
L.append(tmp + "/records/results.jsonl", rec)
def classify(): return L.audit()[0][nxt]
assert classify() == ("observation", "未配置TSA")
shutil.copy(f"{d}/ca.pem", tmp + "/tsa/ca.pem"); json.dump({"url": "local-test", "cafile": "tsa/ca.pem"}, open(tmp + "/tsa/config.json", "w"))
assert classify() == ("observation", "无第三方时间戳")
tsr = local_stamp(d, tip)
L.append(tmp + "/records/attestations.jsonl", {"period": nxt, "tip": tip, "tsa_url": "local-test", "tsr_b64": base64.b64encode(tsr).decode(), "retrieved_at": "x"})
tsa_day = attest.verify(tsr, tip, tmp + "/tsa/ca.pem").astimezone(L.BJ)
today_real = tsa_day.date(); rec2 = dict(rec, date=today_real.isoformat())
# 令牌日期必须与预期开奖日一致：这里预期日是“假设的明天”，与令牌真实日期不符 -> 观察
assert classify()[0] == "observation"
# 构造一致情形：把记录与结果日期改成令牌日期，截止时间分别设为令牌之后/之前
shutil.rmtree(tmp + "/records"); os.makedirs(tmp + "/records")
L.now_bj = lambda: datetime.combine(today_real, datetime.min.time(), tzinfo=L.BJ)  # 午夜，早于任何截止
sources.fetch_ff = lambda *a, **k: ff; L.sync(lambda s: None)
rows = L.load_history(); nxt = L.succ(rows[-1])
tip = L.predict(nxt, rows, "t"); tsr = local_stamp(d, tip)
L.append(tmp + "/records/results.jsonl", dict(rec, issue_no=nxt, date=today_real.isoformat()))
L.append(tmp + "/records/attestations.jsonl", {"period": nxt, "tip": tip, "tsa_url": "local-test", "tsr_b64": base64.b64encode(tsr).decode(), "retrieved_at": "x"})
tg = attest.verify(tsr, tip, tmp + "/tsa/ca.pem").astimezone(L.BJ)
L.cutoff_dt = lambda dd: tg + timedelta(hours=1); assert classify() == ("formal", "")
L.cutoff_dt = lambda dd: tg - timedelta(hours=1); assert classify() == ("observation", "时间戳晚于内部截止")
L.cutoff_dt = lambda dd: tg + timedelta(hours=1)
import io, contextlib
b = io.StringIO()
with contextlib.redirect_stdout(b): L.stats()
o = b.getvalue(); assert "[formal]" in o and "p=" not in o and "不含 p 值" in o and "尚未冻结" in o, o
# 单源开奖结果即使时间戳完美也只能是观察
L.cutoff_dt = lambda dd: tg + timedelta(hours=1)
lines = [json.loads(l) for l in open(tmp + "/records/results.jsonl")]; lines[-1].update(agree="single", sources=["500.com"])
open(tmp + "/records/results.jsonl", "w").write("\n".join(json.dumps(x) for x in lines) + "\n")
assert classify() == ("observation", "开奖结果未双源确认")
# TSA 证书哈希钉扎：缺文件/哈希不符 -> 失败即关闭；匹配 -> 可用
import hashlib
t3 = tempfile.mkdtemp(); os.makedirs(t3 + "/tsa"); open(t3 + "/tsa/ca.pem", "wb").write(b"CA"); open(t3 + "/tsa/tsa.crt", "wb").write(b"CRT")
cfgj = {"url": "u", "cafile": "tsa/ca.pem", "untrusted": "tsa/tsa.crt", "pinned": True}; json.dump(cfgj, open(t3 + "/tsa/config.json", "w"))
assert attest.status(t3)[0] is None and "钉扎" in attest.status(t3)[1]                       # 无 pins.json
good = {"ca.pem": hashlib.sha256(b"CA").hexdigest(), "tsa.crt": hashlib.sha256(b"CRT").hexdigest(), "_source": "t"}
json.dump(good, open(t3 + "/tsa/pins.json", "w")); c, w = attest.status(t3); assert c and c["cafile"].endswith("ca.pem") and w == ""
json.dump(dict(good, **{"tsa.crt": "0" * 64}), open(t3 + "/tsa/pins.json", "w")); c, w = attest.status(t3); assert c is None and "tsa.crt" in w
os.remove(t3 + "/tsa/tsa.crt"); assert "缺失" in attest.status(t3)[1]
shutil.rmtree(t3)
shutil.rmtree(tmp); shutil.rmtree(d); print("attest/audit: ALL PASSED（使用本地测试 TSA，非真实第三方）")
