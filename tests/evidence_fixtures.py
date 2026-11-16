"""测试夹具（不是测试文件）：构造可被 S1/S2 解析器解析的“原始证据”字节。"""
import hashlib, json
from datetime import timedelta


def sha(b): return hashlib.sha256(b).hexdigest()


def gansu_page(rows):
    """rows: {期号: {"date","numbers"}} -> 甘肃历史页 HTML 字节（不足 5 行时补不相关的填充行，满足解析器的行数下限）。"""
    items = [(v["date"], p, *v["numbers"]) for p, v in rows.items()]; k = 0
    while len(items) < 5: k += 1; items.append((f"2000-01-{k:02d}", f"0000{k}", 0, 0, 0))
    body = " ".join(f"<div><span>{d}</span><span>{p}</span><span>{a}</span><span>{b}</span><span>{c}</span></div>" for d, p, a, b, c in items)
    return ("<html><body><h1>排列3 历史开奖数据</h1><div>开奖日期 开奖期次 开奖号码</div>" + body + "</body></html>").encode("utf-8")


def ff_json(rows):
    return json.dumps([{"issue_no": p, "date": v["date"], "numbers": [str(x) for x in v["numbers"]]} for p, v in rows.items()], ensure_ascii=False).encode("utf-8")


def synth_rows(today, n=40):
    """以 today 为锚的合成历史：n 个连续开奖日，止于昨天；期号 = 年份后两位 + 当年第几天（与真实编号一样跨年归一）。
    让依赖“当前日期”的测试不绑定任何具体年份（到 2027 年及以后也成立）。"""
    rows = []
    for k in range(n, 0, -1):
        dd = today - timedelta(days=k)
        rows.append({"issue_no": f"{dd.year % 100:02d}{dd.timetuple().tm_yday:03d}", "date": dd.isoformat(), "numbers": [str(dd.toordinal() % 10), str((dd.toordinal() * 3) % 10), str((dd.toordinal() * 7) % 10)]})
    return rows
