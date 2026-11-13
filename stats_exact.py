"""精确二项与 Holm（纯标准库，对数空间求和避免溢出）。"""
from math import exp, lgamma, log


def binom_sf(k, n, p):
    """P(X >= k)，X~Bin(n,p)。"""
    if k <= 0: return 1.0
    if k > n: return 0.0
    lc = lgamma(n + 1)
    return min(1.0, sum(exp(lc - lgamma(j + 1) - lgamma(n - j + 1) + j * log(p) + (n - j) * log(1 - p)) for j in range(k, n + 1)))


def holm(ps, alpha=0.05):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0.0] * len(ps); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i])); adj[i] = run
    return adj, [a <= alpha for a in adj]
