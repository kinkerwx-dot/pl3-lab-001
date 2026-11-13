#!/usr/bin/env python3
"""PL3-LAB-001 排列三零资金模拟 v2（仅标准库 + openssl）。真实投注金额始终为 0，所有“盈亏”均为模拟。

  conn-test | daily [--period 26302 --official-confirmed] | verify | audit | stats
v2 要点：生成器不再给任何预测贴“正式”标签；是否正式只由事后审计依据【第三方时间戳 + 双源开奖】判定。
"""
import base64, hashlib, json, os, sys
from datetime import datetime, timezone, timedelta, date
import attest, models, sources
from stats_exact import binom_sf

BASE = os.path.dirname(os.path.abspath(__file__))
COST, PRIZE, P0 = 2, 173, 6 / 1000       # 组选六：2 元/注；单注奖金 173 元（需持续核验官方规则）
N_STAR = 1662                            # 确证分析所需正式期数：hot-v1 单一主检验，α=0.05 单侧精确二项，最少 16 次命中，对 p1=2/173 功效 80.03%
ALPHA = 0.05
EXCLUDE_THROUGH = "26302"                # 26302 及更早的期号永不计入确证样本
ROLE = {"hot-v1": "确证性挑战者", "cold-v1": "探索性对照", "random-baseline-v1": "随机基线"}
CUTOFF_HM = (20, 30)                     # 实验内部锁定截止（北京时间），非官方停售时间，未经官方核验
BJ = timezone(timedelta(hours=8))
DATA_SRC = "futurefortune(MIT)快照 + records/results.jsonl 中双源确认的增量"


def path(*p): return os.path.join(BASE, *p)
def now_bj(): return datetime.now(BJ)
def cutoff_dt(d): return datetime(d.year, d.month, d.day, *CUTOFF_HM, tzinfo=BJ)
def sha(d): return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def append(p, rec):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def base_rows():
    b = json.load(open(path("data", "pl3_history.json"), encoding="utf-8"))
    return [{"issue_no": r["issue_no"], "date": r["date"], "numbers": [int(x) for x in r["numbers"]]} for r in b]


def load_results():
    """issue_no -> {"rec","dual"}；单源结果只有在后续 confirm 记录（第二来源一致）出现后才算 dual。"""
    out = {}
    for r in read(path("records", "results.jsonl")):
        if r.get("type") == "result": out[r["issue_no"]] = {"rec": r, "dual": r["agree"] == "dual"}
        elif r.get("type") == "confirm" and r["issue_no"] in out:
            o = out[r["issue_no"]]["rec"]
            if r["numbers"] == o["numbers"] and r["date"] == o["date"]: out[r["issue_no"]]["dual"] = True
    return out


def load_history():
    """模型输入与统计只使用【双源确认】的结果。"""
    rows = base_rows() + [o["rec"] for o in load_results().values() if o["dual"]]
    return sorted(rows, key=lambda r: (r["date"], r["issue_no"]))


def data_sha256():
    h = hashlib.sha256()
    for p in (path("data", "pl3_history.json"), path("records", "results.jsonl")):
        h.update(open(p, "rb").read() if os.path.exists(p) else b"")
    return h.hexdigest()


def succ(last):
    yy, n = int(last["issue_no"][:2]), int(last["issue_no"][2:])
    return f"{(yy + 1) % 100:02d}001" if last["date"].endswith("-12-31") else f"{yy:02d}{n + 1:03d}"


def next_period(rows, today):
    """仅当最近一期（双源确认）开奖日为昨天才自动推算；停售假期后、结果未双源确认等情形返回 None，不猜。"""
    last = rows[-1]
    return succ(last) if date.fromisoformat(last["date"]) == today - timedelta(days=1) else None


