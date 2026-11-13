# PL3-LAB-001 排列三零资金模拟研究（v2.2.1）

规则见 `PREREGISTRATION.md`（v1.2.1 草案，尚未发布、尚未生效）。**真实投注金额始终为 0。** 审计整改对照见 `AUDIT_RESPONSE.md`。

## 已验证 / 未验证
- 已验证（离线）：`for t in tests/test_*.py; do python3 $t; done`
  模型与概率校验、期号推算、双渠道确认与冲突、哈希链与篡改/截断检测、只追加检查、
  时间戳验证与审计分类（用**本地自建**测试 TSA 演练，不是真实第三方）。核心仅用标准库；时间戳测试需要 `openssl`。
- **未验证**：500.com 页面的真实格式、GitHub 服务器能否稳定访问数据源、任何真实 TSA、定时任务的实际触发。

## 两阶段上线（缺一不可）
**阶段一（只读验证）**：默认分支上**只放** `.github/workflows/pl3-conn-test.yml`（手动触发、只读、无定时）。`stage2/` 里的 `pl3-daily.yml` 在 `.github` 之外，不会被 Actions 识别。
1. 核实压缩包 SHA-256 与 `SHA256SUMS`。
2. 预注册 v1.2.1（仅文字修订，规则同 v1.2）：用户已有条件批准（单一主挑战者 hot-v1、N\*=1,662）；条件是 §0 披露原样保留。
3. 运行 `bash tsa/download_and_check.sh`：下载 FreeTSA 的 `cacert.pem`、`tsa.crt` 并与 `tsa/pins.json` 比对，不符则失败并删除文件；通过后连同证书一起提交。
4. 新建**公开**仓库并上传；为默认分支设置保护：**禁止强制推送、禁止删除，并禁用管理员绕过**。
5. 手动运行 `pl3-conn-test`：`S1`、`S2`、`TSA` 三项都必须 PASS，任一项失败或缺失整个任务即失败（TSA 须是真实 FreeTSA 签发并验签；S1/S2 须在新鲜度阈值内，默认 2 天）。证书未提交时 TSA 一项必然失败。
6. 验收凭据：分支规则回读 + Actions 运行链接 + 三项各自日志。

**阶段二（仅在阶段一验收通过后）**：把 `stage2/pl3-daily.yml` 移到 `.github/workflows/`，并在 *Settings → Actions → General → Workflow permissions* 选 Read and write（只有 `record` 任务会写）。
预注册提交后、第一个计划参与确证的期号之前，提交 `records/freeze.json`：`{"first_eligible_period": "<期号，须晚于 26302>", "prereg_commit": "<SHA>"}`；没有它就不会执行确证分析。26302 及更早的期号永不计入确证样本（开奖后仍可按冻结算法作为历史输入）。

## 目录
`stage2/` 阶段二工作流（未启用）· `models.py` 冻结模型 · `pl3_lab.py` 同步/锁定/校验/审计/统计 · `attest.py` RFC 3161 · `sources.py` 数据源 ·
`stats_exact.py` 精确二项与 Holm · `check_append_only.py` 推送前追加检查 · `backtest_randomness.py` 回溯 R1（需 numpy+scipy）·
`data/` 只读快照与上游许可证 · `records/` 只追加账本 · `tsa/` 时间戳配置 · `tests/` 离线测试。
