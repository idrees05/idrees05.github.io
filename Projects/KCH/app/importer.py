"""
CSV importer for KCH UAT test scripts.
Reads Everyday Users, Power Users, Specialist Users, and Master Index CSVs.
Enriches each row with category/is_exploratory from Master Index.
Upserts to test_scripts table; deactivates scripts not seen in import.
"""
import csv
import hashlib
import io
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models import TestScript

load_dotenv()

logger = logging.getLogger(__name__)

CSV_DIR = Path(os.getenv("CSV_DIR", "../"))

TESTER_FILES = {
    "everyday": "KCH_Copilot_UAT_Test_Scripts_Final - Everyday Users.csv",
    "power": "KCH_Copilot_UAT_Test_Scripts_Final - Power Users.csv",
    "specialist": "KCH_Copilot_UAT_Test_Scripts_Final - Specialist Users.csv",
}

MASTER_INDEX_FILE = "KCH_Copilot_UAT_Test_Scripts_Final - Master Index.csv"

TESTER_SHEET_MAP: dict[str, list[str]] = {
    "script_id":              ["Test Script ID", "Script ID", "ID"],
    "user_story_id":          ["Related User Story ID", "User Story ID"],
    "title":                  ["Test Title", "Title"],
    "scenario":               ["Test Script", "Scenario", "Description"],
    "expected_outcome":       ["Expected Outcome", "Expected Result"],
    "preconditions":          ["Preconditions (user role)", "Preconditions"],
    "required_test_data":     ["Required test data", "Required Test Data"],
    "test_steps":             ["Test Steps", "Steps"],
    "recommended_tester_type": ["Recommended Tester Type", "Tester Type"],
}

MASTER_INDEX_MAP: dict[str, list[str]] = {
    "script_id":    ["Test Script ID"],
    "category":     ["Category"],
    "is_exploratory": ["Exploratory?"],
    "source_sheet": ["Tab"],
}

SHEET_TO_TYPE = {
    "Everyday Users":   "everyday",
    "Power Users":      "power",
    "Specialist Users": "specialist",
}

ALLOWED_OUTCOMES = {"Pass", "Fail", "Blocked", "Not Tested"}


