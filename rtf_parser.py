"""A small, dependency-free RTF parser aimed at reading documents safely.

It deliberately ignores active/embedded RTF content and extracts the text and
the formatting that matters in a reader.  It is not an RTF editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re


@dataclass(frozen=True)
class TextStyle:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    size: float = 12.0
    font: str | None = None
    foreground: str | None = None
    background: str | None = None
    alignment: str = "left"
    rise: str | None = None


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    style: TextStyle


@dataclass
class Document:
    text: str
    spans: list[Span] = field(default_factory=list)
    title: str | None = None
    author: str | None = None


@dataclass
class _State:
    style: TextStyle = field(default_factory=TextStyle)
    uc: int = 1
    skip: bool = False
    hidden: bool = False
    pending_ignorable: bool = False


_SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "listtable", "listoverridetable",
    "revtbl", "rsidtbl", "generator", "pict", "object", "objdata",
    "nonshppict", "shppict", "datastore", "themedata", "colorschememapping",
    "xmlnstbl", "latentstyles", "mmathpr", "filetbl", "header", "headerl",
    "headerr", "footer", "footerl", "footerr", "annotation", "comment",
    "atnauthor", "atndate", "pn", "pntext", "fldinst", "info",
}

_SPECIAL = {
    "par": "\n", "line": "\n", "tab": "\t", "page": "\n\n",
    "emdash": "—", "endash": "–", "emspace": "\u2003", "enspace": "\u2002",
    "qmspace": "\u2005", "bullet": "•", "lquote": "‘", "rquote": "’",
    "ldblquote": "“", "rdblquote": "”", "zwj": "\u200d", "zwnj": "\u200c",
}


def _group(data: str, marker: str) -> str | None:
    start = data.find("{\\" + marker)
    if start < 0:
        return None
    depth = 0
    escaped = False
    for index in range(start, len(data)):
        char = data[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return data[start:index + 1]
    return None


def _tables(data: str) -> tuple[dict[int, str], list[str | None]]:
    fonts: dict[int, str] = {}
    font_group = _group(data, "fonttbl") or ""
    for item in re.finditer(r"\\f(-?\d+)(?:[^;{}]|\\[{}])*?\s([^;{}\\][^;{}]*);", font_group):
        name = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", item.group(2)).strip()
        if name:
            fonts[int(item.group(1))] = name

    colors: list[str | None] = []
    color_group = _group(data, "colortbl") or ""
    if color_group:
        body = color_group[color_group.find("colortbl") + 8:-1]
        for item in body.split(";")[:-1]:
            red = re.search(r"\\red(\d+)", item)
            green = re.search(r"\\green(\d+)", item)
            blue = re.search(r"\\blue(\d+)", item)
            if red and green and blue:
                colors.append(f"#{int(red.group(1)):02x}{int(green.group(1)):02x}{int(blue.group(1)):02x}")
            else:
                colors.append(None)
    return fonts, colors


def _metadata(data: str, key: str) -> str | None:
    info = _group(data, "info") or ""
    match = re.search(r"{\\" + key + r"\s+([^{}]*)}", info)
    if not match:
        return None
    value = re.sub(r"\\'[0-9a-fA-F]{2}", "", match.group(1))
    value = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", value)
    return value.replace("\\{", "{").replace("\\}", "}").strip() or None


def parse_rtf(raw: bytes | str) -> Document:
    """Parse *raw* RTF into plain text and styled spans.

    Raises ValueError for input that does not look like an RTF document.
    """
    if isinstance(raw, bytes):
        data = raw.decode("latin-1")
    else:
        data = raw
    if not re.match(r"^\s*{\\rtf\d", data):
        raise ValueError("This file is not a valid RTF document.")

    fonts, colors = _tables(data)
    default_font_match = re.search(r"\\deff(-?\d+)", data[:512])
    default_font = fonts.get(int(default_font_match.group(1))) if default_font_match else None
    state = _State(style=TextStyle(font=default_font))
    stack: list[_State] = []
    output: list[str] = []
    runs: list[list[object]] = []
    output_length = 0
    skip_fallback = 0
    pending_high_surrogate: int | None = None
    codepage = "cp1252"
    index = 0

    def append(text: str) -> None:
        nonlocal skip_fallback, output_length, pending_high_surrogate
        if not text or state.skip or state.hidden:
            return
        if skip_fallback:
            if len(text) <= skip_fallback:
                skip_fallback -= len(text)
                return
            text = text[skip_fallback:]
            skip_fallback = 0
        if pending_high_surrogate is not None:
            text = "\ufffd" + text
            pending_high_surrogate = None
        start = output_length
        output.append(text)
        end = start + len(text)
        output_length = end
        if runs and runs[-1][2] == state.style and runs[-1][1] == start:
            runs[-1][1] = end
        else:
            runs.append([start, end, state.style])

    while index < len(data):
        char = data[index]
        if char == "{":
            stack.append(replace(state))
            index += 1
            continue
        if char == "}":
            if stack:
                state = stack.pop()
            index += 1
            continue
        if char in "\r\n":
            # Physical line endings format the RTF source; visible breaks use
            # the \par or \line control words.
            index += 1
            continue
        if char != "\\":
            start = index
            while index < len(data) and data[index] not in "{}\\\r\n":
                index += 1
            append(data[start:index])
            continue

        index += 1
        if index >= len(data):
            break
        symbol = data[index]
        if symbol in "\\{}":
            append(symbol)
            index += 1
            continue
        if symbol == "'" and index + 2 < len(data):
            try:
                byte = bytes([int(data[index + 1:index + 3], 16)])
                append(byte.decode(codepage, errors="replace"))
            except ValueError:
                pass
            index += 3
            continue
        if symbol == "*":
            state.pending_ignorable = True
            index += 1
            continue
        if symbol == "~":
            append("\u00a0")
            index += 1
            continue
        if symbol == "-":
            append("\u00ad")
            index += 1
            continue
        if symbol == "_":
            append("‑")
            index += 1
            continue
        if not symbol.isalpha():
            index += 1
            continue

        start = index
        while index < len(data) and data[index].isalpha():
            index += 1
        word = data[start:index]
        sign = 1
        if index < len(data) and data[index] == "-":
            sign = -1
            index += 1
        number_start = index
        while index < len(data) and data[index].isdigit():
            index += 1
        parameter = sign * int(data[number_start:index]) if index > number_start else None
        if index < len(data) and data[index] == " ":
            index += 1

        if state.pending_ignorable or word in _SKIP_DESTINATIONS:
            state.skip = True
            state.pending_ignorable = False
            continue
        if state.skip:
            continue
        if word in _SPECIAL:
            append(_SPECIAL[word])
        elif word == "u" and parameter is not None:
            value = parameter if parameter >= 0 else parameter + 65536
            if 0xD800 <= value <= 0xDBFF:
                if pending_high_surrogate is not None:
                    pending_high_surrogate = None
                    append("\ufffd")
                pending_high_surrogate = value
            elif 0xDC00 <= value <= 0xDFFF and pending_high_surrogate is not None:
                scalar = 0x10000 + ((pending_high_surrogate - 0xD800) << 10) + (value - 0xDC00)
                pending_high_surrogate = None
                append(chr(scalar))
            else:
                append(chr(value))
            skip_fallback = state.uc
        elif word == "uc" and parameter is not None:
            state.uc = max(0, parameter)
        elif word == "ansicpg" and parameter is not None:
            candidate = f"cp{parameter}"
            try:
                "".encode(candidate)
                codepage = candidate
            except LookupError:
                codepage = "cp1252"
        elif word == "b":
            state.style = replace(state.style, bold=parameter != 0)
        elif word == "i":
            state.style = replace(state.style, italic=parameter != 0)
        elif word in {"ul", "uld", "uldb", "ulw"}:
            state.style = replace(state.style, underline=parameter != 0)
        elif word == "ulnone":
            state.style = replace(state.style, underline=False)
        elif word == "strike":
            state.style = replace(state.style, strike=parameter != 0)
        elif word == "fs" and parameter is not None:
            state.style = replace(state.style, size=max(5.0, min(96.0, parameter / 2)))
        elif word == "f" and parameter is not None:
            state.style = replace(state.style, font=fonts.get(parameter, state.style.font))
        elif word == "cf" and parameter is not None:
            color = colors[parameter] if 0 <= parameter < len(colors) else None
            state.style = replace(state.style, foreground=color)
        elif word in {"highlight", "cb"} and parameter is not None:
            color = colors[parameter] if 0 <= parameter < len(colors) else None
            state.style = replace(state.style, background=color)
        elif word in {"qc", "qr", "qj", "ql"}:
            alignment = {"qc": "center", "qr": "right", "qj": "fill", "ql": "left"}[word]
            state.style = replace(state.style, alignment=alignment)
        elif word == "super":
            state.style = replace(state.style, rise="super")
        elif word == "sub":
            state.style = replace(state.style, rise="sub")
        elif word == "nosupersub":
            state.style = replace(state.style, rise=None)
        elif word == "plain":
            state.style = TextStyle(font=default_font, alignment=state.style.alignment)
        elif word == "pard":
            state.style = replace(state.style, alignment="left")
        elif word == "v":
            state.hidden = parameter != 0
        elif word == "bin" and parameter:
            index = min(len(data), index + max(0, parameter))

    if pending_high_surrogate is not None:
        pending_high_surrogate = None
        append("\ufffd")
    text = "".join(output)
    spans = [Span(int(start), int(end), style) for start, end, style in runs if start != end]
    return Document(
        text=text,
        spans=spans,
        title=_metadata(data, "title"),
        author=_metadata(data, "author"),
    )
