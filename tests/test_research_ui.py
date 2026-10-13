"""Exercise the real desktop buttons when Tk has a display available."""
import time

import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("factor_qc")
from tkinter import messagebox, ttk
from holdout_governance import research_ui


def test_desktop_search_freeze_evaluate(tmp_path, monkeypatch):
    try:
        app = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    app.withdraw()
    monkeypatch.setattr(tk, "Tk", lambda: app)
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda *args: errors.append(args))
    started = time.monotonic()
    stage = 0
    def widgets(parent):
        for w in parent.winfo_children():
            yield w
            yield from widgets(w)
    def drive():
        nonlocal stage
        try:
            buttons = {str(w.cget("text")): w for w in widgets(app) if isinstance(w, ttk.Button)}
            if errors or time.monotonic()-started > 30:
                app.destroy()
                return
            if stage == 0:
                buttons["1  开始新研究"].invoke()
                stage = 1
            elif stage == 1 and not buttons["2  冻结候选"].instate(["disabled"]):
                buttons["2  冻结候选"].invoke()
                stage = 2
            elif stage == 2 and not buttons["3  最终评估（一次）"].instate(["disabled"]):
                buttons["3  最终评估（一次）"].invoke()
                stage = 3
            elif stage == 3 and not buttons["打开报告"].instate(["disabled"]):
                assert buttons["3  最终评估（一次）"].instate(["disabled"])
                stage = 4
                app.destroy()
                return
        except Exception as exc:
            errors.append(str(exc))
            app.destroy()
            return
        app.after(60, drive)
    app.after(100, drive)
    research_ui.launch(tmp_path)
    assert not errors
    assert stage == 4, "desktop did not complete all three real actions"
    assert len(list(tmp_path.glob("run-*/report.html"))) == 1
