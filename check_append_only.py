#!/usr/bin/env python3
"""推送前检查：只允许对 records/ 三个账本文件做“追加”，任何修改、删除或其他路径的改动都会失败。"""
import subprocess, sys

ALLOWED = {"records/predictions.jsonl", "records/results.jsonl", "records/attestations.jsonl", "records/confirmatory.jsonl"}


def sh(*a):
    return subprocess.run(a, capture_output=True, check=True).stdout


def main():
    bad = []
    for line in sh("git", "status", "--porcelain", "-uall").decode().splitlines():
        code, p = line[:2].strip(), line[3:]
        if p not in ALLOWED: bad.append(f"不允许改动的路径: {p}"); continue
        if code == "M":
            if not open(p, "rb").read().startswith(sh("git", "show", f"HEAD:{p}")): bad.append(f"非追加改动: {p}")
        elif code not in ("??", "A"): bad.append(f"不允许的变更类型 {code}: {p}")
    if bad: sys.exit("拒绝提交：\n" + "\n".join(bad))
    print("追加检查通过")


if __name__ == "__main__":
    main()
