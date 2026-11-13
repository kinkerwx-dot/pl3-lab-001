# 第三方时间戳（TSA）配置

没有这里的配置，所有预测都只能是**观察记录**（设计如此）。需要的文件（由你放入仓库；不要让工作流在运行时下载，以免首次信任）：
- `config.json`：`{"url": "<TSA 的 RFC 3161 地址>", "cafile": "tsa/ca.pem", "untrusted": "tsa/tsa.crt"}`（`untrusted` 可省略）
- `ca.pem`：TSA 根证书；`tsa.crt`：TSA 签名证书（令牌已内带证书时也建议钉扎）。

## 阶段一测试服务：FreeTSA.org（用户已批准）
已随包提供 `config.json`（入口 `https://freetsa.org/tsr`，`pinned: true`）与 `pins.json`（SHA-256 由用户从官网取得）。证书文件本身**不在包内**：运行 `bash tsa/download_and_check.sh` 下载并比对。
以下来自外部审计报告对 FreeTSA 官方资料的核对，**我自己没能联网验证**（沙盒 DNS 无法解析 freetsa.org）：
- HTTPS 入口 `https://freetsa.org/tsr`；根证书 `https://freetsa.org/files/cacert.pem`；签名证书 `https://freetsa.org/files/tsa.crt`。
- 官方公告当前签名证书于 2026 年 3 月轮换，有效期至 2040 年 2 月。
- 请你按官网公布的 SHA-256 核对下载文件，把根证书与允许的签名证书**钉扎**进仓库，并按版本保存（便于轮换后仍能验证旧令牌）。

## 本项目的验证做了什么、没做什么
- 做了：签名、证书链到钉扎的 CA、摘要等于预测链尾、证书在**令牌签发时刻**有效（`-attime`）、令牌日期=北京时间开奖日、早于内部截止。
- **没做：** 证书吊销检查（OCSP/CRL）；证书用途之外的策略 OID 白名单。这些是已披露的局限。
- `conn-test` 只用固定测试文本的摘要请求令牌，验证后输出 `TSA 签发并验证 -> PASS`。
