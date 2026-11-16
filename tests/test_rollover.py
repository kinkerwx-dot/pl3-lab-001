"""跨年期号测试（仅标准库，不联网）：python tests/test_rollover.py"""
import json, os, shutil, sys, tempfile
from datetime import datetime, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources, pl3_lab as L

R = lambda no, d, n=(1, 2, 3): {"issue_no": no, "date": d, "numbers": list(n)}
# 候选期号与 next_period
assert L.succ_candidates(R("26300", "2026-11-10")) == ["26301", "27001"]
assert L.succ_candidates(R("26352", "2026-12-31")) == ["27001"]                                  # 12-31 已开奖，只可能跨年
assert L.succ_candidates(R("26351", "2026-12-30")) == ["26352", "27001"]                         # 12-31 无开奖：两种都有可能
assert L.succ(R("26352", "2026-12-31")) == "27001" and L.succ(R("26044", "2026-02-13")) == "26045"
assert L.next_period([R("26352", "2026-12-31")], date(2027, 1, 1)) == "27001"
assert L.next_period([R("26351", "2026-12-30")], date(2026, 12, 31)) == "26352"
assert L.next_period([R("26351", "2026-12-30")], date(2027, 1, 1)) is None                       # 12-31 无开奖时不猜：需人工核实
assert L.next_period([R("26301", "2026-11-11")], date(2026, 11, 12)) == "26302"

SRC = L.BASE
def world(base_rows):
    d = tempfile.mkdtemp(); os.makedirs(d + "/data"); os.makedirs(d + "/records"); L.BASE = d
    json.dump([{"issue_no": r["issue_no"], "date": r["date"], "numbers": [str(x) for x in r["numbers"]]} for r in base_rows], open(d + "/data/pl3_history.json", "w"))
    return d
def feed(rows):
    S = {r["issue_no"]: {"date": r["date"], "numbers": r["numbers"]} for r in rows}
    sources.fetch_500 = lambda p: ({"period": p, **S[p]} if p in S else None); sources.fetch_ff = lambda *a, **k: S
    L.now_bj = lambda: datetime(2027, 1, 2, 15, 0, tzinfo=L.BJ)
def synced(): return [(r["issue_no"], r["agree"]) for r in L.read(L.BASE + "/records/results.jsonl") if r["type"] == "result"]
base = [R("26349", "2026-12-28"), R("26350", "2026-12-29"), R("26351", "2026-12-30")]

# 1 12-31 无开奖：同步必须直接找到 27001，不能卡在 26352
d = world(base); feed([R("27001", "2027-01-01", (4, 5, 6))]); L.sync(lambda s: None)
assert synced() == [("27001", "dual")], synced(); assert L.history_gap(L.load_history()) is None; shutil.rmtree(d)
# 2 12-31 有开奖：同一次同步依次找到 26352 与 27001
d = world(base); feed([R("26352", "2026-12-31"), R("27001", "2027-01-01")]); L.sync(lambda s: None)
assert synced() == [("26352", "dual"), ("27001", "dual")], synced(); shutil.rmtree(d)
# 3 期号与日期不衔接（同年期号却是次年日期）：停止且不写任何记录
d = world(base); feed([R("26352", "2027-01-01")])
try: L.sync(lambda s: None); raise SystemExit("应拒绝")
except SystemExit as e: assert "不衔接" in str(e)
assert not os.path.exists(d + "/records/results.jsonl") or L.read(d + "/records/results.jsonl") == []; shutil.rmtree(d)
# 4 次年 001 却是同年日期：同样拒绝
d = world(base); feed([R("27001", "2026-12-31")])
try: L.sync(lambda s: None); raise SystemExit("应拒绝")
except SystemExit as e: assert "不衔接" in str(e)
shutil.rmtree(d)

