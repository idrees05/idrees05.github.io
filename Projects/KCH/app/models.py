from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from database import Base


class User(Base):
    __tablename__ = "users"

    user_id       = Column(String, primary_key=True)
    email         = Column(String, unique=True, nullable=False, index=True)
    name          = Column(String, nullable=False)
    department    = Column(String)
    password_hash = Column(String, nullable=False)
    tester_types  = Column(Text, default="[]")   # JSON list of tester-type slugs
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login    = Column(DateTime)


class TesterType(Base):
    __tablename__ = "tester_types"
    slug        = Column(String, primary_key=True)   # e.g. "everyday"
    label       = Column(String, nullable=False)      # e.g. "Everyday Users"
    description = Column(String, default="")          # shown on start form
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)


class TestScript(Base):
    __tablename__ = "test_scripts"

    script_id = Column(String, primary_key=True)
    source_sheet = Column(String)
    tester_type = Column(String)
    user_story_id = Column(String)
    title = Column(Text, nullable=False)
    scenario = Column(Text)
    expected_outcome = Column(Text)
    preconditions = Column(Text)
    required_test_data = Column(Text)
    test_steps = Column(Text, nullable=False)
    category = Column(String)
    is_exploratory = Column(Boolean, default=False)
    recommended_tester_type = Column(String)
    row_hash = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TestRun(Base):
    __tablename__ = "test_runs"

    run_id = Column(String, primary_key=True)
    tester_name = Column(String, nullable=False)
    tester_email = Column(String, nullable=False)
    tester_type = Column(String, nullable=False)
    department = Column(String)
    environment = Column(String, nullable=False)
    device = Column(String)
    browser = Column(String)
    access_issues = Column(Boolean, default=False)
    access_issues_notes = Column(Text)
    status = Column(String, default="IN_PROGRESS")
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime)


class TestResult(Base):
    __tablename__ = "test_results"

    result_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("test_runs.run_id"), nullable=False)
    script_id = Column(String, ForeignKey("test_scripts.script_id"), nullable=False)
    outcome = Column(String)
    failure_category = Column(String)
    happened = Column(Text)
    expected_instead = Column(Text)
    retest_needed = Column(Boolean, default=False)
    comments = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("run_id", "script_id", name="uq_run_script"),)


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id = Column(String, primary_key=True)
    result_id = Column(String, ForeignKey("test_results.result_id"), nullable=False)
    evidence_type = Column(String)  # 'file' | 'url'
    file_path = Column(String)
    file_name = Column(String)
    file_size = Column(Integer)
    mime_type = Column(String)
    url = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
