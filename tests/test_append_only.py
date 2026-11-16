"""推送前追加检查测试：python tests/test_append_only.py"""
import os, shutil, subprocess, sys, tempfile
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = tempfile.mkdtemp(); os.makedirs(d + "/records"); shutil.copy(SRC + "/check_append_only.py", d)
g = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, check=True)
chk = lambda: subprocess.run([sys.executable, "check_append_only.py"], cwd=d, capture_output=True)
g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
open(d + "/records/predictions.jsonl", "w").write("a\nb\n"); g("add", "-A"); g("commit", "-qm", "init")
open(d + "/records/predictions.jsonl", "a").write("c\n"); assert chk().returncode == 0                                # 追加：通过
open(d + "/records/results.jsonl", "w").write("x\n"); assert chk().returncode == 0                                 # 新账本文件：通过
open(d + "/records/predictions.jsonl", "w").write("a\nB\nc\n"); assert chk().returncode != 0                       # 改写旧行：拒绝
open(d + "/records/predictions.jsonl", "w").write("a\nb\n"); g("checkout", "--", "."); os.remove(d + "/records/predictions.jsonl"); assert chk().returncode != 0  # 删除：拒绝
g("checkout", "--", "."); open(d + "/evil.py", "w").write("x"); assert chk().returncode != 0                       # 其他路径：拒绝
# 证据文件（records/evidence/）：允许新增；已提交的证据文件不得修改或删除；records/ 下其他新文件仍不允许
os.remove(d + "/evil.py"); g("checkout", "--", "."); os.remove(d + "/records/results.jsonl") if os.path.exists(d + "/records/results.jsonl") else None
os.makedirs(d + "/records/evidence"); open(d + "/records/evidence/s1-aaaa.html", "wb").write(b"raw"); assert chk().returncode == 0                  # 新增证据文件：通过
g("add", "-A"); g("commit", "-qm", "evidence")
open(d + "/records/evidence/s1-aaaa.html", "wb").write(b"tampered"); assert chk().returncode != 0                                                   # 改写已提交的证据：拒绝
g("checkout", "--", "."); os.remove(d + "/records/evidence/s1-aaaa.html"); assert chk().returncode != 0                                              # 删除已提交的证据：拒绝
g("checkout", "--", "."); open(d + "/records/other.json", "w").write("x"); assert chk().returncode != 0                                              # records/ 下其他新文件：拒绝
os.remove(d + "/records/other.json"); open(d + "/records/evidence/s2-bbbb.json", "wb").write(b"raw2"); assert chk().returncode == 0                   # 再新增一个证据文件：通过
shutil.rmtree(d); print("append-only: ALL PASSED")
