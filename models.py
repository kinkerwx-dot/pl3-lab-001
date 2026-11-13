"""冻结的模型定义（PL3-LAB-001）。仅用标准库。任何改动必须新建版本号（如 hot-v2），不得修改 v1。"""
import hashlib, itertools, math

COMBOS = list(itertools.combinations(range(10), 3))     # 120 个组选六号码，字典序
PERMS = list(itertools.permutations(range(3)))
W, ALPHA_SM, OMIT_CAP, OMIT_FLOOR = 200, 10, 30, 5      # 预先固定常数，未调参
MODELS = {"random-baseline": "v1", "hot": "v1", "cold": "v1"}


def baseline_pick(period):
    """随机基线 v1：SHA256('PL3-LAB-001|RANDOM-BASELINE-v1|期号') 取模 120。纯函数，任何人可复算。"""
    h = hashlib.sha256(f"PL3-LAB-001|RANDOM-BASELINE-v1|{period}".encode()).hexdigest()
    return list(COMBOS[int(h, 16) % 120])


def digit_probs(kind, hist):
    """各位置数字概率（3×10，位置独立）。hist=已开奖号码列表 [[a,b,c],...]，只含目标期之前。"""
    P = []
    for pos in range(3):
        col = [r[pos] for r in hist]
        if kind == "hot":
            recent = col[-W:]
            P.append([(recent.count(d) + ALPHA_SM) / (len(recent) + 10 * ALPHA_SM) for d in range(10)])
        else:   # cold：遗漏期数越大权重越高（封顶）；末 31 期内未出现 = 封顶值
            tail = col[-(OMIT_CAP + 1):][::-1]
            w = [min(next((k for k, x in enumerate(tail) if x == d), OMIT_CAP), OMIT_CAP) + OMIT_FLOOR for d in range(10)]
            P.append([x / sum(w) for x in w])
    return P


def check_probs(P, tol=1e-12):
    ok = len(P) == 3 and all(len(r) == 10 and all(x > 0 for x in r) and abs(sum(r) - 1) <= tol for r in P)
    if not ok: raise ValueError("概率分布未归一化或含非正数")


def pick_g6(P):
    """组选六号码中（6 种排列概率之和）最大者；并列取字典序最小。"""
    s = [sum(P[0][c[a]] * P[1][c[b]] * P[2][c[x]] for a, b, x in PERMS) for c in COMBOS]
    return list(COMBOS[max(range(120), key=lambda i: s[i])])


def forecast(model, period, hist):
    if model == "random-baseline":
        return baseline_pick(period), [[0.1] * 10 for _ in range(3)]
    P = digit_probs(model, hist); check_probs(P)
    return pick_g6(P), P


def log_gain(P, draw):
    """相对均匀分布的对数得分增益（nat）。"""
    a, b, c = draw
    return math.log(P[0][a] * P[1][b] * P[2][c] * 1000)
