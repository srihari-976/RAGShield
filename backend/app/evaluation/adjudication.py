"""Adjudication: detect rater disagreements (max-min >= 3 or unanimous
conflict), resolve via adjudicator decision, keep the record for calibration."""

import json
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.evaluation import Adjudication, Rating

DISAGREEMENT_THRESHOLD = 3


def flag_disagreements(db: Session) -> list[dict]:
    ratings = db.query(Rating).all()
    by_item: dict[str, list[Rating]] = defaultdict(list)
    for r in ratings:
        by_item[r.item_id].append(r)

    flags = []
    for item_id, rows in by_item.items():
        for dim in ("groundedness", "relevance", "completeness", "citation_quality"):
            scores = [getattr(r, dim) for r in rows if getattr(r, dim) is not None]
            if len(scores) >= 2 and (max(scores) - min(scores)) >= DISAGREEMENT_THRESHOLD:
                flags.append(
                    {
                        "item_id": item_id,
                        "dimension": dim,
                        "scores": {r.rater_id: getattr(r, dim) for r in rows if getattr(r, dim) is not None},
                        "spread": max(scores) - min(scores),
                    }
                )
    return flags


def adjudicate(db: Session, item_id: str, dimension: str, adjudicator_id: str, final_score: int, reason: str | None) -> Adjudication:
    rows = db.query(Rating).filter(Rating.item_id == item_id).all()
    original = {r.rater_id: getattr(r, dimension) for r in rows if getattr(r, dimension) is not None}
    existing = db.query(Adjudication).filter(Adjudication.item_id == item_id, Adjudication.dimension == dimension).first()
    if existing:
        existing.final_score = final_score
        existing.reason = reason
        existing.adjudicator_id = adjudicator_id
        record = existing
    else:
        record = Adjudication(
            item_id=item_id,
            dimension=dimension,
            adjudicator_id=adjudicator_id,
            original_scores=json.dumps(original),
            final_score=final_score,
            reason=reason,
        )
        db.add(record)
    db.commit()
    return record


def rater_agreement(db: Session, dimension: str = "groundedness") -> dict:
    """Krippendorff's alpha over all units with 2+ judgments, by dimension."""
    from app.evaluation.krippendorff import krippendorff_alpha

    ratings = db.query(Rating).all()
    by_item: dict[str, list[int | None]] = defaultdict(list)
    for r in ratings:
        by_item[r.item_id].append(getattr(r, dimension))
    matrix = [vals for vals in by_item.values() if sum(1 for v in vals if v is not None) >= 2]
    alpha = krippendorff_alpha(matrix) if matrix else None
    return {"dimension": dimension, "units": len(matrix), "alpha": alpha}
