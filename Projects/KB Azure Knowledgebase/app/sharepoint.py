import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_WEBHOOK_URL = os.getenv("POWER_AUTOMATE_WEBHOOK_URL", "")


def webhook_configured() -> bool:
    return bool(_WEBHOOK_URL)


def notify_published(item) -> None:
    """
    POST item metadata to the Power Automate HTTP trigger when an item is published.
    Runs as a background task — failures are logged but never block the status change.

    Expected Power Automate flow:
      HTTP Request trigger → SharePoint (Create file + Set metadata columns)

    Payload fields map directly to SharePoint column names — the flow owner
    can rename/map them however their library is structured.
    """
    if not webhook_configured():
        logger.info("POWER_AUTOMATE_WEBHOOK_URL not set — SharePoint sync skipped for item %s", item.id)
        return

    payload = {
        "item_id":         item.id,
        "title":           item.title,
        "summary":         item.summary or "",
        "text_content":    item.text_content or "",
        "department":      item.department.name if item.department else "",
        "document_type":   item.document_type.name if item.document_type else "",
        "source":          item.source.name if item.source else "",
        "owner":           item.owner.username if item.owner else "",
        "review_due_date": item.review_due_date.strftime("%Y-%m-%d") if item.review_due_date else "",
        "published_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        response = httpx.post(_WEBHOOK_URL, json=payload, timeout=15.0)
        response.raise_for_status()
        logger.info("Power Automate notified successfully for item %d", item.id)
    except httpx.TimeoutException:
        logger.warning("Power Automate webhook timed out for item %d", item.id)
    except httpx.HTTPStatusError as e:
        logger.warning("Power Automate webhook returned %s for item %d", e.response.status_code, item.id)
    except Exception as e:
        logger.warning("Power Automate webhook failed for item %d: %s", item.id, e)
