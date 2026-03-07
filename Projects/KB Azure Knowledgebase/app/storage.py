import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")
_ACCOUNT_KEY  = os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "")
_CONTAINER    = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "kb-files")

# Local fallback storage directory (dev only — when Azure Storage not configured)
_LOCAL_UPLOAD_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", "./uploads"))

UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_MB", "20")) * 1024 * 1024


def blob_configured() -> bool:
    return bool(_ACCOUNT_NAME and _ACCOUNT_KEY)


def _service_client():
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient(
        account_url=f"https://{_ACCOUNT_NAME}.blob.core.windows.net",
        credential=_ACCOUNT_KEY,
    )


def _sanitise_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200]


def upload_file(item_id: int, filename: str, data: bytes, mime_type: str) -> str:
    """Upload bytes to Azure Blob Storage (prod) or local disk (dev). Returns the blob name."""
    safe_name = _sanitise_filename(filename)
    blob_name = f"items/{item_id}/{uuid.uuid4().hex}_{safe_name}"

    if blob_configured():
        from azure.storage.blob import ContentSettings
        blob_client = _service_client().get_blob_client(container=_CONTAINER, blob=blob_name)
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=mime_type),
        )
    else:
        dest = _LOCAL_UPLOAD_DIR / blob_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    return blob_name


def local_file_path(blob_name: str) -> Path:
    """Absolute path to a locally stored file (dev only)."""
    return (_LOCAL_UPLOAD_DIR / blob_name).resolve()


def presign_url(blob_name: str, expiry: int = 3600) -> str:
    """Return a time-limited SAS URL for Azure Blob Storage, or a local serve path for dev."""
    if not blob_name:
        return ""
    if blob_configured():
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        sas_token = generate_blob_sas(
            account_name=_ACCOUNT_NAME,
            container_name=_CONTAINER,
            blob_name=blob_name,
            account_key=_ACCOUNT_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expiry),
        )
        return (
            f"https://{_ACCOUNT_NAME}.blob.core.windows.net"
            f"/{_CONTAINER}/{blob_name}?{sas_token}"
        )
    return f"/files/{blob_name}"


def delete_file(blob_name: str) -> None:
    """Delete from Azure Blob Storage or local disk. Best-effort — no exception on missing."""
    try:
        if blob_configured():
            blob_client = _service_client().get_blob_client(container=_CONTAINER, blob=blob_name)
            blob_client.delete_blob()
        else:
            p = local_file_path(blob_name)
            if p.exists():
                p.unlink()
    except Exception:
        pass
