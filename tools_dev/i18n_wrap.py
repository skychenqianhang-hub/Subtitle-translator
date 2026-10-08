"""开发工具：把代码里的中文界面文字自动包上 tr()，并导出需要翻译的文字清单。

用法（在项目根目录）：
    python tools_dev/i18n_wrap.py --dry      只统计，不改文件
    python tools_dev/i18n_wrap.py            实际改写文件
    python tools_dev/i18n_wrap.py --extract  不改文件，只从已经包好 tr() 的代码里导出清单到 app/locales/_keys.json

规则：
- 只处理函数体里面的字符串。模块级 / 类级的常量、函数的默认参数在 import 时就求值，不自动包，列出来人工处理。
- 文档字符串不动。
- f-string 转成「模板 + 位置参数」：f"已保存：{p.name}" → tr("已保存：{0}", p.name)
- SKIP_EXACT / SKIP_CONTAINS 里的不动（场景的内部名字、发给翻译模型的提示词等）。
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = [
    "app/ui/common.py", "app/ui/main_window.py", "app/ui/model_panel.py", "app/ui/output_mode.py",
    "app/ui/overlay_window.py", "app/ui/profiles_page.py", "app/ui/realtime_page.py", "app/ui/scene_picker.py",
    "app/ui/settings_dialog.py", "app/ui/settings_page.py", "app/ui/subtitle_editor.py", "app/ui/video_page.py",
    "app/ui/tone_picker.py", "app/ui/glossary_generate_dialog.py", "app/core/profiles/generate.py",
    "app/core/errors.py", "app/core/download.py", "app/core/cost.py", "app/core/subtitle/burn.py",
    "app/core/subtitle/document.py", "app/core/subtitle/project.py", "app/core/audio/extract.py",
    "app/core/audio/capture.py", "app/core/profiles/store.py", "app/core/profiles/glossary_io.py",
    "app/core/pipeline/video_pipeline.py", "app/core/pipeline/live_pipeline.py", "app/core/asr/openai_asr.py",
    "app/core/asr/registry.py", "app/core/translate/anthropic_translate.py",
    "app/core/translate/openai_translate.py", "app/core/translate/registry.py",
]
# 只做导出（这些文件里的文字在使用处用 tr(变量) 翻译，键在这里以常量形式存在）
EXTRACT_CONSTANTS_FROM = ["app/config.py", "app/core/subtitle/style.py", "app/core/subtitle/ass.py"]

EXTRACT_MODULE_CONSTANTS_FROM = ["app/ui/main_window.py", "app/ui/video_page.py", "app/ui/theme.py"]

HAN = re.compile(r"[㐀-鿿]")
SKIP_EXACT = {"通用"}
SKIP_CONTAINS = ["上一次返回的句数不对", "必须恰好返回"]   # 追加给翻译模型的话，不是界面文字


def has_han(s: str) -> bool:
    return bool(HAN.search(s))


def py_literal(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


class Finder(ast.NodeVisitor):
    def __init__(self, src: str) -> None:
        self.src = src
        self.stack: list[ast.AST] = []
        self.replacements: list[tuple[ast.AST, str, str]] = []   # (node, new_code, key)
        self.manual: list[tuple[int, str]] = []
        self.docstrings: set[int] = set()

    def _mark_docstring(self, node) -> None:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            self.docstrings.add(id(body[0].value))

    def generic_visit(self, node) -> None:
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            self._mark_docstring(node)
        self.stack.append(node)
        super().generic_visit(node)
        self.stack.pop()

    def _in_function_body(self, node) -> bool:
        """在某个函数体内（不是默认参数、不是装饰器）。"""
        for i in range(len(self.stack) - 1, -1, -1):
            anc = self.stack[i]
            if isinstance(anc, ast.Lambda):
                return True
            if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child = self.stack[i + 1] if i + 1 < len(self.stack) else node
                return not isinstance(child, ast.arguments) and child not in anc.decorator_list
            if isinstance(anc, ast.ClassDef):
                return False
        return False

    def _already_wrapped(self, node) -> bool:
        if not self.stack:
            return False
        parent = self.stack[-1]
        return isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "tr" \
            and parent.args and parent.args[0] is node

    def _skip(self, text: str) -> bool:
        return text in SKIP_EXACT or any(s in text for s in SKIP_CONTAINS)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or not has_han(node.value):
            return
        if id(node) in self.docstrings or self._skip(node.value):
            return
        if any(isinstance(a, ast.JoinedStr) for a in self.stack):
            return                       # f-string 里面的片段：由 visit_JoinedStr 整体处理
        if self._already_wrapped(node):
            return
        if not self._in_function_body(node):
            self.manual.append((node.lineno, node.value))
            return
        self.replacements.append((node, f"tr({py_literal(node.value)})", node.value))

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        consts = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
        if not has_han(consts):
            self.generic_visit(node)
            return
        if self._skip(consts):
            return
        if any(isinstance(a, ast.JoinedStr) for a in self.stack):
            return                       # 嵌套在别的 f-string 的格式说明里
        if not self._in_function_body(node):
            self.manual.append((node.lineno, "f: " + consts))
            return
        template = ""
        args: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                template += str(v.value).replace("{", "{{").replace("}", "}}")
                continue
            assert isinstance(v, ast.FormattedValue)
            spec = ""
            if v.format_spec is not None:
                if not all(isinstance(x, ast.Constant) for x in v.format_spec.values):
                    self.manual.append((node.lineno, "f(嵌套格式): " + consts))
                    return
                spec = ":" + "".join(str(x.value) for x in v.format_spec.values)
            conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}.get(v.conversion, "")
            template += "{" + str(len(args)) + conv + spec + "}"
            args.append(ast.get_source_segment(self.src, v.value) or ast.unparse(v.value))
        code = "tr(" + ", ".join([py_literal(template)] + args) + ")"
        self.replacements.append((node, code, template))
        # 不再往里走（里面的表达式如果还有中文字符串，属于少见情况，人工看）


def byte_offset(lines_b: list[bytes], lineno: int, col: int) -> int:
    return sum(len(x) for x in lines_b[:lineno - 1]) + col


def process(path: Path, write: bool) -> tuple[list[str], list[tuple[int, str]]]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    f = Finder(src)
    f.visit(tree)
    keys = [k for _, _, k in f.replacements]
    if write and f.replacements:
        data = src.encode("utf-8")
        lines_b = data.splitlines(keepends=True)
        spans = []
        for node, code, _ in f.replacements:
            a = byte_offset(lines_b, node.lineno, node.col_offset)
            b = byte_offset(lines_b, node.end_lineno, node.end_col_offset)
            spans.append((a, b, code.encode("utf-8")))
        for a, b, code in sorted(spans, reverse=True):
            data = data[:a] + code + data[b:]
        out = data.decode("utf-8")
        if "from app.i18n import tr" not in out:
            m = re.search(r"^from __future__ import annotations\n", out, flags=re.M)
            if m:
                out = out[:m.end()] + "\nfrom app.i18n import tr\n" + out[m.end():]
            else:
                out = "from app.i18n import tr\n" + out
        path.write_text(out, encoding="utf-8", newline="\n")
    return keys, f.manual


def extract_wrapped(path: Path) -> list[str]:
    """从已经包好 tr() 的代码里取出所有键。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        index = {"tr": 0, "tr_in": 1}.get(node.func.id)     # tr_in(语言, 文字)：文字是第二个参数
        if index is None or len(node.args) <= index:
            continue
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            keys.append(arg.value)
    return keys


