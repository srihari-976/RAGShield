"""Unit tests for the AI document access classifier."""

from app.ingestion.classifier import (
    _classify_by_filename,
    _clean_roles,
    _parse_llm_json,
    ClassificationResult,
    classify_heuristic,
)


def test_filename_exam_key_restricted():
    res = _classify_by_filename("Exam_Answer_Key_v2.pdf")
    assert res is not None
    assert res.classification == "restricted"
    assert res.roles == []
    assert res.subject is None
    assert res.source == "filename"


def test_filename_gradebook_restricted():
    res = _classify_by_filename("ENGR220-Gradebook-2026.xlsx")
    assert res is not None
    assert res.classification == "restricted"
    assert res.roles == []
    assert res.subject is None


def test_filename_salary_restricted_with_subject():
    res = _classify_by_filename("ramesh_salary.pdf")
    assert res.classification == "restricted"
    assert res.subject == "ramesh"
    assert res.roles == []


def test_filename_personal_review_extracts_subject():
    res = _classify_by_filename("Srihari Performance Review.pdf")
    assert res.classification == "restricted"
    assert res.subject == "srihari"


def test_filename_secret_restricted():
    res = _classify_by_filename("company-secret.txt")
    assert res.classification == "restricted"
    assert res.subject is None


def test_filename_policy_public():
    res = _classify_by_filename("company_policies.pdf")
    assert res is not None
    assert res.classification == "public"


def test_filename_about_public():
    res = _classify_by_filename("AboutUs-2026.pdf")
    assert res.classification == "public"


def test_filename_no_match_returns_none():
    assert _classify_by_filename("meeting_minutes.txt") is None
    assert _classify_by_filename("") is None


def test_heuristic_handles_ocr_spaced_text():
    res = classify_heuristic("Sca n ned docume nt exam a nswer key 1. a 2. c")
    assert res.classification == "restricted"
    assert res.roles == []


def test_heuristic_detects_gradebook_sheet():
    res = classify_heuristic("--- Sheet: Grades ---\nName\tScore\tPass?\nAlice\t85\tYes")
    assert res.classification == "restricted"
    assert res.roles == []


def test_heuristic_gradebook_scores():
    res = classify_heuristic("Student Grades:\nAlice 85\nBob 62\nCarol 91")
    assert res.classification == "restricted"


def test_heuristic_detects_exam_key_as_restricted():
    res = classify_heuristic("CS220 Final\nEXAM ANSWER KEY\n1. a 2. b 3. c")
    assert res.classification == "restricted"
    assert res.roles == []
    assert res.source == "heuristic"
    assert res.confidence >= 0.9


def test_heuristic_detects_salary_as_restricted():
    res = classify_heuristic("Confidential salary record: Alice Smith earns 85000.")
    assert res.classification == "restricted"


def test_heuristic_detects_secret_credential():
    res = classify_heuristic("master api key = sk-123 and password hunter2")
    assert res.classification == "restricted"


def test_heuristic_gradebook_is_restricted():
    res = classify_heuristic("Gradebook for ENGR-220.\nStudent One 95\nStudent Two 87")
    assert res.classification == "restricted"


def test_heuristic_policy_is_public():
    res = classify_heuristic("Company leave policy: 24 days annual leave for employees.")
    assert res.classification == "public"
    assert res.source == "heuristic"


def test_heuristic_public_signal():
    res = classify_heuristic("Open house brochure and public notice for new semester.")
    assert res.classification == "public"


def test_heuristic_default_when_no_signals_is_restricted():
    res = classify_heuristic("The quick brown fox jumps over the lazy dog.")
    assert res.classification == "restricted"
    assert res.roles == []
    assert res.needs_review is True


def test_clean_roles_dedupes_and_maps_aliases():
    assert _clean_roles(["Lecturer", "instructor", "student", "student"]) == ["lecturer", "student"]
    assert _clean_roles([None, "unknown_role", "professor"]) == ["lecturer"]


def test_parse_llm_json():
    res = _parse_llm_json('{"classification": "confidential", "roles": ["lecturer"], "confidence": 0.8, "justification": "rubric"}')
    assert res.source == "llm"
    assert res.classification == "confidential"
    assert res.roles == ["lecturer"]
    assert res.confidence == 0.8
    assert res.needs_review is False


def test_parse_llm_json_subject():
    res = _parse_llm_json('{"classification": "restricted", "roles": [], "subject": "Srihari", "confidence": 0.9}')
    assert res.classification == "restricted"
    assert res.subject == "Srihari"


def test_parse_llm_json_low_confidence_flagged():
    res = _parse_llm_json('{"classification": "restricted", "roles": [], "confidence": 0.2}')
    assert res.needs_review is True


def test_parse_llm_json_bad_classification_falls_back():
    res = _parse_llm_json('{"classification": "topsecret", "roles": [], "confidence": 0.9}')
    assert res.classification == "restricted"


def test_heuristic_financial_overview_is_restricted():
    res = classify_heuristic("SRN Co — Company Financial Overview. Annual Revenue: 12.8 crore.")
    assert res.classification == "restricted"


def test_heuristic_confidential_mark_is_restricted():
    res = classify_heuristic("Document Classification: CONFIDENTIAL / OWNER & AUTHORIZED FINANCE")
    assert res.classification == "restricted"


def test_filename_financials_restricted():
    res = _classify_by_filename("company_financials.pdf")
    assert res is not None
    assert res.classification == "restricted"
    assert res.subject is None


def test_classify_document_financials_stays_restricted(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("public", 0.9))
    res = classifier.classify_document("Company Financial Overview. Confidential. Revenue 12.8 crore.")
    assert res.classification == "restricted"


def test_parse_llm_json_handles_prose_wrapped_json():
    res = _parse_llm_json('Sure! Here it is:\n{"classification": "internal", "roles": [], "confidence": 0.7}')
    assert res.classification == "internal"


def _llm_result(classification, confidence):
    return ClassificationResult(classification=classification, roles=[], confidence=confidence, source="llm")


def test_classify_document_no_signal_llm_public_stays_restricted(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("public", 0.9))
    res = classifier.classify_document("just some routine internal notes about the office layout")
    assert res.classification == "restricted"
    assert res.needs_review is True


def test_classify_document_no_signal_llm_restricted(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("restricted", 0.9))
    res = classifier.classify_document("just some routine internal notes about the office layout")
    assert res.classification == "restricted"
    assert res.confidence == 0.9


def test_classify_document_exam_key_llm_public_vetoed(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("public", 0.95))
    res = classifier.classify_document("EXAM ANSWER KEY 1. a 2. b")
    assert res.classification == "restricted"
    assert res.forced_review is True


def test_classify_document_policy_public_llm_restricted_upgrade_honored(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("restricted", 0.9))
    res = classifier.classify_document("Company leave policy for all employees.")
    assert res.classification == "restricted"


def test_classify_document_policy_public_llm_weak_stays_public(monkeypatch):
    from app.ingestion import classifier
    monkeypatch.setattr(classifier, "classify_llm", lambda text, filename: _llm_result("restricted", 0.6))
    res = classifier.classify_document("Company leave policy for all employees.")
    assert res.classification == "public"


def test_classify_document_policy_public_llm_fails_falls_back(monkeypatch):
    from app.ingestion import classifier

    def boom(text, filename):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(classifier, "classify_llm", boom)
    res = classifier.classify_document("Company leave policy for all employees.")
    assert res.classification == "public"
    assert res.source == "heuristic"