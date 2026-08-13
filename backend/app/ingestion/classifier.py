"""AI document access classifier.

Reads the extracted text of a document and decides:
  - sensitivity classification (public / internal / confidential / restricted)
  - which system roles may read it

The LLM proposes; the deterministic authorization engine enforces. Classification
never blocks ingestion — on any failure we fall back to a keyword heuristic, and on
uncertainty we default to `restricted` + `needs_review` (safety-first).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import get_settings

settings = get_settings()

CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")

CLASSIFIER_PROMPT = """You are a document-access classifier for an organization's RAG platform.
Inspect the document and answer with ONLY valid JSON, no prose:

{"classification": "public"|"restricted", "roles": [], "subject": null,
 "confidence": 0.0, "justification": "short reason"}

Rules:
- "public": ONLY organizational/public material anyone may read — policies,
  about-us / company or school overview pages, brochures, syllabi, public notices, press releases.
- Everything else is "restricted": personal data of a named person (salary, address,
  performance review, personal files), exam answer keys, credentials/secrets, grades,
  financials, and all internal company/school/organization documents.
- "subject": if the document concerns ONE specific person, put that person's name
  (e.g. "Srihari"); otherwise null.
- "roles": always [] — the admin decides who is granted access after review.
- "confidence": 0.0 to 1.0. If you are not confident, use "restricted" and confidence < 0.5.

