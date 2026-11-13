#!/usr/bin/env python3
"""PL3-LAB-001 回溯研究 R1：排列三历史开奖的随机性检验 + 走步（walk-forward）模型评估。

这是【回溯性历史研究】，不是前瞻样本外成绩。检验清单与常数在运行前固定（共13项，Holm 校正，α=0.05）：
  A 均匀性   : 百/十/个位数字卡方 ×3；形态(豹子/组三/组六=1%/27%/72%)卡方 ×1
  B 独立性   : 各位置相邻两期数字转移表卡方 ×3；和值游程检验 ×1；和值 Ljung-Box(lag1-10) ×1
  C 走步模型 : hot-v1、cold-v1 各自的对数得分增益(相对均匀分布)单侧t检验 ×2；
               组选六命中数 vs 二项(p=0.006)单侧 ×2     （共 3+1+3+1+1+2+2 = 13）
随机基线 random-baseline-v1 仅作描述性对照，不进入检验族。
用法: python backtest_randomness.py data/pl3_history.json
"""
import json, sys
import numpy as np
from math import sqrt
from scipy import stats
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from models import W, baseline_pick, digit_probs, pick_g6



def load(path):
    rows = json.load(open(path, encoding="utf-8"))
    rows.sort(key=lambda r: r["issue_no"])
    return [r["issue_no"] for r in rows], np.array([[int(x) for x in r["numbers"]] for r in rows])


def holm(ps, alpha=0.05):
    order = np.argsort(ps); m = len(ps); out = [False] * m; adj = [None] * m; run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i])); adj[i] = run
    for i in range(m): out[i] = adj[i] <= alpha
    return adj, out


def main(path):
    issues, X = load(path); H = X.tolist(); n = len(X); res = []
    def add(name, p, note=""): res.append((name, float(p), note))
    # A 均匀性
    for pos, nm in enumerate(["百位", "十位", "个位"]):
        add(f"A 均匀性-{nm}", stats.chisquare(np.bincount(X[:, pos], minlength=10)).pvalue)
    kind = np.array([1 if len(set(r)) == 1 else (2 if len(set(r)) == 2 else 3) for r in X])
    obs = np.bincount(kind, minlength=4)[1:]
    add("A 形态(豹子/组三/组六)", stats.chisquare(obs, f_exp=n * np.array([.01, .27, .72])).pvalue, f"观测占比={np.round(obs/n,4).tolist()}")
    # B 独立性
    for pos, nm in enumerate(["百位", "十位", "个位"]):
        T = np.zeros((10, 10)); np.add.at(T, (X[:-1, pos], X[1:, pos]), 1)
        add(f"B 相邻期独立-{nm}", stats.chi2_contingency(T)[1])
    s = X.sum(1).astype(float); med = np.median(s); b = s > med; r1 = 1 + int((b[1:] != b[:-1]).sum())
    n1, n2 = int(b.sum()), int((~b).sum()); mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = 2 * n1 * n2 * (2 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    add("B 和值游程检验", 2 * stats.norm.sf(abs((r1 - mu) / sqrt(var))))
    d = s - s.mean(); acf = [np.sum(d[:-k] * d[k:]) / np.sum(d * d) for k in range(1, 11)]
    Q = n * (n + 2) * sum(acf[k - 1] ** 2 / (n - k) for k in range(1, 11)); add("B 和值Ljung-Box", stats.chi2.sf(Q, 10))
    # C 走步模型
    desc = {}
    for kd in ("hot", "cold"):
        gains, hits, picks = [], 0, 0
        for t in range(W, n):
            P = digit_probs(kd, H[:t]); a, b2, c = X[t]
            gains.append(np.log(P[0][a] * P[1][b2] * P[2][c] * 1000))
            hit = len(set(X[t])) == 3 and tuple(sorted(X[t])) == tuple(pick_g6(P)); hits += hit; picks += 1
        g = np.array(gains)
        add(f"C {kd}-v1 对数得分增益>0", stats.ttest_1samp(g, 0, alternative="greater").pvalue, f"均值={g.mean():+.5f} nat/期")
        add(f"C {kd}-v1 组六命中>随机", stats.binomtest(int(hits), picks, 0.006, alternative="greater").pvalue, f"命中{hits}/{picks}={hits/picks:.3%}")
    base = sum(1 for t in range(W, n) if len(set(X[t])) == 3 and baseline_pick(issues[t]) == sorted(X[t].tolist()))
    adj, rej = holm([p for _, p, _ in res])
    print(f"期数 n={n}  区间 {issues[0]}–{issues[-1]}  走步评估期数={n-W}")
    for (nm, p, note), a, r in zip(res, adj, rej):
        print(f"{nm:<26} p={p:.4f}  Holm校正后={a:.4f}  {'拒绝H0' if r else '未拒绝'}  {note}")
    print(f"随机基线 random-baseline-v1 同区间命中 {base}/{n-W}={base/(n-W):.3%}（理论 0.600%，盈亏平衡 1.156%）")
    print(f"检验族共 {len(res)} 项，Holm 校正后拒绝 {sum(rej)} 项")


if __name__ == "__main__":
    main(sys.argv[1])
