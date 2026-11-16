"""conn-test 验收逻辑测试（仅标准库，不联网）：python tests/test_conn.py
S1 现在是约 20 期的滚动窗口：测试覆盖窗口滑动后仍然正确通过、各种失败仍然失败（不放水）。"""
import contextlib, io, os, sys
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import attest, sources, pl3_lab as L

rows = L.load_history(); last = rows[-1]; d_last = date.fromisoformat(last["date"])
rd = lambda r: {"date": r["date"], "numbers": list(r["numbers"])}
LOCAL = {r["issue_no"]: rd(r) for r in rows}

def news(k):                                           # 本地快照之后的 k 个合成开奖期（测试数据）
    out, d, no = {}, d_last, last["issue_no"]
    for i in range(1, k + 1):
        d += timedelta(days=1); no = f"{int(no) + 1}"; out[no] = {"date": d.isoformat(), "numbers": [i % 10, (i * 3) % 10, (i * 7) % 10]}
    return out
def tail(S, k=20): ks = list(S)[-k:]; return {p: S[p] for p in ks}
def universe(k): S = dict(LOCAL); S.update(news(k)); return S

ok_tsa = lambda base: ({"url": "u", "cafile": "c", "untrusted": None}, "")
def run(win, s2, tsa=ok_tsa, today=None, stamp_ok=True, s1_raises=False, max_age=2):
    newest = max((v["date"] for v in (win or {"x": {"date": last["date"]}}).values()))
    today = today or date.fromisoformat(newest) + timedelta(days=1)
    L.now_bj = lambda: datetime(today.year, today.month, today.day, 15, 0, tzinfo=L.BJ)
    sources.fetch_s1_window = (lambda: (_ for _ in ()).throw(RuntimeError("S1 HTTP 503"))) if s1_raises else (lambda: win)
    sources.fetch_ff = (lambda *a, **k: s2) if s2 is not None else (lambda *a, **k: (_ for _ in ()).throw(RuntimeError("S2 down")))
    attest.status = tsa
    attest.stamp = (lambda url, d: b"tsr") if stamp_ok else (lambda url, d: (_ for _ in ()).throw(OSError("net")))
    attest.verify = lambda tsr, d, ca, un=None: datetime(today.year, today.month, today.day, 7, 0, tzinfo=L.BJ)
    b = io.StringIO(); code = None
    with contextlib.redirect_stdout(b):
        try: L.conn_test(max_age)
        except SystemExit as e: code = e.code
    return code, b.getvalue()

# 1 正常：窗口含本地尾部 + 3 个新期
U = universe(3); code, out = run(tail(U), U)
assert code == 0 and "三项全部 PASS" in out and f"最新 {last['issue_no']}" not in out.split("S1:")[1].split("\n")[0] and "与本地历史重叠 17 期" in out and "逐项对比 20 期" in out, out
# 2 【窗口滑动】本地快照最近 5 期早已滑出窗口，S1/S2 都新鲜且一致：必须通过（此前会误判失败）
U = universe(25); code, out = run(tail(U), U)
assert code == 0 and "与本地历史重叠 0 期" in out and "S1: PASS" in out and "S2: PASS" in out, out
# 3 TSA 各类失败 -> 1
for tsa in (lambda b: (None, "TSA证书文件缺失: tsa/cacert.pem"), lambda b: (None, "TSA证书哈希与钉扎不符: tsa.crt"), lambda b: (None, "未配置TSA")):
    U = universe(3); code, out = run(tail(U), U, tsa=tsa); assert code == 1 and "TSA: FAIL" in out and "S1: PASS" in out and "S2: PASS" in out, out
U = universe(3); code, out = run(tail(U), U, stamp_ok=False); assert code == 1 and "请求或验签失败" in out
# 4 新鲜度：S1 过旧 / S2 过旧 / 阈值边界
U = universe(3); W = tail(U); newest = date.fromisoformat(max(v["date"] for v in W.values()))
code, out = run(W, U, today=newest + timedelta(days=2)); assert code == 0, out                      # 距今 2 天，等于阈值，通过
code, out = run(W, U, today=newest + timedelta(days=3)); assert code == 1 and "S1: FAIL" in out and "S2: FAIL" in out and "数据过旧" in out, out
U2 = {k: v for k, v in U.items() if k != list(news(3))[-1]}                                           # S2 落后 1 期
code, out = run(W, U2, today=newest + timedelta(days=1)); assert code == 0, out                      # S1 领先 1 期、S2 日期距今=阈值：通过；领先的那行不参与对比
code, out = run(W, U2, today=newest + timedelta(days=2)); assert code == 1 and "S2: FAIL" in out and "S1: PASS" in out and "数据过旧" in out, out
# 5 一致性：S1 与 S2 在【中间期】不一致 / S2 缺 S1 窗口内的期 / S1 与本地在重叠期不一致 / 窗口不连续 / 可对比期数不足
U = universe(3); W = tail(U); mid = list(W)[5]
bad2 = dict(U); bad2[mid] = {"date": W[mid]["date"], "numbers": [9, 9, 9]}
code, out = run(W, bad2); assert code == 1 and "S2: FAIL" in out and "与S1在重叠期上不一致" in out and mid in out, out
miss2 = {k: v for k, v in U.items() if k != mid}
code, out = run(W, miss2); assert code == 1 and "S2: FAIL" in out and "S2 缺少 S1 窗口内的期号" in out, out
badw = dict(W); loc_p = [p for p in W if p in LOCAL][0]; badw[loc_p] = {"date": W[loc_p]["date"], "numbers": [8, 8, 8]}
code, out = run(badw, U); assert code == 1 and "S1: FAIL" in out and "与本地历史在重叠期上不一致" in out, out
holes = {k: v for k, v in W.items() if k != list(W)[7]}
code, out = run(holes, U); assert code == 1 and "S1: FAIL" in out and "窗口期号不连续" in out, out
code, out = run(tail(U, 8), U); assert code == 1 and "S2: FAIL" in out and "可对比期数不足" in out, out
# 6 不可达：S1 不可达 -> 仅 S1 FAIL（不叠加 S2 交叉核对失败）；S2 不可达 -> S2 FAIL
code, out = run({}, U, s1_raises=True); assert code == 1 and "S1: FAIL" in out and "S2: PASS" in out and "无法读取或解析" in out, out
code, out = run(tail(U), None); assert code == 1 and "S2: FAIL" in out and "无法读取" in out and "S1: PASS" in out, out
print("conn-test: ALL PASSED")