Document text:
"""

# --- heuristic fallback rules: (pattern, classification, roles, confidence) ----
_HEURISTIC_RULES: list[tuple[re.Pattern[str], str, list[str], float]] = [
    (
        re.compile(r"exam\s*(a\s*n\s*s\s*w\s*e\s*r\s*)?(key|sheet)|answer\s*key|question\s*paper|marking\s*scheme", re.I),
        "restricted", [], 0.95,
    ),
    (
        re.compile(r"salary|payroll|compensation|wage|payslip|personal\s+data|address|performance\s*review|appraisal", re.I),
        "restricted", [], 0.9,
    ),
    (
        re.compile(r"secret|credential|password|api\s*key|access\s*token|passphrase", re.I),
        "restricted", [], 0.9,
    ),
    (
        re.compile(r"ssn|social\s*security|aadhaar|pan\s*card|bank\s*account|account\s*number", re.I),
        "restricted", [], 0.9,
    ),
    (
        re.compile(r"financial|finance|budget|ledger|balance\s*sheet|revenue|profit|income|expense|cash\s*reserve|funding\s*plan", re.I),
        "restricted", [], 0.85,
    ),
    (
        re.compile(r"gradebook|sheet:\s*grades|student\s*grades|final\s*grades|marks?\s*rubric|class\s*roster", re.I),
        "restricted", [], 0.85,
    ),
    (
        re.compile(r"confidential|do\s*not\s*distribute|internal\s*use\s*only", re.I),
        "restricted", [], 0.8,
    ),
    (
        re.compile(r"policy|policies|about\s*us|company\s*overview|brochure|flyer|newsletter|public\s*notice|press\s*release|syllabus|mission|vision", re.I),
        "public", [], 0.8,
    ),
]

_ROLE_ALIASES = {
    "instructor": "lecturer",
    "teach": "lecturer",
    "faculty": "lecturer",
    "professor": "lecturer",
    "teacher": "lecturer",
    "hr": "manager",
    "manager": "manager",
    "staff": "employee",
    "engineer": "employee",
    "employee": "employee",
    "student": "student",
    "students": "student",
    "admin": "admin",
    "administrator": "admin",
    "owner": "owner",
}

VALID_ROLES = set(_ROLE_ALIASES.values())


@dataclass
class ClassificationResult:
    classification: str = "restricted"
    roles: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "default"  # file | llm | heuristic | default
    justification: str = ""
    forced_review: bool = False
    subject: str | None = None  # person the document is about (if any)

    @property
    def needs_review(self) -> bool:
        if self.forced_review:
            return True
        if self.source == "default":
            return True
        return self.confidence < settings.auto_classify_confidence


def _clean_roles(roles: list[str] | None) -> list[str]:
    out: list[str] = []
    for r in roles or []:
        if not isinstance(r, str) or not r.strip():
            continue
        alias = _ROLE_ALIASES.get(r.strip().lower(), r.strip().lower())
        if alias in VALID_ROLES and alias not in out:
            out.append(alias)
    return out


def _matching_texts(text: str) -> dict[str, str]:
    """Original + OCR-tolerant compact copies used for pattern matching.

    OCR of scanned pages often inserts stray spaces inside words
    ("a nswer key", "S ca n ned"). Matching against a compacted copy
    (whitespace removed) makes the patterns resilient to that noise."""
    compact = re.sub(r"\s+", "", text)
    return {"text": text, "compact": compact}


def classify_heuristic(text: str, filename: str = "") -> ClassificationResult:
    """Deterministic keyword/pattern classification used for sensitive-signal
    detection and as the LLM fallback."""
    if len(text) > 12000:
        text = text[:12000]
    sources = _matching_texts(text)
    best: tuple[float, str, list[str], float] | None = None
    for pattern, classification, roles, confidence in _HEURISTIC_RULES:
        for variant in (sources["text"], sources["compact"]):
            if pattern.search(variant):
                score = confidence + (0.1 if pattern.search(filename) else 0.0)
                if best is None or score > best[0]:
                    best = (score, classification, roles, confidence)
                break
    if best is None:
        # default posture: no public or personal signal -> restricted + review,
        # so nothing is exposed until an admin grants access
        return ClassificationResult(
            classification="restricted", roles=[], confidence=0.4, source="heuristic",
            justification="no public or personal signal — restricted by default",
        )
    _, classification, roles, confidence = best
    return ClassificationResult(
        classification=classification,
        roles=_clean_roles(roles),
        confidence=confidence,
        source="heuristic",
        justification=f"matched pattern: {classification}",
    )


def classify_llm(text: str, filename: str = "") -> ClassificationResult:
    """Ask the configured chat model for a structured classification."""
    model = settings.classifier_model or settings.chat_model
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": f"Filename: {filename}\n\n{text[:12000]}"},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 400},
    }
    with httpx.Client(
        base_url=settings.ollama_base_url, timeout=settings.auto_classify_timeout
    ) as client:
        resp = client.post("/api/chat", json=payload)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
    return _parse_llm_json(content)


def _parse_llm_json(content: str) -> ClassificationResult:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            raise ValueError("no JSON in classifier output")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid classifier JSON: {e}") from e

    classification = str(data.get("classification", "restricted")).strip().lower()
    if classification not in CLASSIFICATIONS:
        classification = "restricted"
    roles = _clean_roles(data.get("roles"))
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    justification = str(data.get("justification", ""))[:300]
    subject = data.get("subject") or None
    subject = str(subject).strip()[:80] if subject else None
    return ClassificationResult(
        classification=classification,
        roles=roles,
        confidence=confidence,
        source="llm",
        justification=justification,
        subject=subject,
    )


def _classify_by_filename(filename: str) -> ClassificationResult | None:
    """Deterministic, authoritative classification from the file name.

    The file name is a deliberate label (e.g. the admin names a file
    `srihari_salary.pdf`), so a match here overrides the LLM — this prevents
    over-exposure when OCR text is garbled or the model misses a signal.
    Personal documents carry the person's name as the `subject`, which is later
    resolved to a specific user when ACLs are provisioned."""
    fn = (Path(filename).name or filename).lower()
    rules: list[tuple[str, str, bool]] = [
        # personal documents -> restricted, subject = the person
        (r"salary|payroll|compensation|appraisal|performance[\s_\-]*review|address|personal|transcript|report[\s_\-]*card|admit[\s_\-]*card", "restricted", True),
        # credentials / secrets
        (r"secret|credential|password|token|api[\s_\-]*key|passphrase", "restricted", False),
        # exams / answer keys
        (r"exam|answer[\s_\-]*key|question[\s_\-]*paper|marking[\s_\-]*scheme|solution[\s_\-]*key", "restricted", False),
        # grades / gradebooks
        (r"gradebook|grades|marks|class[\s_\-]*roster", "restricted", False),
        # personally-identifiable filings
        (r"ssn|aadhaar|pan[\s_\-]*card|bank[\s_\-]*statement", "restricted", False),
        # financial records
        (r"financial|finance|budget|ledger|balance[\s_\-]*sheet|revenue|profit|income|expense", "restricted", False),
        # organizational / public material
        (r"policy|policies|about[\s_\-]*us|company[\s_\-]*overview|brochure|flyer|press[\s_\-]*release|newsletter|public[\s_\-]*notice|syllabus|mission|vision", "public", False),
    ]
    for pattern, classification, personal in rules:
        if re.search(pattern, fn):
            return ClassificationResult(
                classification=classification,
                roles=[],
                confidence=0.99,
                source="filename",
                justification=f"filename signal: {pattern}",
                subject=_extract_subject(filename) if personal else None,
            )
    return None


_PERSONAL_NOISE = re.compile(
    r"salary|payroll|compensation|appraisal|performance|review|transcript|report|admit|card|address|personal|statement|final|202[0-9]|\.", re.I
)


def _extract_subject(filename: str) -> str | None:
    """Best-effort person-name extraction for personal files, e.g.
    `srihari_performance_review.pdf` -> "srihari"."""
    stem = Path(filename).stem
    cleaned = _PERSONAL_NOISE.sub(" ", stem)
    cleaned = re.sub(r"[^A-Za-z]+", " ", cleaned).strip()
    parts = [p for p in cleaned.split() if len(p) >= 2 and not p.isdigit()]
    subject = " ".join(parts).strip().lower()
    return subject or None


def _auto_label(label: str) -> str:
    """Auto-classification only ever yields `public` or `restricted` — every
    non-public document defaults to restricted and awaits human review."""
    return label if label == "public" else "restricted"


def classify_document(text: str, filename: str = "") -> ClassificationResult:
    """Best-effort classification: filename signals first (authoritative), then
    keyword heuristics, with the LLM as a tie-breaker. A document may only be
    `public` when an explicit public signal (filename or keyword) exists —
    otherwise it defaults to `restricted` and awaits human review."""
    if not settings.auto_classify_enabled:
        return ClassificationResult(
            classification="restricted", roles=[], confidence=0.0, source="default",
            justification="auto-classification disabled",
        )
    by_filename = _classify_by_filename(filename)
    if by_filename is not None:
        return by_filename

    heuristic = classify_heuristic(text, filename)

    # Clear public signal present -> public, unless a confident LLM upgrades to
    # restricted (safe direction), which we honour.
    if heuristic.classification == "public":
        try:
            llm_result = classify_llm(text, filename)
            llm_result.classification = _auto_label(llm_result.classification)
            if llm_result.classification == "restricted" and llm_result.confidence >= heuristic.confidence:
                return llm_result
        except Exception:
            pass
        return heuristic

    # Restricted path (keyword hit or no signal). A strong keyword match vetoes
    # a model that flippantly calls sensitive content "public".
    if heuristic.confidence >= settings.auto_classify_confidence:
        try:
            llm_result = classify_llm(text, filename)
        except Exception:
            llm_result = None
        if llm_result is None:
            return heuristic
        llm_result.classification = _auto_label(llm_result.classification)
        if llm_result.classification != "restricted" or llm_result.confidence < heuristic.confidence:
            heuristic.forced_review = True  # flagged so an admin double-checks
            return heuristic
        return llm_result if llm_result.confidence >= heuristic.confidence else heuristic

    # No keyword signal: default restricted. The LLM may keep it restricted (and
    # raise confidence), but may NOT demote it to public without a public signal.
    try:
        llm_result = classify_llm(text, filename)
        llm_result.classification = _auto_label(llm_result.classification)
        if llm_result.classification == "restricted":
            return llm_result if llm_result.confidence >= heuristic.confidence else heuristic
        heuristic.forced_review = True
        return heuristic
    except Exception:
        # heuristic fallback — never block ingestion
        return heuristic