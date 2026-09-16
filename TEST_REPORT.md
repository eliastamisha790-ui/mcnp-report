# MCNP Report v0.2.1 测试报告

测试日期：2026-09-15  
平台：Windows 11 x64  
解析器目标：MCNP6, 1.0 固定源、光子 F4 tally

## 自动化测试

执行 `python -m pytest tests -q`，结果为 **29 passed**。

覆盖内容：

- MCNP 隐式指数（`1.58-01`、`5.01-05`、`1.00+00`）与首列 ASA 打印控制字符。
- 外部真实样本 `D:\mcnpproject\1.out` 和 `D:\mcnpproject\ceshi.out`；未复制原始输出到工程。
- 10,000,000 histories、F4 total `4.95542E-04`、相对误差 `0.0035`、2,003 条 tally 记录、6 条 warning。
- `1.out`：`0.15 min`、最终 FOM `544429`、未通过 1 项检查。
- `ceshi.out`：`1.58 min`、最终 FOM `52649`、未通过 2 项检查。
- PRINT 60/100/101/126/160/161、10 项统计检查、20 个 TFC 点和 51 条 tally density 记录。
- 截断文件、未知分页段、错误版本和 KCODE 拒绝路径。
- AI 适配器成功、provider 超时、本地降级、required 失败以及未获事实支持的数字拦截。
- OpenAI-compatible `extra_body` 请求参数透传；DeepSeek `deepseek-flash` 关闭思考模式后的真实结构化摘要调用状态为 `ok`，并通过事实 ID 与数字校验。
- GUI 参数校验、拖放路径预填、后台任务调用和友好错误信息。
- 可重复生成的合成回归语料：正常低误差、高误差/零分箱、稳定高精度、截断、未知表和错误版本；这些文件不作为物理结果或模型训练数据。
- 配置优先级：环境变量高于指定 TOML，指定 TOML 高于用户配置。
- Excel 数值类型、7 张工作表、2 个原生图表、自动拆分 Tally 结果表和重复输出保护。
- 约 100 MB 合成输出流式解析，峰值内存断言低于 512 MB。

## 工作簿验收

使用 Artifact Tool 重新打开 `examples\sample_report.xlsx`，完成一次 recalculation、关键区域检查和公式错误扫描。结果：

- 工作表：`总览`、`Tally结果`、`统计诊断`、`粒子与单元`、`核数据库`、`输入清单`、`解析审计`。
- 关键值与源文件一致，Tally 数值保持数值类型。
- `总览`包含 TFC 均值收敛和 FOM 两个可编辑 Excel 图表。
- 公式错误扫描：0 项。
- 逐表渲染检查通过；未发现截断标题、`####`、空白图表或对象重叠。

## EXE 验收

- PyInstaller 单文件构建成功，CLI `dist\mcnp-report.exe` 可独立启动并返回版本 `0.2.1`。
- 无控制台窗口的 `dist\mcnp-report-gui.exe` 启动冒烟测试退出码为 0，并验证把 `1.out` 作为拖放等价参数时可自动预填路径。
- 在包含中文和空格的临时路径中以拖放等价参数运行真实样本成功。
- 重新打开 EXE 生成的 `ceshi.out` 报告，确认 `1.58 min`、FOM `52649`、未通过 2 项检查、2,003 条 tally 记录和 2 个图表。
- 隔离 `%APPDATA%` 后，`init-config` 成功；无密钥的 `--ai required` 返回退出码 6，且不生成工作簿。

## 交付哈希

- `dist\mcnp-report.exe`：SHA-256 `65C5E45FCAEA95227FF870E97489299719DF46E693F823374797EE9CAEF8C605`，10,131,497 bytes。
- `dist\mcnp-report-gui.exe`：SHA-256 `985E675E62EE9E9599D12DD2731FEC69BA65BCC81540BA7F4C6B989D8F5DB47A`，13,357,669 bytes。
- `examples\sample_report.xlsx`：SHA-256 `195B2932B8996CCA7EC398695EF8DBF99E4CF52C8BD5E50858FB96502DAB28AE`，141,099 bytes。

## 已知边界

本版本不会尝试解释 MCNP5、MCNP6.2/6.3、KCODE、FMESH、MCTAL、MESHTAL、PTRAC 或非 F4 tally。未知分页段在非严格模式下进入解析审计，在严格模式下返回退出码 4。
