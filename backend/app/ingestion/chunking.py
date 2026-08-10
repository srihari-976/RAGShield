"""Structure-aware chunking with token-size awareness.

Default: 600 tokens / 80 overlap. document_type can select a strategy:
section (split on headings), clause (split on clauses/articles), record
(logical record lines), whole (single chunk).
"""

import re
from dataclasses import dataclass

from app.core.config import get_settings

settings = get_settings()

TOKENS_PER_CHAR = 0.25  # approx for English text

CHUNK_STRATEGIES = {
    "policy": "section",
    "research_paper": "section",
    "salary": "record",
    "contract": "clause",
    "medical_record": "section",
    "social_post": "whole",
}


@dataclass
class Chunk:
    text: str
    index: int
    metadata: dict


_HEADING_RE = re.compile(r"^#{1,6}\s+.*$|^\d+\.\d*\s+[A-Z].*$|^(SECTION|ARTICLE|CLAUSE|PART|APPENDIX)\b.*$", re.IGNORECASE)
_CLAUSE_RE = re.compile(r"^(\d+\.|\([a-z]\)|[IVXLCDM]+\.)\s*\S", re.IGNORECASE)
_RECORD_RE = re.compile(r"^[A-Z0-9][A-Z0-9 _\-]{2,40}[:|]\s*\S")


def _approx_tokens(text: str) -> int:
    return max(1, int(len(text) * TOKENS_PER_CHAR))


def chunk_text(text: str, document_type: str = "general", chunk_size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    size = chunk_size or settings.chunk_size
    ov = overlap if overlap is not None else settings.chunk_overlap
    strategy = CHUNK_STRATEGIES.get(document_type, "section" if document_type in ("policy", "research_paper") else "sized")
    sections = _split_strategy(text, strategy)
    chunks: list[Chunk] = []
    idx = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if _approx_tokens(section) <= size:
            chunks.append(Chunk(text=section, index=idx, metadata={"strategy": strategy}))
            idx += 1
            continue
        for piece in _size_chunks(section, size, ov):
            chunks.append(Chunk(text=piece, index=idx, metadata={"strategy": strategy}))
            idx += 1
    return chunks


def _split_strategy(text: str, strategy: str) -> list[str]:
    if strategy == "whole":
        return [text]
    if strategy == "section":
        return _split_by_heading(text)
    if strategy == "clause":
        return _split_by_clause(text)
    if strategy == "record":
        return _split_by_record(text)
    return [text]


def _split_by_heading(text: str) -> list[str]:
    lines = text.splitlines()
    sections: list[str] = []
    current: list[str] = []
    for line in lines:
        if _HEADING_RE.match(line.strip()):
            if current:
                sections.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections or [text]


def _split_by_clause(text: str) -> list[str]:
    lines = text.splitlines()
    clauses: list[str] = []
    current: list[str] = []
    for line in lines:
        if _CLAUSE_RE.match(line.strip()):
            if current:
                clauses.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        clauses.append("\n".join(current))
    return clauses or [text]


def _split_by_record(text: str) -> list[str]:
    lines = text.splitlines()
    records: list[str] = []
    current: list[str] = []
    for line in lines:
        if _RECORD_RE.match(line.strip()):
            if current:
                records.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        records.append("\n".join(current))
    return records or [text]


def _size_chunks(text: str, size: int, overlap: int) -> list[str]:
    tokens = text.split()
    if not tokens:
        return []
    step = max(1, size - overlap)
    pieces = []
    i = 0
    while i < len(tokens):
        pieces.append(" ".join(tokens[i : i + size]))
        if i + size >= len(tokens):
            break
        i += step
    return pieces
