import os
import re
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

_R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID", "")
_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
_BUCKET = os.getenv("R2_BUCKET_NAME", "")
_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")

# Local fallback storage directory (dev only)
_LOCAL_UPLOAD_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", "./uploads"))

UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_MB", "20")) * 1024 * 1024


def r2_configured() -> bool:
    return bool(_R2_ACCOUNT_ID and _ACCESS_KEY and _SECRET_KEY and _BUCKET)


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=_ACCESS_KEY,
        aws_secret_access_key=_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _sanitise_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200]


def upload_file(item_id: int, filename: str, data: bytes, mime_type: str) -> str:
    """Upload bytes to R2 (prod) or local disk (dev). Returns a storage key."""
    safe_name = _sanitise_filename(filename)
    key = f"items/{item_id}/{uuid.uuid4().hex}_{safe_name}"

    if r2_configured():
        _client().put_object(
            Bucket=_BUCKET,
            Key=key,
            Body=data,
            ContentType=mime_type,
        )
    else:
        # Local disk fallback for dev
        dest = _LOCAL_UPLOAD_DIR / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    return key


def local_file_path(r2_key: str) -> Path:
    """Absolute path to a locally stored file."""
    return (_LOCAL_UPLOAD_DIR / r2_key).resolve()


def presign_url(r2_key: str, expiry: int = 3600) -> str:
    """Return a download URL. Presigned for R2; local serve path for dev."""
    if r2_configured():
        if _PUBLIC_URL:
            return f"{_PUBLIC_URL}/{r2_key}"
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _BUCKET, "Key": r2_key},
            ExpiresIn=expiry,
        )
    # Local dev: return a route the app serves directly
    return f"/files/{r2_key}"


def delete_file(r2_key: str) -> None:
    """Delete from R2 or local disk. Best-effort, no exception on missing."""
    try:
        if r2_configured():
            _client().delete_object(Bucket=_BUCKET, Key=r2_key)
        else:
            p = local_file_path(r2_key)
            if p.exists():
                p.unlink()
    except Exception:
        pass
