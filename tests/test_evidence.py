"""confirm 证据真实性测试（仅标准库，不联网）：python tests/test_evidence.py
只有“号码相同”“域名可信 + 哈希格式正确”都绝不能把 single 升级为 dual：必须有可读取的证据文件、哈希相符、内容含该结论。"""
import contextlib, io, json, os, shutil, sys, tempfile
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_fixtures as EF, sources, pl3_lab as L

SRC = L.BASE; P, DATE, NUM = "26310", "2026-11-20", [1, 2, 3]
ROW = {P: {"date": DATE, "numbers": NUM}}
S1_URL, S2_URL = "https://www.gstc.org.cn/wanfa/pl3_history", "https://raw.githubusercontent.com/ahbencat/futurefortune/master/datas/pl3_all_data.json"
MAN = {"channels": {"gstc.org.cn": ["www.gstc.org.cn"], "futurefortune": ["raw.githubusercontent.com"], "official-manual": ["official.example.test"]}}

def world(policy=None, sources_=("futurefortune",)):
    d = tempfile.mkdtemp(); os.makedirs(d + "/records/evidence"); L.BASE = d
    if policy: json.dump(policy, open(d + "/evidence_policy.json", "w"))
    L.append(d + "/records/results.jsonl", {"type": "result", "issue_no": P, "date": DATE, "numbers": NUM, "sources": list(sources_), "agree": "single", "retrieved_at": "2026-11-20T15:00:00+08:00"})
    return d
def save(d, name, raw): fn = "records/evidence/" + name; open(d + "/" + fn, "wb").write(raw); return fn
def conf(channel, url, file, raw=None, sha=None, **over):
    ev = {"url": url, "sha256": sha if sha is not None else EF.sha(raw or b""), "retrieved_at": "2026-11-21T15:00:00+08:00"}
    if file is not None: ev["file"] = file
    ev.update(over.pop("ev", {}))
    r = {"type": "confirm", "issue_no": P, "date": DATE, "numbers": NUM, "channel": channel, "evidence": ev, "sources": ["x"], "agree": "dual", "retrieved_at": "x"}
    r.update(over); return r
def dual(make, policy=None, sources_=("futurefortune",)):
    d = world(policy, sources_); rec = make(d)
    if rec is not None: L.append(d + "/records/results.jsonl", rec)
    out = L.load_results()[P]["dual"]; shutil.rmtree(d); return out

page, js = EF.gansu_page(ROW), EF.ff_json(ROW)
def auto1(d, raw=page, **kw): return conf("gstc.org.cn", S1_URL, save(d, "s1.html", raw), raw, **kw)
# ---- 合法
assert dual(lambda d: auto1(d)) is True                                                                          # S1 证据：页面含该期，哈希相符
assert dual(lambda d: conf("futurefortune", S2_URL, save(d, "s2.json", js), js), sources_=("gstc.org.cn",)) is True  # S2 证据（原记录来自 S1）
# ---- 审查指出的漏洞：可信域名 + 合法时间 + 格式正确的哈希，但没有任何真实证据文件
assert dual(lambda d: conf("gstc.org.cn", S1_URL, None, sha="a" * 64)) is False                                  # 没有 file 字段
assert dual(lambda d: conf("gstc.org.cn", S1_URL, "records/evidence/not-there.html", sha="a" * 64)) is False       # file 指向不存在的文件
assert dual(lambda d: {"type": "confirm", "issue_no": P, "date": DATE, "numbers": NUM, "sources": ["futurefortune", "随便写的来源"], "agree": "dual", "retrieved_at": "x"}) is False   # 最初的伪造
# ---- 有文件但不可信
assert dual(lambda d: auto1(d, sha="a" * 64)) is False                                                           # 文件存在，哈希字段与实际不符
assert dual(lambda d: auto1(d, raw=EF.gansu_page({"26311": {"date": DATE, "numbers": NUM}}))) is False           # 文件不含该期
assert dual(lambda d: auto1(d, raw=EF.gansu_page({P: {"date": DATE, "numbers": [9, 9, 9]}}))) is False           # 含该期但号码不同
assert dual(lambda d: auto1(d, raw=EF.gansu_page({P: {"date": "2026-11-19", "numbers": NUM}}))) is False         # 含该期但日期不同
assert dual(lambda d: auto1(d, raw=b"<html>not a lottery page</html>")) is False                                 # 无法被渠道解析器解析
assert dual(lambda d: conf("futurefortune", S2_URL, save(d, "s2.json", b"{bad json"), b"{bad json"), sources_=("gstc.org.cn",)) is False
assert dual(lambda d: conf("gstc.org.cn", S1_URL, save(d, "s2.json", js), js)) is False                           # 用 S2 的文件冒充 S1（S1 解析器不接受）
def outside(d, rel, raw=page):                                                                                    # 在“越界位置”真的放一份有效证据，路径限制才有意义
    os.makedirs(os.path.dirname(d + "/" + rel), exist_ok=True); open(d + "/" + rel, "wb").write(raw)
    return conf("gstc.org.cn", S1_URL, rel, raw)
