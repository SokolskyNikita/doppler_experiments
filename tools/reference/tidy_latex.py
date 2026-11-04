"""Tidy Mistral's spaced-out LaTeX (`\\mathbf { x } ^ { T }`) without changing the math.

Only whitespace that TeX ignores in math mode is removed or added. Every rewritten
formula is re-tokenized and must match the original token stream exactly, or it is
left untouched. Text inside \\text{...}-style groups (where spaces matter) is kept
verbatim.

usage: tidy_latex.py FILE.md [...]   (rewrites in place, prints a summary)
"""
import re
import sys

TEXT_CMDS = {"text", "textrm", "textit", "textbf", "mbox", "hbox", "textnormal"}
SPACED_BINOPS = {"=", "<", ">"}
SPACED_CMDS = {"leq", "geq", "le", "ge", "approx", "sim", "neq", "ne", "equiv",
               "rightarrow", "to", "Rightarrow", "leftarrow", "propto", "simeq"}
SPACED_STYLE = re.compile(r"\{ \S+ \}|\S _ \{|\^ \{ ")


def tokenize(s):
    """Return TeX tokens. Whitespace is a token ' ' only inside text groups."""
    toks, i, n = [], 0, len(s)
    text_depth = []  # brace depth stack for open text groups
    depth = 0
    pending_text = False
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\[A-Za-z]+", s[i:])
            if m:
                tok = m.group(0)
                i += len(tok)
                toks.append(tok)
                if tok[1:] in TEXT_CMDS:
                    pending_text = True
                if not text_depth:
                    while i < n and s[i].isspace():
                        i += 1
                continue
            toks.append(s[i:i + 2])  # control symbol, incl. "\ " and "\\"
            i += 2
            continue
        if c.isspace():
            j = i
            while j < n and s[j].isspace():
                j += 1
            if text_depth:
                toks.append(" ")
            i = j
            continue
        if c == "{":
            depth += 1
            if pending_text:
                text_depth.append(depth)
                pending_text = False
        elif c == "}":
            if text_depth and text_depth[-1] == depth:
                text_depth.pop()
            depth -= 1
        toks.append(c)
        i += 1
    return toks


def render(toks):
    out = []
    prev = ""
    in_text = 0
    depth = 0
    text_stack = []
    pending_text = False
    for t in toks:
        if t == " ":
            out.append(" ")
            prev = t
            continue
        if t == "{":
            depth += 1
            if pending_text:
                text_stack.append(depth)
                pending_text = False
        elif t == "}":
            if text_stack and text_stack[-1] == depth:
                text_stack.pop()
            depth -= 1
        if t.startswith("\\") and t[1:] in TEXT_CMDS:
            pending_text = True
        spaced = (t in SPACED_BINOPS or (t.startswith("\\") and t[1:] in SPACED_CMDS)
                  or t in ("&", "\\\\"))
        if not text_stack:
            if spaced and out and out[-1] != " ":
                out.append(" ")
            elif re.fullmatch(r"\\[A-Za-z]+", prev) and re.match(r"[A-Za-z]", t):
                out.append(" ")  # keep a control word separated from a letter
        out.append(t)
        if not text_stack and spaced:
            out.append(" ")
        prev = t
    s = "".join(out)
    return re.sub(r" {2,}", " ", s).strip()


def looks_like_prose(body):
    """True if the span has ordinary words in it: a mis-paired '$', not a formula."""
    s = re.sub(r"\\(?:text\w*|mathrm|operatorname\*?|mbox)\s*\{[^{}]*\}", "", body)
    s = re.sub(r"\\begin\s*\{[^}]*\}|\\end\s*\{[^}]*\}|\\[A-Za-z]+", "", s)
    return re.search(r"[A-Za-z]{3,}[\s,.;:]+[A-Za-z]{3,}", s) is not None


def tidy_math(body):
    if not SPACED_STYLE.search(body) or looks_like_prose(body):
        return body, False
    new = render(tokenize(body))
    if tokenize(new) != tokenize(body):
        return body, False
    return new, new != body


# Mistral writes math as $$…$$ / $…$ in some files and \[…\] / \(…\) in others.
# Display math may span lines. Inline math must sit on one line; inline $…$ must
# also start and end on a non-space character and not touch another '$' (so
# "$17.00" prices don't pair up). Alternatives are tried in order at each position,
# so a display block is always consumed before an inline match can start inside it.
MATH = re.compile(
    r"(\$\$)(.+?)(\$\$)"
    r"|(\\\[)(.+?)(\\\])"
    r"|(\\\()([^\n]+?)(\\\))"
    r"|(?<![\\$])(\$)(?![\s$])([^$\n]+?)(?<![\s\\])(\$)(?!\$)",
    re.S,
)


def spans(src):
    """Split text into ('txt', s) and ('math', open, body, close) pieces."""
    out, pos = [], 0
    for m in MATH.finditer(src):
        g = [x for x in m.groups() if x is not None]
        out.append(("txt", src[pos:m.start()]))
        out.append(("math", g[0], g[1], g[2]))
        pos = m.end()
    out.append(("txt", src[pos:]))
    return out


def tidy_file(path):
    src = open(path, encoding="utf-8").read()
    changed = 0
    pieces = []
    for piece in spans(src):
        if piece[0] == "txt":
            pieces.append(piece[1])
            continue
        _, open_, body, close = piece
        new, did = tidy_math(body)
        changed += did
        pieces.append(open_ + new + close)
    out = "".join(pieces)
    # Only whitespace inside formulas may change.
    assert re.sub(r"\s", "", out) == re.sub(r"\s", "", src), path
    open(path, "w", encoding="utf-8").write(out)
    return changed, len(src), len(out)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        n, a, b = tidy_file(p)
        print(f"{p}: {n} formulas tidied, {a} -> {b} chars")
