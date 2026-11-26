"""Helper for the TypeScript port: print a Python module with every string literal and f-string turned
into a TypeScript template literal, so long HTML and Telugu text is copied exactly. The Python code
around the strings still has to be rewritten by hand.

    python ts/scripts/py_strings_to_ts.py gulf_saathi/site.py > /tmp/site_draft.ts
"""
import ast
import sys


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


class Converter:
    def __init__(self, src: str):
        self.src = src
        self.lines = src.splitlines(keepends=True)
        self.starts = [0]
        for ln in self.lines:
            self.starts.append(self.starts[-1] + len(ln))

    def off(self, lineno, col):
        # ast columns are UTF-8 byte offsets
        line = self.lines[lineno - 1]
        return self.starts[lineno - 1] + len(line.encode()[:col].decode())

    def span(self, n):
        return self.off(n.lineno, n.col_offset), self.off(n.end_lineno, n.end_col_offset)

    def lit(self, n) -> str:
        if isinstance(n, ast.Constant):
            return "`" + esc(n.value) + "`"
        out = []
        for part in n.values:
            if isinstance(part, ast.Constant):
                out.append(esc(part.value))
            else:
                expr = self.expr(part.value)
                if part.conversion != -1 or part.format_spec is not None:
                    expr = f"/*FMT {ast.unparse(part)}*/ {expr}"
                out.append("${" + expr + "}")
        return "`" + "".join(out) + "`"

    def strings_in(self, node):
        found = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.JoinedStr) or (isinstance(child, ast.Constant) and isinstance(child.value, str)):
                found.append(child)
            else:
                found.extend(self.strings_in(child))
        return found

    def expr(self, node) -> str:
        a, b = self.span(node)
        text = self.src[a:b]
        if isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            return self.lit(node)
        for s in sorted(self.strings_in(node), key=lambda s: self.span(s)[0], reverse=True):
            sa, sb = self.span(s)
            text = text[:sa - a] + self.lit(s) + text[sb - a:]
        return text

    def module(self) -> str:
        tree = ast.parse(self.src)
        text = self.src
        for s in sorted(self.strings_in(tree), key=lambda s: self.span(s)[0], reverse=True):
            sa, sb = self.span(s)
            text = text[:sa] + self.lit(s) + text[sb:]
        return text


if __name__ == "__main__":
    sys.stdout.write(Converter(open(sys.argv[1], encoding="utf-8").read()).module())