# 5 开奖日期必须严格向前推进（可隔很多天：停售假期、跨年）
assert L.history_gap([R("26300", "2026-11-10"), R("26301", "2026-11-10")]) is not None          # 同一天
assert L.history_gap([R("26300", "2026-11-10"), R("26301", "2026-11-09")]) is not None          # 倒退
assert L.history_gap([R("26299", "2026-11-09"), R("26300", "2026-11-10"), R("26301", "2026-11-11")]) is None
assert L.history_gap([R("26263", "2026-09-30"), R("26264", "2026-10-05")]) is None              # 国庆停售
assert L.history_gap([R("26044", "2026-02-13"), R("26045", "2026-02-24")]) is None              # 春节停售
assert L.history_gap([R("26352", "2026-12-31"), R("27001", "2027-01-01")]) is None              # 跨年
assert L.history_gap([R("26351", "2026-12-30"), R("27001", "2027-01-01")]) is None              # 12-31 无开奖的跨年
assert L.history_gap([R("26352", "2026-12-31"), R("27001", "2026-12-31")]) is not None          # 跨年却同一天
# 同步时：新一期的日期不晚于上一期 -> 停止且不写记录
for bad_date in ("2026-12-30", "2026-12-29"):
    d = world(base); feed([R("26352", bad_date)])
    try: L.sync(lambda s: None); raise SystemExit("应拒绝")
    except SystemExit as e: assert "不衔接" in str(e), e
    assert not os.path.exists(d + "/records/results.jsonl") or L.read(d + "/records/results.jsonl") == []; shutil.rmtree(d)

# 6 目标期必须紧接已确认历史末尾
d = world([R("26300", "2026-11-10")])
assert L.target_gap(L.load_history()[-1:], "26301", date(2026, 11, 11)) is None
for per, dt in (("26301", date(2026, 11, 10)), ("26301", date(2026, 11, 9)), ("26302", date(2026, 11, 12)), ("26300", date(2026, 11, 12)), ("27001", date(2026, 11, 12))):
    g = L.target_gap([R("26300", "2026-11-10")], per, dt); assert g and f"目标期号 {per}" in g, (per, dt, g)
assert L.target_gap([R("26263", "2026-09-30")], "26264", date(2026, 10, 5)) is None             # 停售假期之后
assert L.target_gap([R("26352", "2026-12-31")], "27001", date(2027, 1, 1)) is None              # 跨年
assert L.target_gap([R("26351", "2026-12-30")], "27001", date(2027, 1, 1)) is None              # 12-31 无开奖
assert L.target_gap([R("26351", "2026-12-30")], "26352", date(2027, 1, 1)) is not None          # 同年期号却是次年日期
L.append(d + "/records/results.jsonl", {"type": "result", "issue_no": "26301", "date": "2026-11-11", "numbers": [4, 5, 6], "sources": ["futurefortune"], "agree": "single", "retrieved_at": "x"})
g = L.target_gap([R("26300", "2026-11-10")], "26302", date(2026, 11, 12)); assert g and "26301" in g and "未经双渠道确认" in g   # 列出其间未确认的结果
shutil.rmtree(d)

# 7 依赖“今天”的测试夹具在任何日期都自洽（防止 2027 年起离线测试因日历而失败，进而拖垮每日流水线）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import evidence_fixtures as EF
for today in (date(2026, 11, 15), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2), date(2027, 3, 1), date(2028, 2, 29), date(2028, 12, 31), date(2029, 1, 1), date(2030, 7, 4)):
    rows = [{"issue_no": r["issue_no"], "date": r["date"], "numbers": [int(x) for x in r["numbers"]]} for r in EF.synth_rows(today)]
    nxt = L.next_period(rows, today)
    assert nxt and L.history_gap(rows) is None and L.target_gap(rows, nxt, today) is None, (today, nxt)
    assert L.target_gap(rows, f"{int(nxt) + 1}", today) is not None                                  # 跳期仍被拒绝
L.BASE = SRC; print("rollover: ALL PASSED")