def sync(log=print):
    """两阶段：先收集并校验全部新结果与确认，任何冲突都在写入任何记录之前退出。"""
    res = load_results()
    allrows = sorted(base_rows() + [o["rec"] for o in res.values()], key=lambda r: (r["date"], r["issue_no"]))
    try: ff = sources.fetch_ff()
    except Exception as e: ff = {}; log(f"S2 不可用：{e}")
    out, t = [], now_bj().isoformat(timespec="seconds")

    def other(n, rec):   # 取“另一个来源”对该期的读数
        if "500.com" in rec["sources"]: return ff.get(n), "futurefortune"
        try: return sources.fetch_500(n), "500.com"
        except Exception as e: log(f"S1 不可用：{e}"); return None, "500.com"

    for n, o in res.items():
        if o["dual"]: continue
        s, nm = other(n, o["rec"])
        if s is None: continue
        if s["numbers"] != o["rec"]["numbers"] or s["date"] != o["rec"]["date"]:
            sys.exit(f"数据源冲突 {n}：已停止，未写入任何记录，请用官方网站人工核对")
        out.append({"type": "confirm", "issue_no": n, "date": s["date"], "numbers": s["numbers"], "sources": o["rec"]["sources"] + [nm], "agree": "dual", "retrieved_at": t})
    last = allrows[-1]
    for _ in range(14):
        p = succ(last)
        try: s1 = sources.fetch_500(p)
        except Exception as e: s1 = None; log(f"S1 不可用：{e}")
        s2 = ff.get(p)
        if s1 and s2 and (s1["numbers"] != s2["numbers"] or s1["date"] != s2["date"]):
            sys.exit(f"数据源冲突 {p}：已停止，未写入任何记录，请用官方网站人工核对")
        src = s1 or s2
        if not src: break
        out.append({"type": "result", "issue_no": p, "date": src["date"], "numbers": src["numbers"],
                    "sources": [n for n, s in (("500.com", s1), ("futurefortune", s2)) if s],
                    "agree": "dual" if (s1 and s2) else "single", "retrieved_at": t})
        last = {"issue_no": p, "date": src["date"]}
    for r in out:
        append(path("records", "results.jsonl"), r)
        log(f"{r['type']} {r['issue_no']} {r['date']} {''.join(map(str, r['numbers']))} ({r['agree']})")
    if not out: log("没有新的开奖结果")


