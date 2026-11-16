"""数据源适配器。S1=甘肃省体彩历史开奖页面，S2=GitHub 开源数据集 futurefortune（MIT）。
官方体彩网为争议时的最终依据（人工核对）。网络部分只能在 GitHub Actions 里验证：运行 conn-test。
日志只输出主机名与异常类型，不输出响应正文。"""
import hashlib, json, re, time, datetime, html, urllib.error, urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; pl3-lab/2.0; research)"
S1_URL = "https://www.gstc.org.cn/wanfa/pl3_history"
S2_URL = "https://raw.githubusercontent.com/ahbencat/futurefortune/{branch}/datas/pl3_all_data.json"
EVIDENCE = {}   # 渠道 -> {"url", "sha256", "raw"}：最近一次抓取的 URL、原始字节及其哈希，供 sync 存证并写入 confirm 记录


def get(url, retries=3, timeout=25):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, b""
            last = f"HTTP {e.code}"
        except Exception as e:
            last = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET 失败 {urlparse(url).netloc}: {last}")


def decode(raw):
    try: return raw.decode("utf-8")
    except UnicodeDecodeError: return raw.decode("gb18030", errors="replace")


def parse_500(period, raw):
    """解析 期号/开奖日期/开奖号码；缺任何一项或期号不符都返回 None（宁缺毋滥）。"""
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", decode(raw)))
    mp = re.search(r"第\s*(\d{5})\s*期", t)
    md = re.search(r"开奖日期[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", t)
    mn = re.search(r"开奖号码[：:]\s*(\d)\s*(\d)\s*(\d)(?!\d)", t)
    if not (mp and md and mn) or mp.group(1) != period: return None
    y, m, d = map(int, md.groups())
    return {"period": period, "date": f"{y:04d}-{m:02d}-{d:02d}", "numbers": [int(x) for x in mn.groups()]}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden and value.strip():
            self.nodes.append(value)


def parse_gansu_history(raw):
    """Parse current historical table only; reject incomplete/malformed/duplicate rows.

    Returns {period: {'date': ISO, 'numbers': [int,int,int]}}.
    No draws can be synthesized if a row is absent or bad.
    """
    if not re.search(rb"</html\s*>", raw, re.I):
        raise ValueError("S1 HTML incomplete")
    parsed = _VisibleText()
    parsed.feed(decode(raw))
    text = " ".join(html.unescape(" ".join(parsed.nodes)).split())
    header = "开奖日期 开奖期次 开奖号码"
    if text.count(header) != 1:
        raise ValueError("S1 table header missing or duplicated")
    segment = text.split(header, 1)[1]
    pat = re.compile(r"(?<!\d)(20\d{2}-\d{1,2}-\d{1,2})\s+(\d{5})\s+(\d)\s+(\d)\s+(\d)(?!\d)")
    rows = {}
    for match in pat.finditer(segment):
        ds, period, *digits = match.groups()
        try:
            iso = datetime.date.fromisoformat(ds).isoformat()
        except ValueError as exc:
            raise ValueError("S1 invalid calendar date") from exc
        if period in rows:
            raise ValueError("S1 duplicate issue number")
        rows[period] = {"date": iso, "numbers": [int(x) for x in digits]}
    if not 5 <= len(rows) <= 50:
        raise ValueError("S1 history row count outside expected limits")
    # Preserve row order. A garbled or partial table is not acceptable.
    if len({item["date"] for item in rows.values()}) != len(rows):
        raise ValueError("S1 duplicate draw date")
    return rows


_gansu_cache = None


def fetch_s1_window():
    """S1 当前滚动窗口 {期号: {date, numbers}}：严格解析，任何 HTTP/解析问题都抛异常；单进程内只下载一次。"""
    global _gansu_cache
    if _gansu_cache is None:
        status, raw = get(S1_URL)
        if status != 200:
            raise RuntimeError(f"S1 HTTP {status}")
        _gansu_cache = parse_gansu_history(raw)
        EVIDENCE["gstc.org.cn"] = {"url": S1_URL, "sha256": hashlib.sha256(raw).hexdigest(), "raw": raw}
    return _gansu_cache


def fetch_500(period):
    """Compatibility entrypoint; S1 is the official Gansu publication, not 500.com."""
    if not re.fullmatch(r"\d{5}", period):
        raise ValueError("S1 invalid period")
    window = fetch_s1_window()
    return {"period": period, **window[period]} if period in window else None


def parse_ff(raw):
    return {r["issue_no"]: {"date": r["date"], "numbers": [int(x) for x in r["numbers"]]} for r in json.loads(decode(raw))}


def fetch_ff(branch="master"):
    status, raw = get(S2_URL.format(branch=branch))
    if status != 200: raise RuntimeError(f"S2 HTTP {status}")
    out = parse_ff(raw)
    EVIDENCE["futurefortune"] = {"url": S2_URL.format(branch=branch), "sha256": hashlib.sha256(raw).hexdigest(), "raw": raw}
    return out
