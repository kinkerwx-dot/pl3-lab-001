"""数据源适配器。S1=500彩票网单期页面，S2=GitHub 开源数据集 futurefortune（MIT）。
官方体彩网为争议时的最终依据（人工核对）。网络部分只能在 GitHub Actions 里验证：运行 conn-test。
日志只输出主机名与异常类型，不输出响应正文。"""
import json, re, time, urllib.error, urllib.request
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; pl3-lab/2.0; research)"
S1_URL = "https://kaijiang.500.com/shtml/pls/{period}.shtml"
S2_URL = "https://raw.githubusercontent.com/ahbencat/futurefortune/{branch}/datas/pl3_all_data.json"


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


def fetch_500(period):
    status, raw = get(S1_URL.format(period=period))
    return parse_500(period, raw) if status == 200 else None


def parse_ff(raw):
    return {r["issue_no"]: {"date": r["date"], "numbers": [int(x) for x in r["numbers"]]} for r in json.loads(decode(raw))}


def fetch_ff(branch="master"):
    status, raw = get(S2_URL.format(branch=branch))
    if status != 200: raise RuntimeError(f"S2 HTTP {status}")
    return parse_ff(raw)