def predict(period, rows, note):
    t = now_bj()
    if t >= cutoff_dt(t.date()):
        sys.exit(f"已过北京时间 {CUTOFF_HM[0]}:{CUTOFF_HM[1]} 内部锁定截止：{period} 期记为缺失，不得补预测")
    if period in load_results():
        sys.exit(f"{period} 期已有开奖结果，拒绝预测")
    recs = read(path("records", "predictions.jsonl"))
    if any(r["period"] == period for r in recs):
        print(f"{period} 期已锁定，跳过"); return None
    hist = [r["numbers"] for r in rows]; prev = recs[-1]["hash"] if recs else "GENESIS"
    env = {k: os.environ.get(k, "") for k in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_NAME")}
    for m, v in models.MODELS.items():
        pick, P = models.forecast(m, period, hist)
        rec = {"period": period, "model": m, "version": v, "pick": pick, "probs": P,
               "data_range": f"{rows[0]['issue_no']}–{rows[-1]['issue_no']}", "data_sha256": data_sha256(), "data_sources": DATA_SRC,
               "expected_draw_date": t.date().isoformat(), "generated_at": t.isoformat(timespec="seconds"),
               "locked_at": t.isoformat(timespec="seconds"), "period_note": note, "env_claimed": env, "prev_hash": prev}
        rec["hash"] = prev = sha(rec)
        append(path("records", "predictions.jsonl"), rec)
        print(f"锁定 {period} {m}-{v}: {''.join(map(str, pick))}")
    return prev


def daily(period=None, confirmed=False):
    sync(); rows = load_history()
    if period:
        if not confirmed: sys.exit("手动指定期号必须同时 --official-confirmed（已在官方网站核实）")
        tip = predict(period, rows, "人工核实期号")
    else:
        p = next_period(rows, now_bj().date())
        if not p:
            print(f"无法自动核实今日期号（最近双源确认的开奖 {rows[-1]['issue_no']} {rows[-1]['date']}）：今日记为缺失；"
                  "若是停售假期后，请在官方网站核实后手动运行并填写期号。"); return
        tip = predict(p, rows, "期号由最近一期自动推算")
        period = p
    if not tip: return
    cfg, why = attest.status(BASE)
    if not cfg: print(f"{why}：本批预测无第三方时间证据，只能是观察记录"); return
    try:
        tsr = attest.stamp(cfg["url"], tip)
        attest.verify(tsr, tip, cfg["cafile"], cfg.get("untrusted"))
        append(path("records", "attestations.jsonl"), {"period": period, "tip": tip, "tsa_url": cfg["url"],
               "tsr_b64": base64.b64encode(tsr).decode(), "retrieved_at": now_bj().isoformat(timespec="seconds")})
        print("已取得并验证第三方时间戳")
    except Exception as e:
        print(f"时间戳失败（{type(e).__name__}）：本批预测只能是观察记录")


def verify(check_net=True):
    prev, hashes = "GENESIS", set()
    for i, r in enumerate(read(path("records", "predictions.jsonl")), 1):
        if r["prev_hash"] != prev or sha({k: v for k, v in r.items() if k != "hash"}) != r["hash"]:
            sys.exit(f"第{i}条预测校验失败：记录被改动或链被打断")
        try: models.check_probs(r["probs"])
        except ValueError: sys.exit(f"第{i}条预测概率分布无效")
        prev = r["hash"]; hashes.add(prev)
    for a in read(path("records", "attestations.jsonl")):
        if a["tip"] not in hashes: sys.exit(f"第三方时间戳所证明的链尾 {a['tip'][:12]} 不在预测链中：疑似尾部被截断")
    if check_net:
        try: ff = sources.fetch_ff()
        except Exception: ff = {}
        for n, o in load_results().items():
            s2 = ff.get(n)
            if s2 and s2["numbers"] != o["rec"]["numbers"]: sys.exit(f"结果 {n} 与 S2 冲突，请人工核对官方")
    print("OK：预测哈希链与时间戳链尾完整", prev[:16])


def audit():
    """事后判定：formal 当且仅当 链完整 ∧ 开奖双源确认且日期相符 ∧ 第三方时间戳验证通过且早于内部截止。"""
    verify(check_net=False)
    preds, res = read(path("records", "predictions.jsonl")), load_results(); cfg, cfg_why = attest.status(BASE)
    atts = {}
    for a in read(path("records", "attestations.jsonl")): atts.setdefault(a["period"], a)
    by = {}
    for r in preds: by.setdefault(r["period"], []).append(r)
    out = {}
    for p, recs in by.items():
        d = date.fromisoformat(recs[0]["expected_draw_date"]); why = None
        if p not in res: out[p] = ("pending", "尚未开奖/无结果"); continue
        if not res[p]["dual"]: why = "开奖结果未双源确认"
        elif res[p]["rec"]["date"] != d.isoformat(): why = "开奖日期与预期不符"
        elif not cfg: why = cfg_why or "未配置TSA"
        elif p not in atts: why = "无第三方时间戳"
        elif atts[p]["tip"] != recs[-1]["hash"]: why = "时间戳链尾与记录不符"
        else:
            try:
                gt = attest.verify(base64.b64decode(atts[p]["tsr_b64"]), atts[p]["tip"], cfg["cafile"], cfg.get("untrusted"))
                if gt.astimezone(BJ).date() != d: why = "时间戳日期与开奖日不符"
                elif gt >= cutoff_dt(d): why = "时间戳晚于内部截止"
            except ValueError: why = "时间戳验证失败"
        out[p] = ("formal", "") if why is None else ("observation", why)
    return out, preds, res


def stats():
    cls, preds, res = audit(); by, hits = {}, {}
    for r in preds:
        c = cls[r["period"]][0]
        if c == "pending": continue
        d = res[r["period"]]["rec"]["numbers"]; hit = len(set(d)) == 3 and sorted(d) == sorted(r["pick"])
        key = (c, f"{r['model']}-{r['version']}")
        s = by.setdefault(key, dict(n=0, hit=0, pnl=0, peak=0, mdd=0, lg=[]))
        s["n"] += 1; s["hit"] += hit; s["pnl"] += (PRIZE if hit else 0) - COST
        s["peak"] = max(s["peak"], s["pnl"]); s["mdd"] = max(s["mdd"], s["peak"] - s["pnl"]); s["lg"].append(models.log_gain(r["probs"], d))
        if c == "formal": hits.setdefault(key[1], []).append((r["period"], int(hit)))
    for (c, m), s in sorted(by.items()):
        print(f"[{c}] {m}（{ROLE.get(m, '')}）: n={s['n']} 命中={s['hit']}({s['hit']/s['n']:.2%}) 累计模拟盈亏={s['pnl']}元 最大回撤={s['mdd']}元 "
              f"平均对数得分增益={sum(s['lg'])/len(s['lg']):+.4f}  （描述性，不含 p 值）")
    why = {}
    for p, (c, w) in cls.items():
        if c == "observation": why[w] = why.get(w, 0) + 1
    if why: print("观察记录原因：", "; ".join(f"{k}×{v}" for k, v in why.items()))
    confirmatory(hits)


def first_eligible():
    f = path("records", "freeze.json")
    return json.load(open(f, encoding="utf-8"))["first_eligible_period"] if os.path.exists(f) else None


def confirmatory(hits):
    """唯一确证性检验：hot-v1 的前瞻命中率 vs 0.6%，单侧精确二项，α=0.05，N=N_STAR 个正式期，只执行一次。
    样本只含：正式记录 ∧ 期号 > EXCLUDE_THROUGH ∧ 期号 ≥ 冻结起点。cold-v1 与随机基线不参与推断。"""
    f = path("records", "confirmatory.jsonl")
    if read(f): print("确证分析已执行（只做一次）：", json.dumps(read(f)[0], ensure_ascii=False)); return
    fe = first_eligible()
    if not fe: print("确证分析：尚未冻结（records/freeze.json 不存在），不做任何推断。"); return
    if fe <= EXCLUDE_THROUGH: print(f"确证分析：冻结起点 {fe} 必须晚于 {EXCLUDE_THROUGH}，不做任何推断。"); return
    use = [h for p, h in hits.get("hot-v1", []) if p > EXCLUDE_THROUGH and p >= fe]
    if len(use) < N_STAR:
        print(f"确证分析：自 {fe} 起正式且双源确认的 hot-v1 期数 {len(use)}，未达 N*={N_STAR}，不做任何推断。"); return
    k = sum(use[:N_STAR]); p = binom_sf(k, N_STAR, P0)
    rec = {"model": "hot-v1", "n": N_STAR, "first_eligible_period": fe, "hits": k, "p_value": p, "alpha": ALPHA,
           "reject_H0": p <= ALPHA, "at": now_bj().isoformat(timespec="seconds")}
    append(f, rec); print("确证分析结果：", json.dumps(rec, ensure_ascii=False))


def _age_days(d): return (now_bj().date() - date.fromisoformat(d)).days


def check_s1(rows, max_age):
    """S1：最近5期与本地逐项一致；并向前探测本地快照之后的新期，报告“最新可验证期号”；日期不得早于 today−max_age。"""
    bad = []
    for r in rows[-5:]:
        try: s1 = sources.fetch_500(r["issue_no"])
        except Exception as e: s1 = None; print("S1", e)
        if not s1 or s1["numbers"] != r["numbers"] or s1["date"] != r["date"]: bad.append(r["issue_no"])
    got, last, err = {}, rows[-1], ""
    for _ in range(14):
        p = succ(last)
        try: s1 = sources.fetch_500(p)
        except Exception as e: s1 = None; err = type(e).__name__; print("S1", e)
        if not s1: break
        got[p] = s1; last = {"issue_no": p, "date": s1["date"]}
    age = _age_days(last["date"]); fails = []
    if bad: fails.append(f"最近5期不一致或解析失败{bad}")
    if err: fails.append(f"探测新期时出错({err})")
    if age > max_age: fails.append(f"数据过旧：最新可验证 {last['date']} 距今 {age} 天 > {max_age}")
    return (not fails), f"最新可验证 {last['issue_no']}（{last['date']}，距今{age}天）" + ("；" + "；".join(fails) if fails else ""), got


def check_s2(rows, max_age, new_from_s1):
    """S2：近30期无缺失/不符；最新期号与日期不得过旧；与 S1 在新期上必须一致。"""
    try: ff = sources.fetch_ff()
    except Exception as e: print("S2", e); return False, f"无法读取（{type(e).__name__}）"
    tail = rows[-30:]
    miss = [r["issue_no"] for r in tail if r["issue_no"] not in ff]
    diff = [r["issue_no"] for r in tail if r["issue_no"] in ff and (ff[r["issue_no"]]["numbers"] != r["numbers"] or ff[r["issue_no"]]["date"] != r["date"])]
    cross = [p for p, s1 in new_from_s1.items() if p in ff and (ff[p]["numbers"] != s1["numbers"] or ff[p]["date"] != s1["date"])]
    lp = max(ff, key=lambda k: (ff[k]["date"], k)); age = _age_days(ff[lp]["date"]); fails = []
    if miss or diff: fails.append(f"近30期缺失{miss}、不符{diff}")
    if cross: fails.append(f"与S1在新期上不一致{cross}")
    if age > max_age: fails.append(f"数据过旧：最新 {ff[lp]['date']} 距今 {age} 天 > {max_age}")
    return (not fails), f"{len(ff)} 期，最新 {lp}（{ff[lp]['date']}，距今{age}天）" + ("；" + "；".join(fails) if fails else "")


def check_tsa():
    """TSA：必须真实签发并验证通过。未配置、证书缺失、哈希不符、请求或验签失败，一律 FAIL。"""
    cfg, why = attest.status(BASE)
    if not cfg: return False, why
    try:
        d = hashlib.sha256(b"conn-test").hexdigest()
        gt = attest.verify(attest.stamp(cfg["url"], d), d, cfg["cafile"], cfg.get("untrusted"))
        return True, f"已签发并验证，令牌时间 {gt.isoformat()}"
    except Exception as e: return False, f"请求或验签失败（{type(e).__name__}）"


def conn_test(max_age=2):
    """阶段一验收：S1、S2、TSA 三项必须全部 PASS，任何一项失败/缺失都返回非零退出码；三项分别输出。"""
    rows = load_history()
    ok1, d1, got = check_s1(rows, max_age)
    ok2, d2 = check_s2(rows, max_age, got)
    ok3, d3 = check_tsa()
    print("== conn-test 汇总 ==")
    print(f"本地快照最新: {rows[-1]['issue_no']}（{rows[-1]['date']}）；新鲜度阈值 {max_age} 天（遇停售假期需人工判断）")
    for nm, ok, d in (("S1", ok1, d1), ("S2", ok2, d2), ("TSA", ok3, d3)): print(f"{nm}: {'PASS' if ok else 'FAIL'} — {d}")
    allok = ok1 and ok2 and ok3
    print("结论:", "三项全部 PASS" if allok else "未通过：任一项 FAIL 即不得进入部署验收")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["daily"]: daily(a[a.index("--period") + 1] if "--period" in a else None, "--official-confirmed" in a)
    elif a[:1] == ["verify"]: verify()
    elif a[:1] == ["audit"]:
        for p, (c, w) in sorted(audit()[0].items()): print(p, c, w)
    elif a[:1] == ["stats"]: stats()
    elif a[:1] == ["conn-test"]: conn_test(int(a[a.index("--max-age-days") + 1]) if "--max-age-days" in a else 2)
    else: print(__doc__)
