from __future__ import annotations

import ctypes
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .config import user_config_path
from .errors import AIProviderError, ConfigurationError, PartialParseError, UnsupportedVersionError, WorkbookError
from .service import AnalysisOutcome, AnalysisRequest, analyze_file, default_output_path


BLUE = "#17365D"
MID_BLUE = "#4472C4"
PALE = "#EAF2F8"
TEXT = "#1F2937"


def _initial_input(argv: list[str]) -> str:
    for value in argv:
        path = Path(value.strip('"')).expanduser()
        if path.suffix.lower() == ".out" and path.is_file():
            return str(path.resolve())
    return ""


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, UnsupportedVersionError): return "文件或版本不支持：" + str(exc)
    if isinstance(exc, PartialParseError): return "严格解析未通过：" + str(exc)
    if isinstance(exc, AIProviderError): return "AI 调用失败：" + str(exc)
    if isinstance(exc, WorkbookError): return "Excel 写入失败：" + str(exc)
    if isinstance(exc, ConfigurationError): return "配置错误：" + str(exc)
    return f"处理失败：{exc}"


class McnpReportApp:
    def __init__(self, root: tk.Tk, initial_input: str = "") -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_output: Path | None = None
        self.running = False

        root.title(f"MCNP 输出中文报告  v{__version__}")
        root.geometry("840x650")
        root.minsize(760, 590)
        root.configure(bg="#F5F7FA")
        self._configure_style()
        self._build_ui()
        if initial_input:
            self.input_var.set(initial_input)
            self.output_var.set(str(default_output_path(initial_input)))
            self._log(f"已读取拖放文件：{initial_input}")
        self._refresh_ai_hint()
        self.root.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names(): style.theme_use("vista")
        style.configure("TFrame", background="#F5F7FA")
        style.configure("Card.TLabelframe", background="#FFFFFF", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#F5F7FA", foreground=BLUE, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabel", background="#F5F7FA", foreground=TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(9, 5))
        style.configure("TCheckbutton", background="#F5F7FA", foreground=TEXT, font=("Microsoft YaHei UI", 9))

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BLUE, height=78)
        header.pack(fill="x")
        tk.Label(header, text="MCNP 输出中文报告", bg=BLUE, fg="white", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", padx=26, pady=(14, 1))
        tk.Label(header, text="MCNP6, 1.0 固定光子源 F4 tally", bg=BLUE, fg="#D9EAF7", font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=27)

        body = ttk.Frame(self.root, padding=(22, 16, 22, 14)); body.pack(fill="both", expand=True)
        file_card = ttk.LabelFrame(body, text=" 文件 ", style="Card.TLabelframe", padding=12); file_card.pack(fill="x")
        file_card.columnconfigure(1, weight=1)
        self.input_var = tk.StringVar(); self.output_var = tk.StringVar()
        ttk.Label(file_card, text="MCNP 输出").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(file_card, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Button(file_card, text="选择 .out", command=self._choose_input).grid(row=0, column=2, padx=(8, 0), pady=5)
        ttk.Label(file_card, text="Excel 报告").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(file_card, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Button(file_card, text="选择位置", command=self._choose_output).grid(row=1, column=2, padx=(8, 0), pady=5)

        ai_card = ttk.LabelFrame(body, text=" AI 中文解读（可选） ", style="Card.TLabelframe", padding=12); ai_card.pack(fill="x", pady=(13, 0))
        ai_card.columnconfigure(3, weight=1)
        self.ai_var = tk.StringVar(value="auto"); self.profile_var = tk.StringVar(value="default"); self.config_var = tk.StringVar()
        ttk.Label(ai_card, text="模式").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(ai_card, textvariable=self.ai_var, values=("auto", "off", "required"), state="readonly", width=12).grid(row=0, column=1, sticky="w", padx=(8, 22), pady=4)
        ttk.Label(ai_card, text="Profile").grid(row=0, column=2, sticky="w", pady=4)
        ttk.Entry(ai_card, textvariable=self.profile_var, width=22).grid(row=0, column=3, sticky="w", padx=(8, 0), pady=4)
        ttk.Label(ai_card, text="TOML 配置").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(ai_card, textvariable=self.config_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 8), pady=4)
        ttk.Button(ai_card, text="选择配置", command=self._choose_config).grid(row=1, column=4, pady=4)
        self.ai_hint = ttk.Label(ai_card, text="", foreground="#5B6472"); self.ai_hint.grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))

        option_row = ttk.Frame(body); option_row.pack(fill="x", pady=(13, 8))
        self.strict_var = tk.BooleanVar(value=False); self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(option_row, text="严格解析（未识别段直接失败）", variable=self.strict_var).pack(side="left")
        ttk.Checkbutton(option_row, text="允许覆盖已有报告", variable=self.overwrite_var).pack(side="left", padx=(22, 0))

        action_row = ttk.Frame(body); action_row.pack(fill="x", pady=(0, 10))
        self.run_button = ttk.Button(action_row, text="生成 Excel 报告", style="Primary.TButton", command=self._start)
        self.run_button.pack(side="left")
        self.open_button = ttk.Button(action_row, text="打开生成的报告", command=self._open_output, state="disabled"); self.open_button.pack(side="left", padx=(10, 0))
        ttk.Button(action_row, text="AI 配置说明", command=self._open_help).pack(side="right")

        self.progress = ttk.Progressbar(body, mode="indeterminate"); self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(body, textvariable=self.status_var, foreground=BLUE).pack(anchor="w", pady=(5, 5))
        log_card = ttk.LabelFrame(body, text=" 处理日志 ", style="Card.TLabelframe", padding=8); log_card.pack(fill="both", expand=True)
        self.log = tk.Text(log_card, height=10, wrap="word", state="disabled", bg="#FFFFFF", fg=TEXT, relief="flat", font=("Microsoft YaHei UI", 9), padx=8, pady=7)
        scroll = ttk.Scrollbar(log_card, command=self.log.yview); self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")

    def _choose_input(self) -> None:
        selected = filedialog.askopenfilename(title="选择 MCNP 输出", filetypes=[("MCNP output", "*.out"), ("所有文件", "*.*")])
        if selected:
            self.input_var.set(selected); self.output_var.set(str(default_output_path(selected)))

    def _choose_output(self) -> None:
        initial = self.output_var.get().strip() or "mcnp_report.xlsx"
        selected = filedialog.asksaveasfilename(title="保存 Excel 报告", initialfile=Path(initial).name, defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if selected: self.output_var.set(selected)

    def _choose_config(self) -> None:
        selected = filedialog.askopenfilename(title="选择 AI TOML 配置", filetypes=[("TOML", "*.toml"), ("所有文件", "*.*")])
        if selected: self.config_var.set(selected); self._refresh_ai_hint()

    def _refresh_ai_hint(self) -> None:
        configured = bool(self.config_var.get().strip()) or user_config_path().is_file()
        self.ai_hint.configure(text=("AI 配置已检测。密钥仅从配置指定的环境变量读取。" if configured else "当前未检测到 AI 配置。auto 会自动使用本地规则结论，off 完全离线。"))

    def _start(self) -> None:
        if self.running: return
        source = self.input_var.get().strip(); output = self.output_var.get().strip()
        if not source:
            messagebox.showwarning("缺少文件", "请先选择一个 MCNP .out 文件。"); return
        if not output: output = str(default_output_path(source)); self.output_var.set(output)
        request = AnalysisRequest(source, output, self.ai_var.get(), self.profile_var.get().strip() or None, self.config_var.get().strip() or None, self.strict_var.get(), self.overwrite_var.get())
        self.running = True; self.run_button.configure(state="disabled"); self.open_button.configure(state="disabled")
        self.progress.start(12); self.status_var.set("正在处理…"); self._log("开始分析。")
        threading.Thread(target=self._worker, args=(request,), daemon=True).start()

    def _worker(self, request: AnalysisRequest) -> None:
        try:
            outcome = analyze_file(request, lambda stage, message: self.events.put(("progress", message)))
            self.events.put(("success", outcome))
        except Exception as exc:
            self.events.put(("error", exc))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress": self.status_var.set(str(payload)); self._log(str(payload))
                elif kind == "success": self._finished(payload)
                elif kind == "error": self._failed(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _finished(self, outcome: AnalysisOutcome) -> None:
        self.running = False; self.progress.stop(); self.run_button.configure(state="normal"); self.open_button.configure(state="normal")
        self.last_output = outcome.output_path
        summary = f"完成：{outcome.tally_rows:,} 条 tally，{outcome.tfc_points} 个 TFC 点，{outcome.warning_count} 条警告。"
        if outcome.ai_error: summary += " AI 未可用，已使用本地规则。"
        self.status_var.set(summary); self._log(summary); self._log(str(outcome.output_path))
        messagebox.showinfo("报告已生成", summary)

    def _failed(self, exc: Exception) -> None:
        self.running = False; self.progress.stop(); self.run_button.configure(state="normal")
        message = _friendly_error(exc); self.status_var.set(message); self._log(message); messagebox.showerror("处理失败", message)

    def _open_output(self) -> None:
        if self.last_output and self.last_output.is_file(): os.startfile(self.last_output)

    def _open_help(self) -> None:
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.extend([Path(sys.executable).resolve().parent.parent / "README.md", Path(getattr(sys, "_MEIPASS", "")) / "README.md"])
        candidates.append(Path(__file__).resolve().parents[2] / "README.md")
        for path in candidates:
            if path.is_file(): os.startfile(path); return
        messagebox.showinfo("AI 配置", f"请查看 config.example.toml，用户配置路径：\n{user_config_path()}")

    def _log(self, text: str) -> None:
        self.log.configure(state="normal"); self.log.insert("end", text + "\n"); self.log.see("end"); self.log.configure(state="disabled")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    if "--smoke-test" in args:
        root.withdraw()
        initial_input = _initial_input([arg for arg in args if arg != "--smoke-test"])
        app = McnpReportApp(root, initial_input)
        root.update_idletasks()
        valid = not initial_input or app.input_var.get() == initial_input
        root.destroy()
        return 0 if valid else 1
    McnpReportApp(root, _initial_input(args)); root.mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
