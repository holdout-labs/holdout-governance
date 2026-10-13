"""Local desktop controls; no web service, credentials or cloud dependencies."""
from __future__ import annotations

import argparse
import importlib
import queue
import sys
import threading
import uuid
import webbrowser
from pathlib import Path


def default_directory():
    """Installed launchers use one stable location, independent of the shell cwd."""
    return Path.home() / ".holdout" / "research-runs"


def check_environment():
    for name in ("tkinter", "numpy", "jsonschema", "yaml", "factor_qc", "lookahead_free", "falsification_ledger", "lesson_book"):
        importlib.import_module(name)
    from .research import runtime_versions
    runtime_versions()


def main(argv=None):
    parser = argparse.ArgumentParser(description="打开本地合成因子研究工作台")
    parser.add_argument("--dir", type=Path, default=default_directory(), help="保存研究的目录")
    parser.add_argument("--check", action="store_true", help="只检查运行环境，不开启研究或窗口")
    args = parser.parse_args(argv)
    try:
        check_environment()
    except ImportError as exc:
        if getattr(exc, "name", None) in {"tkinter", "_tkinter"}:
            message = "当前 Python 缺少 Tkinter 桌面支持，请安装带 Tcl/Tk 的 Python 3.11 或更新版本。"
        else:
            message = ('研究依赖尚未安装。请在项目目录运行：python -m pip install -e ".[research]"。'
                       '本次构建包的依赖也可安装：python -m pip install numpy jsonschema pyyaml factor-qc lookahead-free falsification-ledger lesson-book。')
        print(message, file=sys.stderr)
        return 2
    if args.check:
        print("研究运行环境已就绪；没有创建研究或使用最终测试数据。")
        return 0
    try:
        launch(args.dir)
    except Exception as exc:
        print(f"工作台未能打开：{exc}。请在可显示桌面窗口的电脑运行，研究记录不会因此清零。", file=sys.stderr)
        return 2
    return 0


