"""Offline deterministic validation for the Gansu official S1 HTML adapter."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sources


def document(rows):
    body = " ".join(
        f'<div><span>{d}</span><span>{p}</span><span>{a}</span><span>{b}</span><span>{c}</span></div>'
        for d, p, a, b, c in rows
    )
    return ("<html><body><h1>排列3 历史开奖数据</h1>"
            "<div>开奖日期 开奖期次 开奖号码</div>" + body +
            "</body></html>").encode("utf-8")


data = [
    (f"2026-11-{10+i:02d}", f"{26300+i}", str(i % 10), str((i+1) % 10), str((i+2) % 10))
    for i in range(5)
]
raw = document(data)
got = sources.parse_gansu_history(raw)
assert len(got) == 5
assert got["26300"] == {"date": "2026-11-10", "numbers": [0, 1, 2]}
assert got["26304"] == {"date": "2026-11-14", "numbers": [4, 5, 6]}


def fails(raw_data):
    try:
        sources.parse_gansu_history(raw_data)
    except ValueError:
        return
    raise AssertionError("Malformed HTML unexpectedly accepted")


fails(raw.replace(b"</html>", b""))
fails(raw.replace(b"\xe5\xbc\x80\xe5\xa5\x96\xe6\x97\xa5\xe6\x9c\x9f", b"bad-label"))
fails(document(data[:4]))
fails(document(data + [data[0]]))
fails(document(data[:-1] + [("2026-11-14", "26304", "9", "9", "9")]).replace(
    b"2026-11-14", b"2026-11-50"))

old_get, old_cache = sources.get, sources._gansu_cache
try:
    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        return 200, raw
    sources.get = fake_get
    sources._gansu_cache = None
    assert sources.fetch_500("26300") == {"period": "26300", "date": "2026-11-10", "numbers": [0, 1, 2]}
    assert sources.fetch_500("26304")["numbers"] == [4, 5, 6]
    assert sources.fetch_500("26305") is None
    assert calls == [sources.S1_URL], calls
    try:
        sources.fetch_500("not-five")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid period accepted")
finally:
    sources.get, sources._gansu_cache = old_get, old_cache

print("gansu-s1: ALL PASSED")
