"""conn-test 验收逻辑测试（仅标准库，不联网）：python tests/test_conn.py
覆盖：三项全 PASS 才退出 0；TSA 缺失/哈希不符/请求失败、S1 或 S2 数据过旧、S1/S2 不一致、S1 不可达，一律非零退出。"""
import contextlib, io, os, sys
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import attest, sources, pl3_lab as L

rows = L.load_history(); last = rows[-1]; d_last = date.fromisoformat(last["date"])
NEW = {"issue_no": L.succ(last), "date": (d_last + timedelta(days=1)).isoformat(), "numbers": [5, 4, 4]}   # 本地快照之后的新一期（测试数据）
rd = lambda r: {"date": r["date"], "numbers": r["numbers"]}
def world(new=True):
    S = {r["issue_no"]: rd(r) for r in rows}
    if new: S[NEW["issue_no"]] = rd(NEW)
    return S
fake_tsa_ok = (lambda base: ({"url": "u", "cafile": "c", "untrusted": None}, ""))
def run(s1, s2, tsa=fake_tsa_ok, today=None, stamp_ok=True, s1_raises=False, max_age=2):
    today = today or date.fromisoformat(NEW["date"]) + timedelta(days=1)       # 最新一期的“次日”15:00
    L.now_bj = lambda: datetime(today.year, today.month, today.day, 15, 0, tzinfo=L.BJ)
    def f500(p):
        if s1_raises: raise RuntimeError("GET 失败 x: URLError")
        return ({"period": p, **s1[p]} if p in s1 else None)
    sources.fetch_500 = f500; sources.fetch_ff = lambda *a, **k: s2 if s2 is not None else (_ for _ in ()).throw(RuntimeError("S2 down"))
    attest.status = tsa
    attest.stamp = (lambda url, d: b"tsr") if stamp_ok else (lambda url, d: (_ for _ in ()).throw(OSError("net")))
    attest.verify = lambda tsr, d, ca, un=None: datetime(today.year, today.month, today.day, 7, 0, tzinfo=L.BJ)
    b = io.StringIO(); code = None
    with contextlib.redirect_stdout(b):
        try: L.conn_test(max_age)
        except SystemExit as e: code = e.code
    return code, b.getvalue()

code, out = run(world(), world())
assert code == 0 and out.count("PASS") >= 3 and "三项全部 PASS" in out and f"本地快照最新: {last['issue_no']}" in out, out
assert f"S1: PASS — 最新可验证 {NEW['issue_no']}" in out and f"S2: PASS — {len(rows) + 1} 期，最新 {NEW['issue_no']}" in out, out   # 分别报告三处最新期号

# 审计复现的缺陷：TSA 证书缺失 -> 必须非零
code, out = run(world(), world(), tsa=lambda base: (None, "TSA证书文件缺失: tsa/cacert.pem,tsa/tsa.crt"))
assert code == 1 and "TSA: FAIL" in out and "S1: PASS" in out and "S2: PASS" in out and "未通过" in out, out
code, out = run(world(), world(), tsa=lambda base: (None, "TSA证书哈希与钉扎不符: tsa.crt")); assert code == 1 and "TSA: FAIL" in out
code, out = run(world(), world(), tsa=lambda base: (None, "未配置TSA")); assert code == 1
code, out = run(world(), world(), stamp_ok=False); assert code == 1 and "TSA: FAIL" in out and "请求或验签失败" in out

# 新鲜度：数据停在旧期（本地快照那一期），而今天已是几天之后
stale_today = d_last + timedelta(days=5)
code, out = run(world(new=False), world(new=False), today=stale_today)
assert code == 1 and "S1: FAIL" in out and "S2: FAIL" in out and "数据过旧" in out, out
# S1 落后但仍在阈值内（距今=2天）-> 通过；超过阈值（距今=3天）-> 仅 S1 FAIL，S2 仍 PASS
code, out = run(world(new=False), world(), today=d_last + timedelta(days=2)); assert code == 0 and "S1: PASS" in out and "S2: PASS" in out, out
code, out = run(world(new=False), world(), today=d_last + timedelta(days=3)); assert code == 1 and "S1: FAIL" in out and "S2: PASS" in out, out
# 单独 S2 过旧
code, out = run(world(), world(new=False), today=d_last + timedelta(days=3)); assert code == 1 and "S2: FAIL" in out and "S1: PASS" in out and "数据过旧" in out, out

# 两源对新期读数不一致 / S1 不可达 / S2 不可达 / 近30期被篡改
bad = world(); bad[NEW["issue_no"]] = {"date": NEW["date"], "numbers": [9, 9, 9]}
code, out = run(world(), bad); assert code == 1 and "S2: FAIL" in out and "与S1在新期上不一致" in out, out
code, out = run(world(), world(), s1_raises=True); assert code == 1 and "S1: FAIL" in out
code, out = run(world(), None); assert code == 1 and "S2: FAIL" in out and "无法读取" in out
tam = world(); tam[rows[-3]["issue_no"]] = {"date": rows[-3]["date"], "numbers": [0, 0, 0]}
code, out = run(world(), tam); assert code == 1 and "S2: FAIL" in out and "不符" in out
print("conn-test: ALL PASSED")