def extract_module_constants(path: Path) -> list[str]:
    """界面文件里模块级的中文常量（例如模式按钮的名字），使用处会 tr(变量)。"""
    src = path.read_text(encoding="utf-8")
    f = Finder(src)
    f.visit(ast.parse(src))
    return [t for _, t in f.manual if not t.startswith("f")]


def extract_constants(path: Path) -> list[str]:
    """config.py 这类文件：所有含中文的字符串常量（不含文档字符串和注释）都算键，使用处会 tr(变量)。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    f = Finder(src)
    f.visit(tree)
    out = [k for _, _, k in f.replacements] + [t for _, t in f.manual if not t.startswith("f")]
    return out


def main() -> int:
    dry = "--dry" in sys.argv
    extract_only = "--extract" in sys.argv
    all_keys: list[str] = []
    for rel in FILES:
        p = ROOT / rel
        if extract_only:
            all_keys.extend(extract_wrapped(p))
            continue
        keys, manual = process(p, write=not dry)
        all_keys.extend(keys)
        print(f"{rel}: {'将包' if dry else '已包'} {len(keys)} 处" + (f"，需人工 {len(manual)} 处" if manual else ""))
        for ln, text in manual:
            print(f"    人工 L{ln}: {text[:70]!r}")
    if extract_only:
        for rel in EXTRACT_CONSTANTS_FROM:
            all_keys.extend(extract_constants(ROOT / rel))
        for rel in EXTRACT_MODULE_CONSTANTS_FROM:
            all_keys.extend(extract_module_constants(ROOT / rel))
        uniq = list(dict.fromkeys(all_keys))
        out = ROOT / "app" / "locales" / "_keys.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(uniq, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"共 {len(uniq)} 条不重复的界面文字 → {out}")
    else:
        print(f"合计 {len(all_keys)} 处，不重复 {len(set(all_keys))} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
