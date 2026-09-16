# MCNP 输出解析工具（GUI + CLI）

`mcnp-report` 将 MCNP6, 1.0 固定源 `.out` 文件流式解析为面向核工程人员的中文 Excel 报告。同时提供 Windows 图形界面和 CLI。程序不依赖 AI 才能工作；AI 不可用时会自动生成规则化中文结论。

## 图形界面

双击 `dist\mcnp-report-gui.exe`，选择 `.out` 文件和 Excel 保存位置，然后点击“生成 Excel 报告”。GUI 支持：

- `auto` / `off` / `required` AI 模式、profile 和自定义 TOML。
- 严格解析、覆盖保护、分阶段进度和处理日志。
- 完成后直接打开 Excel 报告。
- 把 `.out` 文件拖到 GUI EXE 图标上时，程序会自动填入文件路径。

## CLI 快速使用

免安装版：把一个 `.out` 文件拖到 `dist\mcnp-report.exe` 上，或在 PowerShell 中运行：

```powershell
.\dist\mcnp-report.exe analyze "D:\mcnpproject\1.out" --ai off
```

默认在原文件旁生成 `<文件名>_mcnp_report.xlsx`。若同名文件已存在，会加时间戳保护原报告。

完整命令：

```text
mcnp-report analyze INPUT [-o OUTPUT] [--ai auto|off|required]
                    [--profile NAME] [--config PATH] [--strict] [--overwrite]
```

- `--ai auto`：默认。AI 成功时使用模型结论；失败时仍生成本地规则报告。
- `--ai off`：完全离线，不调用模型。
- `--ai required`：模型失败时退出，不生成报告。
- `--strict`：必要字段缺失或出现未知分页段时终止。
- `--overwrite`：允许覆盖指定的现有 Excel。

退出码：`0` 成功、`2` 配置错误、`3` 文件或版本不支持、`4` 严格解析失败、`5` Excel 写入失败、`6` 必需 AI 调用失败。

## Excel 内容

- `总览`：运行状态、NPS、计算时间、F4 总值与误差、AI/规则中文结论、TFC 与 FOM 图表。
- `Tally结果`：能量分箱、结果、相对误差、质量标记与源行号；超出 Excel 上限时自动拆表。
- `统计诊断`：10 项检查、TFC 序列、PRINT 160、PRINT 161。
- `粒子与单元`：PRINT 60/101/126 以及粒子产生和损失。
- `核数据库`：XSDIR、截面表、库文件和日期。
- `输入清单`：输入卡、类别和中文说明。
- `解析审计`：文件哈希、编码、段落覆盖率、行号范围、诊断和版本限制。

数值以真正的 Excel 数值保存；原始卡片和标识符保留为文本。

## AI 配置与隐私

复制 `config.example.toml` 后修改。优先级从高到低为：命令参数、环境变量、`--config` 指定 TOML、用户配置、默认值。用户配置路径为 `%APPDATA%\mcnp-report\config.toml`，可用 `mcnp-report init-config` 创建。

API 密钥只从 `api_key_env` 指定的环境变量读取。程序默认只发送本地提取的事实摘要，不发送完整输出、输入卡或核数据库路径。OpenAI-compatible 服务支持 `chat_completions` 和 `responses` endpoint；非标准服务可参考 `examples\custom_adapter.py`。外部适配器会作为可信 Python 代码执行，只加载自己审核过的文件。

对于需要额外请求参数的兼容服务，可在 profile 中配置 `extra_body`。例如 DeepSeek 的 `deepseek-flash` 可通过 `[ai.profiles.<名称>.extra_body.thinking] type = "disabled"` 禁用思考模式，确保为结构化报告保留完整输出额度。

初始交付没有预置任何 API 密钥或真实模型地址。因此 `auto` 默认会降级到本地规则，`off` 完全离线，只有完成配置后才会真正调用 AI。

## 合成回归语料

`training_data\synthetic` 包含正常低误差、高误差/零分箱、稳定高精度、截断、错误版本和未知表等合成 `.out`。这些数据只用于软件回归测试，不是真实 MCNP 结果，不得用于工程或安全判断。可运行 `python tools\generate_synthetic_outputs.py` 重新生成。

## 从源码运行与构建

要求 Python 3.11+：

```powershell
python -m pip install -e .
mcnp-report analyze "D:\mcnpproject\1.out" --ai off
python -m pytest
.\build_exe.ps1
```

构建脚本使用 PyInstaller 同时生成 `dist\mcnp-report-gui.exe` 和 `dist\mcnp-report.exe`。如果 XlsxWriter 安装在额外目录，可传入 `-XlsxWriterPath`。

## v1 支持边界

只支持样本对应的 `MCNP6, 1.0` 固定源输出及 F4 tally。MCNP5、MCNP6.2/6.3、KCODE、FMESH、MCTAL、MESHTAL、PTRAC 和其他 tally 类型会拒绝或在审计中明确标记，不会输出未经验证的数据。

测试直接读取 `D:\mcnpproject\1.out` 与 `D:\mcnpproject\ceshi.out`，不会把原始 `.out` 复制进工程。
