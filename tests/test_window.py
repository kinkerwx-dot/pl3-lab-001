"""历史连续性与滚动窗口缺口测试（仅标准库，不联网）：python tests/test_window.py"""
import contextlib, io, json, os, shutil, sys, tempfile
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import attest, sources, pl3_lab as L

R = lambda no, d: {"issue_no": no, "date": d, "numbers": [1, 2, 3]}
# history_gap：连续、跨年（含 12-31 无开奖）、缺口、错误的跨年
assert L.history_gap([R("26299", "2026-11-09"), R("26300", "2026-11-10"), R("26301", "2026-11-11")]) is None
assert L.history_gap([R("26351", "2026-12-30"), R("27001", "2027-01-01")]) is None
assert L.history_gap([R("26044", "2026-02-13"), R("26045", "2026-02-24")]) is None            # 停售假期：期号仍连续
g = L.history_gap([R("26300", "2026-11-10"), R("26306", "2026-11-16")]); assert g and "26300" in g and "26306" in g
assert L.history_gap([R("26300", "2026-11-10"), R("27001", "2026-11-11")]) is not None           # 同一年内不能跳到次年 001
assert L.history_gap([R("26300", "2026-11-10"), R("26300", "2026-11-11")]) is not None           # 重复期号
assert L.history_gap([R("26351", "2026-12-30"), R("26352", "2027-01-01")]) is not None           # 同年期号却是次年日期
assert L.history_gap([R("26351", "2026-12-30"), R("27001", "2026-12-31")]) is not None           # 次年 001 却是同年日期

# 端到端：S1 窗口已滑过 26301–26305，S2 有 -> 这些期只能是 single；模型输入出现缺口时必须拒绝预测，且不写任何预测
tmp = tempfile.mkdtemp(); os.makedirs(tmp + "/data"); os.makedirs(tmp + "/records"); shutil.copy(L.BASE + "/data/pl3_history.json", tmp + "/data/")
SRC_BASE = L.BASE; L.BASE = tmp
rows0 = L.load_history(); d = date.fromisoformat(rows0[-1]["date"]); S = {}
for k in range(1, 26):
    d += timedelta(days=1); S[f"{26300 + k}"] = {"date": d.isoformat(), "numbers": [(k * 5) % 10, (k * 3 + 1) % 10, (k * 7 + 2) % 10]}
win = {p: S[p] for p in list(S)[-20:]}
sources.fetch_s1_window = lambda: win
sources.fetch_500 = lambda p: ({"period": p, **win[p]} if p in win else None)
sources.fetch_ff = lambda *a, **k: {**{r["issue_no"]: {"date": r["date"], "numbers": r["numbers"]} for r in rows0}, **S}
today = date.fromisoformat(S["26325"]["date"]) + timedelta(days=1)
L.now_bj = lambda: datetime(today.year, today.month, today.day, 15, 0, tzinfo=L.BJ); attest.status = lambda b: (None, "未配置TSA")
def day():
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        try: L.daily(); return None, b.getvalue()
        except SystemExit as e: return str(e), b.getvalue()
msg = None
for _ in range(4):
    msg, _ = day()
    if msg: break
assert msg and "模型输入历史不连续" in msg and "26300" in msg and "26306" in msg and "记为缺失" in msg, msg
single = sorted(k for k, o in L.load_results().items() if not o["dual"]); assert single == ["26301", "26302", "26303", "26304", "26305"], single
assert L.read(tmp + "/records/predictions.jsonl") == []                                          # 拒绝时没有写入任何预测
# 伪造的 confirm：号码/日期相同、来源随意填写、没有证据 -> 不得解锁（审查复现过的漏洞）
for p in single:
    L.append(tmp + "/records/results.jsonl", {"type": "confirm", "issue_no": p, "date": S[p]["date"], "numbers": S[p]["numbers"], "sources": ["futurefortune", "官方公告人工核对"], "agree": "dual", "retrieved_at": "x"})
