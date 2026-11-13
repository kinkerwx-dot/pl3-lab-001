"""核心离线测试（仅标准库）：python tests/test_core.py"""
import json, os, shutil, sys, tempfile
from datetime import datetime, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import models, sources, stats_exact as SE, pl3_lab as L

SRC = L.BASE
full = json.load(open(os.path.join(SRC, "data", "pl3_history.json"), encoding="utf-8"))
X = [[int(x) for x in f["numbers"]] for f in full]

# 解析器
txt = "排列3 第 26294期 开奖日期：2026年11月4日 兑奖截止日期：2027年1月2日 开奖号码： 3 2 9 号码类型：组六"
assert sources.parse_500("26294", txt.encode()) == {"period": "26294", "date": "2026-11-04", "numbers": [3, 2, 9]}
assert sources.parse_500("26294", txt.encode("gbk"))["numbers"] == [3, 2, 9]
assert sources.parse_500("26295", txt.encode()) is None and sources.parse_500("26294", b"<li>3</li><li>2</li>") is None
# 期号推算
r = lambda no, d, n=(1, 2, 3): {"issue_no": no, "date": d, "numbers": list(n)}
assert L.next_period([r("26301", "2026-11-11")], date(2026, 11, 12)) == "26302"
assert L.next_period([r("26352", "2026-12-31")], date(2027, 1, 1)) == "27001"
assert L.next_period([r("26263", "2026-09-30")], date(2026, 10, 5)) is None
# 模型：冻结值与性质；精确二项与 scipy 对照（若可用）
assert models.baseline_pick("26302") == [0, 8, 9] and models.baseline_pick("26303") == [4, 5, 9]
for m in ("hot", "cold"):
    P = models.digit_probs(m, X[:-1]); models.check_probs(P); pk = models.pick_g6(P); assert pk == sorted(set(pk))
try:
    models.check_probs([[0.1] * 10, [0.1] * 10, [0.1] * 9 + [0.2]]); raise SystemExit("应拒绝未归一化")
except ValueError: pass
assert abs(SE.binom_sf(15, 1500, 0.006) - 0.0410) < 5e-4 and abs(SE.binom_sf(16, 1500, 2 / 173) - 0.0) < 1 and SE.binom_sf(0, 10, .1) == 1
try:
    from scipy.stats import binom
    for n, k, p in ((1500, 15, .006), (2200, 20, .006), (2200, 30, 2 / 173)):
        assert abs(SE.binom_sf(k, n, p) - binom.sf(k - 1, n, p)) < 1e-10
except ImportError: pass
adj, rej = SE.holm([0.01, 0.03]); assert adj == [0.02, 0.03] and rej == [True, True]

# 端到端（假数据源）
tmp = tempfile.mkdtemp(); os.makedirs(tmp + "/data"); os.makedirs(tmp + "/records")
json.dump(full[:-3], open(tmp + "/data/pl3_history.json", "w"), ensure_ascii=False)
L.BASE = tmp
ff = sources.parse_ff(json.dumps(full[-3:]).encode())
d0 = date.fromisoformat(full[-1]["date"]); T = lambda h, m, extra=0: datetime(d0.year, d0.month, d0.day + extra, h, m, tzinfo=L.BJ)
S1 = {"on": True}
sources.fetch_ff = lambda *a, **k: ff
sources.fetch_500 = lambda p: ({"period": p, **ff[p]} if S1["on"] and p in ff else None)
L.now_bj = lambda: T(15, 0)
L.sync(lambda s: None)
res = L.load_results(); assert len(res) == 3 and all(o["dual"] for o in res.values())
rows = L.load_history(); nxt = L.succ(rows[-1])
# 单源结果：不进入历史/统计，直到第二来源确认
S1["on"] = False; ff2 = dict(ff); ff = {k: v for k, v in ff2.items() if k != full[-1]["issue_no"]}
shutil.rmtree(tmp + "/records"); os.makedirs(tmp + "/records"); json.dump(full[:-1], open(tmp + "/data/pl3_history.json", "w"), ensure_ascii=False)
sources.fetch_ff = lambda *a, **k: ff
ff_only = {full[-1]["issue_no"]: {"date": full[-1]["date"], "numbers": [int(x) for x in full[-1]["numbers"]]}}
sources.fetch_ff = lambda *a, **k: ff_only
L.sync(lambda s: None); o = L.load_results()[full[-1]["issue_no"]]; assert o["rec"]["agree"] == "single" and not o["dual"]
assert L.load_history()[-1]["issue_no"] == full[-2]["issue_no"] and L.next_period(L.load_history(), d0 + __import__("datetime").timedelta(days=1)) is None
S1["on"] = True; sources.fetch_500 = lambda p: {"period": p, **ff_only[p]} if p in ff_only else None
L.sync(lambda s: None); assert L.load_results()[full[-1]["issue_no"]]["dual"] and L.load_history()[-1]["issue_no"] == full[-1]["issue_no"]
# 冲突：两阶段，任何记录都不得写入
before = open(tmp + "/records/results.jsonl").read()
nx = L.succ(L.load_history()[-1])
sources.fetch_ff = lambda *a, **k: {nx: {"date": "2030-01-01", "numbers": [1, 2, 3]}}
sources.fetch_500 = lambda q: {"period": q, "date": "2030-01-01", "numbers": [3, 2, 1]}
try: L.sync(lambda s: None); raise SystemExit("冲突未拦截")
except SystemExit as e: assert "冲突" in str(e) and "未拦截" not in str(e)
assert open(tmp + "/records/results.jsonl").read() == before
# 锁定：无 evidence_class；概率精确存储；重复/已开奖/截止拒绝；篡改与尾部截断
rows = L.load_history(); nxt = L.succ(rows[-1]); L.now_bj = lambda: T(15, 0, 1)
tip = L.predict(nxt, rows, "t"); recs = L.read(tmp + "/records/predictions.jsonl")
assert len(recs) == 3 and all("evidence_class" not in x and "formal" not in json.dumps(x) for x in recs)
assert recs[1]["probs"] == models.digit_probs("hot", [r["numbers"] for r in rows]) and tip == recs[-1]["hash"]
assert L.predict(nxt, rows, "t") is None
for fn, why in ((lambda: L.predict(full[-1]["issue_no"], rows, ""), "已开奖"),):
    try: fn(); raise SystemExit("应拒绝: " + why)
    except SystemExit as e: assert "拒绝" in str(e)
