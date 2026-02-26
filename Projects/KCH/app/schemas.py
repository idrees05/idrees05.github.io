from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


class StartRunRequest(BaseModel):
    tester_name: str
    tester_email: str
    tester_type: str
    department: Optional[str] = None
    environment: str
    device: Optional[str] = None
    browser: Optional[str] = None
    access_issues: bool = False
    access_issues_notes: Optional[str] = None

    @field_validator("tester_email")
    @classmethod
    def email_must_be_nhs(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.endswith("@nhs.net"):
            raise ValueError("Email must end with @nhs.net")
        return v

    @field_validator("tester_type")
    @classmethod
    def valid_tester_type(cls, v: str) -> str:
        allowed = {"everyday", "power", "specialist"}
        if v.lower() not in allowed:
            raise ValueError(f"tester_type must be one of {allowed}")
        return v.lower()

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, v: str) -> str:
        allowed = {"DEV", "TEST", "UAT", "PROD"}
        if v.upper() not in allowed:
            return v  # allow free-text fallback
        return v.upper()


class SaveResultRequest(BaseModel):
    outcome: Optional[str] = None
    failure_category: Optional[str] = None
    happened: Optional[str] = None
    expected_instead: Optional[str] = None
    retest_needed: bool = False
    comments: Optional[str] = None

    @field_validator("outcome")
    @classmethod
    def valid_outcome(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"Pass", "Fail", "Blocked", "Not Tested"}
        if v not in allowed:
            raise ValueError(f"outcome must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def failure_fields_required(self) -> "SaveResultRequest":
        if self.outcome in ("Fail", "Blocked"):
            if not self.failure_category:
                raise ValueError("failure_category is required when outcome is Fail or Blocked")
            if not self.happened:
                raise ValueError("happened is required when outcome is Fail or Blocked")
        return self


class ScriptOut(BaseModel):
    script_id: str
    title: str
    scenario: Optional[str]
    expected_outcome: Optional[str]
    preconditions: Optional[str]
    required_test_data: Optional[str]
    test_steps: str
    category: Optional[str]
    is_exploratory: bool
    tester_type: str

    model_config = {"from_attributes": True}


class ResultOut(BaseModel):
    result_id: str
    run_id: str
    script_id: str
    outcome: Optional[str]
    failure_category: Optional[str]
    happened: Optional[str]
    expected_instead: Optional[str]
    retest_needed: bool
    comments: Optional[str]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    evidence_id: str
    result_id: str
    evidence_type: str
    file_name: Optional[str]
    file_size: Optional[int]
    url: Optional[str]
    uploaded_at: Optional[datetime]

    model_config = {"from_attributes": True}
