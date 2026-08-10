"""ABAC policy engine.

Policies are stored as JSON rules evaluated against subject/resource attribute
dicts. Small, safe DSL (no eval): supports eq/neq/in/contains/gt/lt and
and/any/not combinators.

Example rule for "doctor can read assigned patients' records":
{
  "any": [
    {"eq": ["subject.id", "resource.owner_id"]},
    {"all": [
      {"eq": ["subject.role", "doctor"]},
      {"contains": ["resource.patient_id", "subject.assigned_patients"]}
    ]}
  ]
}
"""

import json
import operator
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import ResourcePolicy

_MISSING = object()


def _lookup(attrs: dict[str, Any], path: str) -> Any:
    cur: Any = attrs
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part, _MISSING)
        else:
            return _MISSING
    return cur


def _truthy(v: Any) -> bool:
    if v is _MISSING or v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip() != ""
    return len(v) > 0


def _resolve(attrs: dict[str, Any], arg: Any) -> Any:
    """Resolve a rule argument as an attribute path, falling back to the raw
    literal value when the path does not exist (or the arg is not a string)."""
    if isinstance(arg, str):
        v = _lookup(attrs, arg)
        return arg if v is _MISSING else v
    return arg


def evaluate_rule(rule: dict, ctx: dict[str, Any]) -> bool:
    for op, args in rule.items():
        if op == "eq":
            return _resolve(ctx, args[0]) == _resolve(ctx, args[1])
        if op == "neq":
            return _resolve(ctx, args[0]) != _resolve(ctx, args[1])
        if op == "in":
            return _resolve(ctx, args[0]) in _resolve(ctx, args[1])
        if op == "contains":
            return _resolve(ctx, args[1]) in _resolve(ctx, args[0])
        if op == "gt":
            return _resolve(ctx, args[0]) > _resolve(ctx, args[1])
        if op == "lt":
            return _resolve(ctx, args[0]) < _resolve(ctx, args[1])
        if op in ("all", "and"):
            return all(evaluate_rule(a, ctx) for a in args)
        if op in ("any", "or"):
            return any(evaluate_rule(a, ctx) for a in args)
        if op == "not":
            return not evaluate_rule(args, ctx)
        if op == "bool":
            return _truthy(_resolve(ctx, args))
        # Shorthand: {"subject.role": "student"}  ->  equality check
        return _resolve(ctx, op) == _resolve(ctx, args)
    return False


def evaluate_policy(policy: ResourcePolicy, subject_attrs: dict, resource_attrs: dict) -> bool:
    try:
        rule = json.loads(policy.rule)
    except json.JSONDecodeError:
        return False
    ctx = {"subject": subject_attrs, "resource": resource_attrs, "environment": {}}
    return evaluate_rule(rule, ctx)


def evaluate_policies(db: Session, tenant_id: str, action: str, subject_attrs: dict, resource_attrs: dict) -> bool:
    """First matching active policy decides (priority order)."""
    policies = (
        db.query(ResourcePolicy)
        .filter(ResourcePolicy.tenant_id == tenant_id, ResourcePolicy.is_active.is_(True))
        .order_by(ResourcePolicy.priority.asc())
        .all()
    )
    for p in policies:
        if p.action != action:
            continue
        if evaluate_policy(p, subject_attrs, resource_attrs):
            return p.effect == "allow"
    return False  # no policy matched -> deny