L.now_bj = lambda: T(20, 31, 1)
try: L.predict("99999", rows, ""); raise SystemExit("应拒绝: 截止后")
except SystemExit as e: assert "缺失" in str(e)
sources.fetch_ff = lambda *a, **k: {}
L.verify()
L.append(tmp + "/records/attestations.jsonl", {"period": nxt, "tip": "f" * 64, "tsr_b64": ""})
try: L.verify(); raise SystemExit("截断未发现")
except SystemExit as e: assert "截断" in str(e)
os.remove(tmp + "/records/attestations.jsonl")
p = tmp + "/records/predictions.jsonl"; s = open(p, encoding="utf-8").read().replace('"pick": [', '"pick": [9, ', 1); open(p, "w", encoding="utf-8").write(s)
try: L.verify(); raise SystemExit("篡改未发现")
except SystemExit as e: assert "校验失败" in str(e)
shutil.rmtree(tmp)

# 确证分析：未达 N* 不写任何东西；达到后只执行一次并持久化
tmp2 = tempfile.mkdtemp(); os.makedirs(tmp2 + "/records"); L.BASE = tmp2
import io, contextlib
def cap(fn, *a):
    b = io.StringIO()
    with contextlib.redirect_stdout(b): fn(*a)
    return b.getvalue()
L.N_STAR = 5
H = lambda L_, base=26400: [(f"{base+i}", h) for i, h in enumerate(L_)]
exists = lambda: os.path.exists(tmp2 + "/records/confirmatory.jsonl")
out = cap(L.confirmatory, {"hot-v1": H([1, 1, 1, 0, 0])}); assert "尚未冻结" in out and not exists()
json.dump({"first_eligible_period": "26302"}, open(tmp2 + "/records/freeze.json", "w"))       # 冻结起点必须晚于 26302
out = cap(L.confirmatory, {"hot-v1": H([1] * 9)}); assert "必须晚于 26302" in out and not exists()
json.dump({"first_eligible_period": "26401"}, open(tmp2 + "/records/freeze.json", "w"))
out = cap(L.confirmatory, {"hot-v1": H([0, 0, 1])}); assert "未达 N*" in out and not exists()
# 26302 及更早、以及冻结起点之前的期号不计入；cold 不参与推断
hist = H([1, 1, 1, 0, 0, 0]) + [("26302", 1), ("26100", 1)]
out = cap(L.confirmatory, {"hot-v1": hist, "cold-v1": H([1] * 9)}); rec = L.read(tmp2 + "/records/confirmatory.jsonl")
assert len(rec) == 1 and rec[0]["model"] == "hot-v1" and rec[0]["hits"] == 2 and rec[0]["n"] == 5 and "cold-v1" not in json.dumps(rec[0]) and "确证分析结果" in out
out2 = cap(L.confirmatory, {"hot-v1": H([1] * 6)}); assert len(L.read(tmp2 + "/records/confirmatory.jsonl")) == 1 and "只做一次" in out2
# 冻结常量：N*、临界值与功效（与独立复算一致）
L.N_STAR = 1662
k = 0
while SE.binom_sf(k, 1662, L.P0) > L.ALPHA: k += 1
assert k == 16 and abs(SE.binom_sf(16, 1662, 2 / 173) - 0.8003) < 5e-4
shutil.rmtree(tmp2); print("core: confirmatory ok")
print("core: ALL PASSED")