def _detect_col(headers: list[str], aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in headers:
            return alias
    return None


def _build_col_map(headers: list[str], field_map: dict[str, list[str]]) -> dict[str, str | None]:
    return {field: _detect_col(headers, aliases) for field, aliases in field_map.items()}


def _row_hash(data: dict) -> str:
    content = "|".join([
        data.get("title", "") or "",
        data.get("test_steps", "") or "",
        data.get("expected_outcome", "") or "",
        data.get("scenario", "") or "",
        data.get("preconditions", "") or "",
    ])
    return hashlib.md5(content.encode()).hexdigest()


def _load_master_index(csv_dir: Path) -> dict[str, dict]:
    path = csv_dir / MASTER_INDEX_FILE
    if not path.exists():
        logger.warning("Master index not found at %s", path)
        return {}

    index: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        col_map = _build_col_map(headers, MASTER_INDEX_MAP)

        for row in reader:
            sid_col = col_map.get("script_id")
            if not sid_col:
                continue
            sid = (row.get(sid_col) or "").strip()
            if not sid:
                continue
            cat_col = col_map.get("category")
            exp_col = col_map.get("is_exploratory")
            src_col = col_map.get("source_sheet")
            index[sid] = {
                "category": (row.get(cat_col) or "").strip() if cat_col else "",
                "is_exploratory": (row.get(exp_col) or "").strip().lower() == "yes" if exp_col else False,
                "source_sheet": (row.get(src_col) or "").strip() if src_col else "",
            }
    return index


def run_import(db: Session, csv_dir: Path | None = None) -> dict[str, Any]:
    if csv_dir is None:
        csv_dir = CSV_DIR

    master = _load_master_index(csv_dir)
    seen_ids: set[str] = set()
    counts = {"inserted": 0, "updated": 0, "deactivated": 0, "skipped": 0, "errors": []}

    for tester_type, filename in TESTER_FILES.items():
        path = csv_dir / filename
        if not path.exists():
            counts["errors"].append(f"File not found: {path}")
            logger.warning("CSV not found: %s", path)
            continue

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            col_map = _build_col_map(headers, TESTER_SHEET_MAP)

            for row_num, row in enumerate(reader, start=2):
                sid_col = col_map.get("script_id")
                if not sid_col:
                    counts["errors"].append(f"{filename}: Cannot find script_id column")
                    break

                sid = (row.get(sid_col) or "").strip()
                if not sid:
                    continue

                steps_col = col_map.get("test_steps")
                steps = (row.get(steps_col) or "").strip() if steps_col else ""
                if not steps:
                    counts["skipped"] += 1
                    counts["errors"].append(f"{filename} row {row_num}: {sid} has empty test_steps — skipped")
                    continue

                title_col = col_map.get("title")
                title = (row.get(title_col) or "").strip() if title_col else sid

                def get(field: str) -> str:
                    col = col_map.get(field)
                    return (row.get(col) or "").strip() if col else ""

                enrichment = master.get(sid, {})
                data = {
                    "script_id": sid,
                    "tester_type": tester_type,
                    "source_sheet": enrichment.get("source_sheet") or SHEET_TO_TYPE.get(tester_type, tester_type),
                    "user_story_id": get("user_story_id"),
                    "title": title,
                    "scenario": get("scenario"),
                    "expected_outcome": get("expected_outcome"),
                    "preconditions": get("preconditions"),
                    "required_test_data": get("required_test_data"),
                    "test_steps": steps,
                    "category": enrichment.get("category", ""),
                    "is_exploratory": enrichment.get("is_exploratory", False),
                    "recommended_tester_type": get("recommended_tester_type"),
                }
                data["row_hash"] = _row_hash(data)
                seen_ids.add(sid)

                existing: TestScript | None = db.get(TestScript, sid)
                if existing is None:
                    db.add(TestScript(**data, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
                    counts["inserted"] += 1
                elif existing.row_hash != data["row_hash"]:
                    for k, v in data.items():
                        setattr(existing, k, v)
                    existing.updated_at = datetime.utcnow()
                    existing.is_active = True
                    counts["updated"] += 1
                # else: unchanged, skip

    # Deactivate scripts from standard types that are no longer in the CSVs.
    # Custom-type scripts (uploaded via admin upload) are never touched here.
    standard_types = set(TESTER_FILES.keys())
    all_active_standard = db.query(TestScript).filter(
        TestScript.is_active == True,
        TestScript.tester_type.in_(standard_types),
    ).all()
    for script in all_active_standard:
        if script.script_id not in seen_ids:
            script.is_active = False
            counts["deactivated"] += 1

    db.commit()
    counts["total_active"] = db.query(TestScript).filter(TestScript.is_active == True).count()
    return counts


def import_from_upload(db: Session, tester_type: str, content: str) -> dict[str, Any]:
    """Upsert scripts from an uploaded CSV. Does not deactivate existing scripts."""
    counts = {"inserted": 0, "updated": 0, "deactivated": 0, "skipped": 0, "errors": []}

    reader = csv.DictReader(io.StringIO(content))
    headers = list(reader.fieldnames or [])
    col_map = _build_col_map(headers, TESTER_SHEET_MAP)

    sid_col = col_map.get("script_id")
    if not sid_col:
        counts["errors"].append("Missing Script ID column (expected: 'Test Script ID', 'Script ID', or 'ID')")
        return counts

    steps_col = col_map.get("test_steps")
    if not steps_col:
        counts["errors"].append("Missing Test Steps column (expected: 'Test Steps' or 'Steps')")
        return counts

    for row_num, row in enumerate(reader, start=2):
        sid = (row.get(sid_col) or "").strip()
        if not sid:
            continue
        steps = (row.get(steps_col) or "").strip()
        if not steps:
            counts["skipped"] += 1
            counts["errors"].append(f"Row {row_num}: {sid} — empty test_steps, skipped")
            continue

        title_col = col_map.get("title")
        title = (row.get(title_col) or "").strip() if title_col else sid

        def get(field, _row=row, _col_map=col_map):
            col = _col_map.get(field)
            return (_row.get(col) or "").strip() if col else ""

        data = {
            "script_id": sid,
            "tester_type": tester_type,
            "source_sheet": tester_type,
            "user_story_id": get("user_story_id"),
            "title": title,
            "scenario": get("scenario"),
            "expected_outcome": get("expected_outcome"),
            "preconditions": get("preconditions"),
            "required_test_data": get("required_test_data"),
            "test_steps": steps,
            "category": get("category"),
            "is_exploratory": False,
            "recommended_tester_type": get("recommended_tester_type"),
        }
        data["row_hash"] = _row_hash(data)

        existing = db.get(TestScript, sid)
        if existing is None:
            db.add(TestScript(**data, is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
            counts["inserted"] += 1
        elif existing.row_hash != data["row_hash"]:
            for k, v in data.items():
                setattr(existing, k, v)
            existing.updated_at = datetime.utcnow()
            existing.is_active = True
            counts["updated"] += 1

    db.commit()
    counts["total_active"] = db.query(TestScript).filter(TestScript.is_active == True).count()
    return counts