assert dual(lambda d: outside(d, "x.html") and conf("gstc.org.cn", S1_URL, "records/evidence/../../x.html", page)) is False   # 路径穿越（文件真实存在）
assert dual(lambda d: outside(d, "elsewhere/s1.html")) is False                                                   # 不在证据目录（文件真实存在）
assert dual(lambda d: conf("gstc.org.cn", S1_URL, save(d, "empty.html", b""), b"")) is False                      # 空文件
# ---- 渠道/主机/格式/数据一致性
same = lambda d: conf("futurefortune", S2_URL, save(d, "s2.json", js), js)
assert dual(same) is False                                                                                       # 与原记录同一渠道（证据再有效也不是“第二渠道”）
assert dual(lambda d: conf("evil.example", S1_URL, save(d, "s1.html", page), page)) is False and dual(lambda d: conf(None, S1_URL, save(d, "s1.html", page), page)) is False
assert dual(lambda d: conf("gstc.org.cn", "https://evil.example/pl3", save(d, "s1.html", page), page)) is False
assert dual(lambda d: conf("gstc.org.cn", "http://www.gstc.org.cn/wanfa/pl3_history", save(d, "s1.html", page), page)) is False
for bad_sha in ("a" * 63, "A" * 64, "z" * 64): assert dual(lambda d: auto1(d, sha=bad_sha)) is False
assert dual(lambda d: auto1(d, ev={"retrieved_at": "2026-11-21T15:00:00"})) is False and dual(lambda d: auto1(d, ev={"retrieved_at": "昨天"})) is False
assert dual(lambda d: auto1(d, numbers=[1, 2, 4])) is False and dual(lambda d: auto1(d, date="2026-11-21")) is False   # confirm 与原记录不一致
# ---- 人工核对（official-manual）：默认关闭；开启后必须有证据文件 + 核对人 + 文件内容含结论
text = f"中国体育彩票 排列3 开奖公告 第{P}期 开奖日期：2026年11月20日 开奖号码：1 2 3".encode()
def man(d, raw=text, checker="张三", file="records/evidence/official-26310.txt", url="https://official.example.test/pl3/26310", **kw):
    fn = save(d, "official-26310.txt", raw) if file.startswith("records/evidence/official") else file
    return conf("official-manual", url, fn, raw, ev={"checker": checker} if checker is not None else {}, **kw)
assert dual(man, policy=MAN) is True
assert dual(man, policy=None) is False                                                                           # 默认策略：人工恢复关闭
assert dual(lambda d: man(d, checker=None), policy=MAN) is False and dual(lambda d: man(d, checker=" "), policy=MAN) is False   # 缺核对人
assert dual(lambda d: man(d, raw="随手写的一段话".encode()), policy=MAN) is False                                          # 文件内容不含结论
assert dual(lambda d: man(d, raw="第26310期 2026年11月20日 开奖号码 4 5 6".encode()), policy=MAN) is False          # 号码不对
assert dual(lambda d: man(d, raw="第26310期 2026年11月19日 开奖号码 1 2 3".encode()), policy=MAN) is False          # 日期不对
assert dual(lambda d: man(d, raw="第26311期 2026年11月20日 开奖号码 1 2 3".encode()), policy=MAN) is False          # 期号不对
assert dual(lambda d: man(d, sha="0" * 64), policy=MAN) is False                                                 # 哈希不符
assert dual(lambda d: man(d, file="records/evidence/../../outside.txt"), policy=MAN) is False
assert dual(lambda d: man(d, url="https://evil.example/x"), policy=MAN) is False                                 # 主机不在 official-manual 名单
assert dual(lambda d: man(d, raw=b""), policy=MAN) is False
# ---- confirm 先于原记录出现：忽略
d = world(); L.append(d + "/records/results.jsonl", {**auto1(d), "issue_no": "26999"}); assert list(L.load_results()) == [P]; shutil.rmtree(d)

# ---- sync：只在有可追溯证据时写 confirm；证据文件先落盘；证据内容不含结论时即使写了 confirm 也不会升级
d = world(); L.BASE = d; sources.EVIDENCE.clear()
os.makedirs(d + "/data"); shutil.copy(SRC + "/data/pl3_history.json", d + "/data/")
sources.fetch_500 = lambda p: {"period": p, "date": DATE, "numbers": NUM} if p == P else None; sources.fetch_ff = lambda *a, **k: {}
L.now_bj = lambda: datetime(2026, 11, 21, 15, 0, tzinfo=L.BJ)
logs = []; L.sync(logs.append)
assert not L.load_results()[P]["dual"] and any("没有可追溯的证据" in l for l in logs) and [r["type"] for r in L.read(d + "/records/results.jsonl")] == ["result"], logs
bad_raw = EF.gansu_page({"26311": {"date": DATE, "numbers": NUM}})                                               # EVIDENCE 与读数不符（内容不含该期）
sources.EVIDENCE["gstc.org.cn"] = {"url": S1_URL, "sha256": EF.sha(bad_raw), "raw": bad_raw}
L.sync(lambda s: None); assert not L.load_results()[P]["dual"], "内容不含结论的证据不得升级"
shutil.rmtree(d); d = world(); L.BASE = d; os.makedirs(d + "/data"); shutil.copy(SRC + "/data/pl3_history.json", d + "/data/")
sources.EVIDENCE["gstc.org.cn"] = {"url": S1_URL, "sha256": EF.sha(page), "raw": page}
L.sync(lambda s: None); c = L.read(d + "/records/results.jsonl")[-1]
assert c["type"] == "confirm" and c["channel"] == "gstc.org.cn" and L.load_results()[P]["dual"]
assert EF.sha(open(d + "/" + c["evidence"]["file"], "rb").read()) == c["evidence"]["sha256"] == EF.sha(page) and "raw" not in json.dumps(c)
n = len(L.read(d + "/records/results.jsonl")); L.sync(lambda s: None); assert len(L.read(d + "/records/results.jsonl")) == n   # 幂等
shutil.rmtree(d); L.BASE = SRC; print("evidence: ALL PASSED")