def launch(directory=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from . import research
    directory = Path(directory or default_directory()).resolve()
    app = tk.Tk()
    app.title("Holdout · 因子研究工作台")
    app.geometry("1160x790")
    app.minsize(850, 600)
    app.configure(bg="#f4f5f0")
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure("TFrame", background="#f4f5f0")
    style.configure("TLabel", background="#f4f5f0", foreground="#193c32", font=("Microsoft YaHei UI", 10))
    style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=8)
    style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 9))
    style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
    outer = ttk.Frame(app, padding=22)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="HOLDOUT  /  因子研究", font=("Microsoft YaHei UI", 23, "bold")).pack(anchor="w")
    ttk.Label(outer, text="合成数据 · 固定规则自动搜索 · 内置可学习信号 · 不连接真实账户").pack(anchor="w", pady=(3, 14))
    form = ttk.Frame(outer)
    form.pack(fill="x")
    family = tk.StringVar(value="放量滞涨")
    families = {"放量滞涨": "volume_stall", "短期动量": "momentum", "短期反转": "reversal"}
    ttk.Label(form, text="研究方向").grid(row=0, column=0, sticky="w")
    family_box = ttk.Combobox(form, textvariable=family, values=list(families), state="readonly", width=12)
    family_box.grid(row=1, column=0, padx=(0, 12))
    question = tk.StringVar(value=research.QUESTIONS["volume_stall"])
    ttk.Label(form, text="研究问题（用于登记；方向决定候选库）").grid(row=0, column=1, sticky="w")
    question_box = ttk.Entry(form, textvariable=question)
    question_box.grid(row=1, column=1, sticky="ew", padx=(0, 12))
    form.columnconfigure(1, weight=1)
    ttk.Label(form, text="最多试验次数").grid(row=0, column=2, sticky="w")
    budget = tk.StringVar(value="30")
    budget_box = ttk.Spinbox(form, from_=12, to=100, textvariable=budget, width=8)
    budget_box.grid(row=1, column=2)
    family_box.bind("<<ComboboxSelected>>", lambda e: question.set(research.QUESTIONS[families[family.get()]]))
    toolbar = ttk.Frame(outer)
    toolbar.pack(fill="x", pady=14)
    status = tk.StringVar(value="输入问题后开始研究。结果自动保存在本机，下次可以继续打开。")
    ttk.Label(outer, textvariable=status, wraplength=1050).pack(anchor="w", pady=(0, 8))
    bar = ttk.Progressbar(outer, mode="determinate", maximum=100)
    bar.pack(fill="x", pady=(0, 12))
    table_frame = ttk.Frame(outer)
    table_frame.pack(fill="both", expand=True)
    columns = ("id", "stage", "operation", "features", "sharpe", "outcome")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
    for col, title, width in zip(columns, ["候选", "阶段", "动作", "因子输入", "反馈 Sharpe", "结果"], [55, 90, 85, 210, 105, 410]):
        tree.heading(col, text=title)
        tree.column(col, width=width, minwidth=45)
    scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)
    detail = tk.Text(outer, height=7, wrap="word", font=("Microsoft YaHei UI", 10), bg="#fff", relief="flat", padx=10, pady=8)
    detail.pack(fill="x", pady=(12, 0))
    detail.insert("1.0", "点击候选查看公式、模型参数与淘汰原因。\n最终测试只在‘冻结候选’后开放一次。\n这是本地受控演示，不是操作系统级沙箱；不对不受信任的程序授予研究目录访问权限。")
    detail.configure(state="disabled")
    current = {"path": None, "state": None, "busy": False, "test_available": False}
    messages = queue.Queue()

    def show_detail(text):
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", text)
        detail.configure(state="disabled")

    def insert(t):
        tree.insert("", "end", iid=str(t["id"]), values=(t["id"], research.STAGES[t["stage"]], t["operation"],
                    ", ".join(research.FEATURE_LABELS[n] for n in t["candidate"]["features"]), f'{t["feedback"]["sharpe"]:.2f}' if "feedback" in t else "—", t.get("outcome", "计算中")))
        tree.see(str(t["id"]))

    def selected(event=None):
        if not current["state"] or not tree.selection():
            return
        index = int(tree.selection()[0])-1
        t = current["state"]["trials"][index]
        formulas = "；".join(f'{research.FEATURE_LABELS[n]} = {research.FORMULAS.get(n, "未来收益标签，禁止使用")}' for n in t["candidate"]["features"])
        show_detail(f'{t["reason"]}\n{t.get("outcome", "")}\n公式：{formulas}\n模型：先用训练期均值和标准差统一输入尺度，再加权求和；正则强度 {t["candidate"]["ridge"]}。完整系数在报告中。\n候选指纹：{t["candidate_hash"]}')
    tree.bind("<<TreeviewSelect>>", selected)

    def refresh():
        if current["path"]:
            s = research.inspect(current["path"])
            current["state"] = s
            tree.delete(*tree.get_children())
            for t in s["trials"]:
                insert(t)
            bar["value"] = len(s["trials"])/s["plan"]["budget"]*100
            status.set(f'{research.PHASES[s["phase"]]}  |  已用 {len(s["trials"])}/{s["plan"]["budget"]} 次  |  测试访问 {s["evaluation_count"]} 次  |  候选 {s["selected"] or "无"}')
            custody = research.audit(current["path"])
            current["test_available"] = custody["registry"].get("available", False)
            if not current["test_available"] and not s["final"]:
                if custody["registry_error"]:
                    reason = "测试登记处不可用；请保留现有记录并恢复原登记处，不能换空库。"
                elif s["evaluation_count"]:
                    reason = "本轮最终测试机会已消耗；失败或重启也不能重试。"
                else:
                    reason = "同一或重叠测试样本已有使用记录；搜索可以继续，不能再次作为独立测试。"
                status.set(status.get() + "\n" + reason)
            if s["final"]:
                f = s["final"]
                show_detail(f'最终结果（合成数据）：日均扣费收益年化 {f["annual_mean"]:.2%}；成本翻倍 {f["stress_annual_mean"]:.2%}；最大回撤 {f["max_drawdown"]:.2%}。\n预注册标准：{"满足" if all(f["outcomes"].values()) else "未全部满足，不能放行"}。最终评估不等于人工批准。\n完整公式、窗口和证据见“打开报告”。')
        controls()

    def controls():
        busy = current["busy"]
        phase = (current["state"] or {}).get("phase")
        for button in (start_button, load_button):
            button.configure(state="disabled" if busy else "normal")
        search_button.configure(state="normal" if not busy and phase == "ready" else "disabled")
        freeze_button.configure(state="normal" if not busy and phase == "searched" and current["state"]["selected"] else "disabled")
        eval_button.configure(state="normal" if not busy and phase == "frozen" and current["test_available"] else "disabled")
        report_button.configure(state="normal" if not busy and current["path"] else "disabled")

    def work(fn):
        current["busy"] = True
        controls()
        def execute():
            try:
                fn()
                messages.put(("done", None))
            except Exception as exc:
                messages.put(("error", str(exc)))
        threading.Thread(target=execute, daemon=False).start()

    def start():
        try:
            number = int(budget.get())
            text = question.get().strip()
            if not text or len(text) > 500 or not 12 <= number <= 100:
                raise ValueError()
        except ValueError:
            messagebox.showerror("检查输入", "问题不能为空且最多500字；次数应为12到100的整数。")
            return
        target = Path(directory).resolve()/f'run-{research.now()[:10]}-{uuid.uuid4().hex[:8]}'
        key = families[family.get()]
        tree.delete(*tree.get_children())
        current.update(path=None, state=None)
        status.set("正在登记方案并准备合成数据…")
        def execute():
            research.create(target, text, number, key)
            messages.put(("created", target))
            research.search(target, lambda t: messages.put(("trial", t)))
        work(execute)

    def load():
        path = filedialog.askopenfilename(title="选择已有研究的 research.sqlite", initialdir=str(Path(directory).resolve()), filetypes=[("研究记录", "*.sqlite")])
        if path:
            try:
                research.inspect(Path(path).parent)
                current["path"] = Path(path).parent
                research.render(current["path"])
                refresh()
            except Exception as exc:
                messagebox.showerror("无法打开研究", str(exc))

    start_button = ttk.Button(toolbar, text="1  开始新研究", command=start)
    start_button.pack(side="left", padx=(0, 8))
    search_button = ttk.Button(toolbar, text="继续搜索", command=lambda: work(lambda: research.search(current["path"], lambda t: messages.put(("trial", t)))))
    search_button.pack(side="left", padx=(0, 8))
    freeze_button = ttk.Button(toolbar, text="2  冻结候选", command=lambda: work(lambda: research.freeze(current["path"])))
    freeze_button.pack(side="left", padx=(0, 8))
    eval_button = ttk.Button(toolbar, text="3  最终评估（一次）", command=lambda: work(lambda: research.evaluate(current["path"])))
    eval_button.pack(side="left", padx=(0, 8))
    report_button = ttk.Button(toolbar, text="打开报告", command=lambda: webbrowser.open((current["path"]/"report.html").as_uri()))
    report_button.pack(side="left", padx=(0, 8))
    load_button = ttk.Button(toolbar, text="打开已有研究", command=load)
    load_button.pack(side="right")

    def poll():
        while not messages.empty():
            kind, value = messages.get()
            if kind == "created":
                current["path"] = value
            elif kind == "trial":
                insert(value)
                status.set(f'正在{research.STAGES[value["stage"]]} · 第 {value["id"]} 次 · {value.get("outcome", "")}')
            else:
                current["busy"] = False
                try:
                    refresh()
                except Exception as exc:
                    status.set(str(exc))
                    controls()
                if kind == "error":
                    messagebox.showerror("研究已停止，记录保留", value)
        app.after(150, poll)
    def close():
        if current["busy"]:
            messagebox.showinfo("研究正在计算", "请等待当前操作完成，试验记录会自动保存。")
        else:
            app.destroy()
    app.protocol("WM_DELETE_WINDOW", close)
    controls()
    app.after(150, poll)
    app.mainloop()


if __name__ == "__main__":
    raise SystemExit(main())
