from dataclasses import dataclass, field

PERMISSIONS = {
    "document.read": "Read documents and query the knowledge base",
    "document.upload": "Upload new documents",
    "document.delete": "Delete documents",
    "document.manage": "Full document administration (reindex, metadata, permissions)",
    "user.create": "Create users",
    "user.edit": "Edit users",
    "user.delete": "Delete or disable users",
    "role.assign": "Assign roles to users",
    "permission.manage": "Manage ACLs and ABAC policies",
    "tenant.manage": "Manage tenants",
    "evaluation.run": "Run offline evaluations",
    "evaluation.rate": "Rate evaluation items",
    "evaluation.adjudicate": "Adjudicate rating disagreements",
    "evaluation.view": "View evaluation results and metrics",
    "observability.view": "View traces and latency metrics",
    "audit.view": "View audit logs",
    "model.manage": "Manage model configuration",
    "chat.query": "Query the RAG assistant",
    "prompt.manage": "Manage prompt versions and experiments",
    "admin.dashboard": "Access the admin dashboard",
}

SYSTEM_ROLES: dict[str, dict[str, str]] = {
    "owner": {
        "description": "Tenant owner. Full access including all document ACLs.",
        "permissions": list(PERMISSIONS.keys()),
    },
    "admin": {
        "description": "Tenant administrator. Full administrative access.",
        "permissions": list(PERMISSIONS.keys()),
    },
    "manager": {
        "description": "Manager. Administration minus tenant/user deletion.",
        "permissions": [
            "document.read", "document.upload", "document.manage",
            "user.create", "user.edit", "role.assign",
            "permission.manage", "evaluation.run", "evaluation.view",
            "observability.view", "audit.view", "chat.query",
        ],
    },
    "employee": {
        "description": "Standard employee with chat and document access as granted.",
        "permissions": ["document.read", "chat.query", "evaluation.rate", "evaluation.view"],
    },
    "lecturer": {
        "description": "Lecturer. Can manage documents and view their course workspace.",
        "permissions": [
            "document.read", "document.upload", "document.manage",
            "permission.manage", "evaluation.view", "chat.query",
        ],
    },
    "student": {
        "description": "Student. Can chat and read documents granted to them.",
        "permissions": ["document.read", "chat.query"],
    },
}


@dataclass
class Identity:
    user_id: str
    tenant_id: str
    username: str
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    department: str | None = None
    email: str | None = None
    full_name: str | None = None


def resolve_role_permissions(role_names: list[str], role_map: dict[str, set[str]]) -> set[str]:
    perms: set[str] = set()
    for r in role_names:
        perms |= role_map.get(r, set())
    return perms
