"""
text_ingest.py - BrandPilot pre-flight engine, Step 1: Ingest & parse (text path).

Job: take whatever text comes in (pasted string, .txt/.md file, raw bytes) and return a
clean, canonical text plus paragraph/sentence segments with exact character offsets.

Key rule: every offset refers to IngestedText.text (the canonical text), so findings
(span_start / span_end) and editor highlights always line up with the same string.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Union

MAX_CHARS = 100_000                      # ~15k words; reject anything bigger
MAX_BYTES = 2_000_000
SUPPORTED_EXT = {".txt", ".md", ".markdown"}

# Zero-width chars removed. ZWNJ (200C) / ZWJ (200D) are KEPT: Devanagari needs them.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u2060\ufeff"), None)
# Control chars except \n and \t
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Content is untrusted DATA. These only flag it for human review; never obeyed.
_INJECTION = [
    re.compile(p, re.I)
    for p in (
        r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules|guidelines)",
        r"disregard .{0,40}(rules|guidelines|instructions)",
        r"(approve|pass) (this|everything|all)\b",
        r"\byou are now\b",
        r"\bsystem prompt\b",
        r"</?\s*(system|assistant|instructions?)\s*>",
    )
]

_PARAGRAPH = re.compile(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*")
# Sentence boundary: . ! ? or Hindi danda followed by whitespace, or any newline.
# "4.5:1" / "7.1:1" do not split because no whitespace follows the dot.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?\u0964])\s+|\n")


@dataclass
class Segment:
    start: int          # offset in IngestedText.text (inclusive)
    end: int            # offset (exclusive)
    text: str


@dataclass
class IngestedText:
    source: str                         # "paste" or file name
    text: str                           # canonical text; ALL offsets refer to this
    sha256: str                         # hash of canonical text (audit / versioning)
    char_count: int
    word_count: int
    paragraphs: list[Segment] = field(default_factory=list)
    sentences: list[Segment] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class IngestError(ValueError):
    """Input cannot be processed (empty, too large, unsupported type)."""


def _decode(raw: bytes, warnings: list[str]) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        warnings.append("Not valid UTF-8; decoded as cp1252 - check special characters.")
        return raw.decode("cp1252", errors="replace")


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)      # stable Hindi/accents
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_ZERO_WIDTH)
    text = _CONTROL.sub("", text)
    text = text.replace("\u00a0", " ")             # non-breaking space -> space
    return text.strip()


def _split_sentences(text: str, p_start: int, p_end: int) -> list[Segment]:
    out: list[Segment] = []
    last = p_start
    para = text[p_start:p_end]
    pieces = []
    for m in _SENT_BOUNDARY.finditer(para):
        pieces.append((last, p_start + m.start()))
        last = p_start + m.end()
    pieces.append((last, p_end))
    for s, e in pieces:
        chunk = text[s:e]
        stripped = chunk.strip()
        if not stripped:
            continue
        s += len(chunk) - len(chunk.lstrip())
        e = s + len(stripped)
        out.append(Segment(s, e, text[s:e]))
    return out


def ingest_text(content: Union[str, bytes], source: str = "paste") -> IngestedText:
    """Main entry point: paste string or raw bytes -> IngestedText."""
    warnings: list[str] = []
    if isinstance(content, bytes):
        if len(content) > MAX_BYTES:
            raise IngestError(f"Input too large ({len(content)} bytes, max {MAX_BYTES}).")
        content = _decode(content, warnings)

    text = _normalise(content)
    if not text:
        raise IngestError("Input is empty.")
    if len(text) > MAX_CHARS:
        raise IngestError(f"Text too long ({len(text)} chars, max {MAX_CHARS}).")

    paragraphs, sentences = [], []
    for m in _PARAGRAPH.finditer(text):
        paragraphs.append(Segment(m.start(), m.end(), m.group()))
        sentences.extend(_split_sentences(text, m.start(), m.end()))

    flags = sorted({m.group(0) for pat in _INJECTION for m in pat.finditer(text)})
    if flags:
        warnings.append("Possible prompt-injection text found; route to human review.")

    return IngestedText(
        source=source,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        char_count=len(text),
        word_count=len(text.split()),
        paragraphs=paragraphs,
        sentences=sentences,
        injection_flags=flags,
        warnings=warnings,
    )


def ingest_file(path: Union[str, Path]) -> IngestedText:
    """Read a .txt / .md file from disk."""
    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_EXT:
        raise IngestError(f"Unsupported file type '{p.suffix}'. Use: {sorted(SUPPORTED_EXT)}")
    if not p.is_file():
        raise IngestError(f"File not found: {p}")
    return ingest_text(p.read_bytes(), source=p.name)


if __name__ == "__main__":
    import json
    import sys

    result = ingest_file(sys.argv[1]) if len(sys.argv) > 1 else ingest_text(sys.stdin.read())
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
