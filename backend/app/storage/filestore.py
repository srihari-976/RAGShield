import hashlib
import shutil
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()
BASE = Path(settings.file_storage_path).resolve()


class FileStore:
    """Filesystem object store: data/files/{tenant_id}/{document_id}/..."""

    def ensure_tenant_dir(self, tenant_id: str) -> Path:
        p = BASE / tenant_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_original(self, tenant_id: str, document_id: str, filename: str, content: bytes) -> str:
        doc_dir = BASE / tenant_id / document_id / "original"
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / filename
        path.write_bytes(content)
        return str(path)

    def save_extracted(self, tenant_id: str, document_id: str, filename: str, content: bytes) -> str:
        doc_dir = BASE / tenant_id / document_id / "extracted"
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / filename
        path.write_bytes(content)
        return str(path)

    def read(self, relative_path: str) -> bytes:
        p = Path(relative_path)
        if not p.is_absolute():
            p = BASE / p
        return p.read_bytes()

    def delete_document(self, tenant_id: str, document_id: str) -> None:
        doc_dir = BASE / tenant_id / document_id
        if doc_dir.exists():
            shutil.rmtree(doc_dir)

    @staticmethod
    def checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()


file_store = FileStore()