assert not any(L.load_results()[p]["dual"] for p in single) and L.history_gap(L.load_history()) is not None
msg, _ = day(); assert msg and "模型输入历史不连续" in msg and L.read(tmp + "/records/predictions.jsonl") == []
# 合法的人工恢复：仓库所有者先在策略里登记官方主机（可审计的版本变更），再逐期保存证据文件（含核对人）并追加带证据的 confirm
json.dump({"channels": {"gstc.org.cn": ["www.gstc.org.cn"], "futurefortune": ["raw.githubusercontent.com"], "official-manual": ["official.example.test"]}}, open(tmp + "/evidence_policy.json", "w"))
os.makedirs(tmp + "/records/evidence")
def manual_confirm(p, row, base=tmp):
    body = f"官方公告存档 第{p}期 开奖日期：{row['date']} 开奖号码：{' '.join(map(str, row['numbers']))}".encode(); fn = f"records/evidence/{p}-official.txt"; open(base + "/" + fn, "wb").write(body)
    L.append(base + "/records/results.jsonl", {"type": "confirm", "issue_no": p, "date": row["date"], "numbers": row["numbers"], "channel": "official-manual",
        "evidence": {"url": f"https://official.example.test/pl3/{p}", "sha256": __import__("hashlib").sha256(body).hexdigest(), "retrieved_at": "2026-12-06T10:00:00+08:00", "file": fn, "checker": "测试核对人"},
        "sources": ["futurefortune", "official-manual"], "agree": "dual", "retrieved_at": "2026-12-06T10:00:00+08:00"})
for p in single: manual_confirm(p, S[p])
assert all(L.load_results()[p]["dual"] for p in single) and L.history_gap(L.load_history()) is None
msg, out = day(); assert msg is None and "锁定 26326" in out, (msg, out)
p0 = L.read(tmp + "/records/predictions.jsonl")[0]; assert p0["period"] == "26326" and p0["data_range"].endswith("26325")

# ---- 历史末尾缺口：26301 只有单渠道时，人工指定 26302 也不能生成预测（审查复现的绕过）
shutil.rmtree(tmp); tmp = tempfile.mkdtemp(); os.makedirs(tmp + "/data"); os.makedirs(tmp + "/records"); shutil.copy(SRC_BASE + "/data/pl3_history.json", tmp + "/data/"); L.BASE = tmp
d1 = date.fromisoformat(rows0[-1]["date"]) + timedelta(days=1); one = {"26301": {"date": d1.isoformat(), "numbers": [4, 5, 6]}}
sources.fetch_500 = lambda p: None                                                              # S1 窗口里没有 26301：只能是单渠道
sources.fetch_ff = lambda *a, **k: {**{r["issue_no"]: {"date": r["date"], "numbers": r["numbers"]} for r in rows0}, **one}
today2 = d1 + timedelta(days=1); L.now_bj = lambda: datetime(today2.year, today2.month, today2.day, 15, 0, tzinfo=L.BJ)
def manual_day():
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        try: L.daily(period="26302", confirmed=True); return None, b.getvalue()
        except SystemExit as e: return str(e), b.getvalue()
msg, _ = manual_day()
assert msg and "目标期号 26302" in msg and "26301" in msg and "未经双渠道确认" in msg and "记为缺失" in msg, msg
assert not L.load_results()["26301"]["dual"] and L.read(tmp + "/records/predictions.jsonl") == []
json.dump({"channels": {"gstc.org.cn": ["www.gstc.org.cn"], "futurefortune": ["raw.githubusercontent.com"], "official-manual": ["official.example.test"]}}, open(tmp + "/evidence_policy.json", "w"))
os.makedirs(tmp + "/records/evidence"); manual_confirm("26301", one["26301"], base=tmp)         # 证据完整的恢复之后，同样的人工指定可以正常运行
msg, out = manual_day(); assert msg is None and "锁定 26302" in out, (msg, out)
q = L.read(tmp + "/records/predictions.jsonl")[0]; assert q["period"] == "26302" and q["data_range"].endswith("26301")
# 目标期号与历史末尾不衔接（例如手误跳期）同样拒绝
shutil.rmtree(tmp); tmp = tempfile.mkdtemp(); os.makedirs(tmp + "/data"); os.makedirs(tmp + "/records"); shutil.copy(SRC_BASE + "/data/pl3_history.json", tmp + "/data/"); L.BASE = tmp
sources.fetch_ff = lambda *a, **k: {r["issue_no"]: {"date": r["date"], "numbers": r["numbers"]} for r in rows0}
L.now_bj = lambda: datetime(2026, 11, 20, 15, 0, tzinfo=L.BJ)
b = io.StringIO()
with contextlib.redirect_stdout(b):
    try: L.daily(period="26305", confirmed=True); msg = None
    except SystemExit as e: msg = str(e)
assert msg and "目标期号 26305" in msg and L.read(tmp + "/records/predictions.jsonl") == []
shutil.rmtree(tmp); L.BASE = SRC_BASE; print("window: ALL PASSED")
