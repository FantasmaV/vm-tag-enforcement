"""
test_tag_enforcement.py
-----------------------
Unit tests for the Aria Automation ABX Action — VM Tag Enforcement.

Tests cover VALIDATE, ENFORCE, and REMEDIATE request types, all tag
validation rules, and every error path.

Run with:
    pytest tests/test_tag_enforcement.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../abx-actions'))
import tag_enforcement


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_tags():
    """Return a fully compliant tag set."""
    future_date = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")
    return {
        "owner":          "rbarden@company.com",
        "costCenter":     "CC-1234",
        "environment":    "PROD",
        "application":    "WebPortal",
        "expirationDate": future_date,
    }


@pytest.fixture
def base_inputs(valid_tags):
    """Base valid inputs for an ENFORCE request."""
    return {
        "vmName":      "VM-PROD-WEB-TXD-001",
        "requestType": "ENFORCE",
        "tags":        valid_tags,
    }


@pytest.fixture(autouse=True)
def clear_defaults(monkeypatch):
    """Clear default env vars for most tests."""
    monkeypatch.setattr(tag_enforcement, "DEFAULT_OWNER",           "")
    monkeypatch.setattr(tag_enforcement, "DEFAULT_COST_CENTER",     "")
    monkeypatch.setattr(tag_enforcement, "DEFAULT_EXPIRATION_DAYS", 90)


# ── handler() routing tests ────────────────────────────────────────────────────

class TestHandlerRouting:

    def test_raises_on_missing_vm_name(self, base_inputs):
        """handler() should raise KeyError if vmName missing."""
        del base_inputs["vmName"]
        with pytest.raises(KeyError, match="vmName"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_raises_on_invalid_request_type(self, base_inputs):
        """handler() should raise ValueError for unknown requestType."""
        base_inputs["requestType"] = "APPROVE"
        with pytest.raises(ValueError, match="Invalid requestType"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_raises_on_invalid_tags_type(self, base_inputs):
        """handler() should raise ValueError if tags is not a dict."""
        base_inputs["tags"] = ["owner", "costCenter"]
        with pytest.raises(ValueError, match="must be a dictionary"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_defaults_tags_to_empty_dict(self, base_inputs):
        """handler() should default tags to empty dict if not provided."""
        del base_inputs["tags"]
        base_inputs["requestType"] = "VALIDATE"
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["violationCount"] > 0

    def test_normalizes_request_type_lowercase(self, base_inputs):
        """handler() should normalize lowercase requestType."""
        base_inputs["requestType"] = "enforce"
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["status"] == "compliant"


# ── VALIDATE tests ─────────────────────────────────────────────────────────────

class TestHandleValidate:

    def test_validate_compliant_with_valid_tags(self, base_inputs, valid_tags):
        """VALIDATE should return compliant for fully valid tags."""
        base_inputs["requestType"] = "VALIDATE"
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["status"]         == "compliant"
        assert result["violationCount"] == 0
        assert result["violations"]     == []

    def test_validate_returns_violation_for_missing_tags(self, base_inputs):
        """VALIDATE should return violation status for missing tags."""
        base_inputs["requestType"] = "VALIDATE"
        base_inputs["tags"]        = {}
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["status"]         == "violation"
        assert result["violationCount"] == len(tag_enforcement.REQUIRED_TAGS)

    def test_validate_does_not_raise_on_violations(self, base_inputs):
        """VALIDATE should never raise even with violations."""
        base_inputs["requestType"] = "VALIDATE"
        base_inputs["tags"]        = {}
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["status"] == "violation"

    def test_validate_returns_tags_in_result(self, base_inputs, valid_tags):
        """VALIDATE result should include the tag set."""
        base_inputs["requestType"] = "VALIDATE"
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["tags"] == valid_tags


# ── ENFORCE tests ──────────────────────────────────────────────────────────────

class TestHandleEnforce:

    def test_enforce_passes_with_valid_tags(self, base_inputs):
        """ENFORCE should return compliant for fully valid tags."""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["status"]         == "compliant"
        assert result["violationCount"] == 0

    def test_enforce_raises_on_missing_tags(self, base_inputs):
        """ENFORCE should raise ValueError when tags are missing."""
        base_inputs["tags"] = {}
        with pytest.raises(ValueError, match="BLOCKED"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_enforce_raises_on_invalid_owner(self, base_inputs):
        """ENFORCE should raise ValueError for invalid owner email."""
        base_inputs["tags"]["owner"] = "not-an-email"
        with pytest.raises(ValueError, match="BLOCKED"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_enforce_raises_on_invalid_cost_center(self, base_inputs):
        """ENFORCE should raise ValueError for invalid cost center format."""
        base_inputs["tags"]["costCenter"] = "1234"
        with pytest.raises(ValueError, match="BLOCKED"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_enforce_raises_on_past_expiration_date(self, base_inputs):
        """ENFORCE should raise ValueError for past expiration date."""
        base_inputs["tags"]["expirationDate"] = "2020-01-01"
        with pytest.raises(ValueError, match="BLOCKED"):
            tag_enforcement.handler(context=None, inputs=base_inputs)

    def test_enforce_raises_on_invalid_environment(self, base_inputs):
        """ENFORCE should raise ValueError for unknown environment tag."""
        base_inputs["tags"]["environment"] = "STAGE2"
        with pytest.raises(ValueError, match="BLOCKED"):
            tag_enforcement.handler(context=None, inputs=base_inputs)


# ── REMEDIATE tests ────────────────────────────────────────────────────────────

class TestHandleRemediate:

    def test_remediate_applies_default_owner(self, base_inputs, monkeypatch):
        """REMEDIATE should apply DEFAULT_OWNER when owner is missing."""
        monkeypatch.setattr(tag_enforcement, "DEFAULT_OWNER", "default@company.com")
        base_inputs["requestType"]    = "REMEDIATE"
        base_inputs["tags"]["owner"]  = ""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["tags"]["owner"] == "default@company.com"
        assert any("owner" in r for r in result["remediatedItems"])

    def test_remediate_applies_default_cost_center(self, base_inputs, monkeypatch):
        """REMEDIATE should apply DEFAULT_COST_CENTER when costCenter is missing."""
        monkeypatch.setattr(tag_enforcement, "DEFAULT_COST_CENTER", "CC-9999")
        base_inputs["requestType"]         = "REMEDIATE"
        base_inputs["tags"]["costCenter"]  = ""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["tags"]["costCenter"] == "CC-9999"

    def test_remediate_applies_default_expiration_date(self, base_inputs, monkeypatch):
        """REMEDIATE should apply default expiration date when missing."""
        monkeypatch.setattr(tag_enforcement, "DEFAULT_EXPIRATION_DAYS", 30)
        base_inputs["requestType"]            = "REMEDIATE"
        base_inputs["tags"]["expirationDate"] = ""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["tags"]["expirationDate"] != ""
        assert any("expirationDate" in r for r in result["remediatedItems"])

    def test_remediate_cannot_default_environment(self, base_inputs):
        """REMEDIATE should not auto-fill environment — must be explicit."""
        base_inputs["requestType"]         = "REMEDIATE"
        base_inputs["tags"]["environment"] = ""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["violationCount"] > 0

    def test_remediate_cannot_default_application(self, base_inputs):
        """REMEDIATE should not auto-fill application — must be explicit."""
        base_inputs["requestType"]          = "REMEDIATE"
        base_inputs["tags"]["application"]  = ""
        result = tag_enforcement.handler(context=None, inputs=base_inputs)
        assert result["violationCount"] > 0


# ── validate_tags() unit tests ─────────────────────────────────────────────────

class TestValidateTags:

    def test_valid_tags_return_no_violations(self, valid_tags):
        """validate_tags() should return empty list for fully valid tags."""
        assert tag_enforcement.validate_tags(valid_tags) == []

    def test_detects_all_missing_tags(self):
        """validate_tags() should report all 5 required tags as missing."""
        violations = tag_enforcement.validate_tags({})
        assert len(violations) == len(tag_enforcement.REQUIRED_TAGS)

    def test_invalid_email_formats(self, valid_tags):
        """validate_tags() should reject invalid email formats."""
        for bad_email in ["notanemail", "missing@", "@nodomain.com", "no spaces@test.com"]:
            valid_tags["owner"] = bad_email
            violations = tag_enforcement.validate_tags(valid_tags)
            assert any("owner" in v for v in violations)

    def test_valid_email_formats(self, valid_tags):
        """validate_tags() should accept valid email formats."""
        for good_email in ["user@company.com", "r.barden@corp.io", "admin+test@lab.local"]:
            valid_tags["owner"] = good_email
            violations = tag_enforcement.validate_tags(valid_tags)
            assert not any("owner" in v for v in violations)

    def test_invalid_cost_center_formats(self, valid_tags):
        """validate_tags() should reject invalid cost center formats."""
        for bad_cc in ["1234", "CC1234", "CC-12", "CC-12345", "cc-1234"]:
            valid_tags["costCenter"] = bad_cc
            violations = tag_enforcement.validate_tags(valid_tags)
            assert any("costCenter" in v for v in violations)

    def test_valid_cost_center_format(self, valid_tags):
        """validate_tags() should accept CC-NNNN format."""
        valid_tags["costCenter"] = "CC-5678"
        assert tag_enforcement.validate_tags(valid_tags) == []

    def test_invalid_environments(self, valid_tags):
        """validate_tags() should reject unknown environment values."""
        for bad_env in ["STAGING", "PRODUCTION", "QA", "LAB"]:
            valid_tags["environment"] = bad_env
            violations = tag_enforcement.validate_tags(valid_tags)
            assert any("environment" in v for v in violations)

    def test_all_valid_environments(self, valid_tags):
        """validate_tags() should accept all defined environment values."""
        for env in tag_enforcement.ALLOWED_ENVIRONMENTS:
            valid_tags["environment"] = env
            assert tag_enforcement.validate_tags(valid_tags) == []

    def test_application_too_short(self, valid_tags):
        """validate_tags() should reject application names under 3 chars."""
        valid_tags["application"] = "AB"
        violations = tag_enforcement.validate_tags(valid_tags)
        assert any("application" in v for v in violations)

    def test_application_too_long(self, valid_tags):
        """validate_tags() should reject application names over 50 chars."""
        valid_tags["application"] = "A" * 51
        violations = tag_enforcement.validate_tags(valid_tags)
        assert any("application" in v for v in violations)

    def test_past_expiration_date_rejected(self, valid_tags):
        """validate_tags() should reject past expiration dates."""
        valid_tags["expirationDate"] = "2020-01-01"
        violations = tag_enforcement.validate_tags(valid_tags)
        assert any("expirationDate" in v for v in violations)

    def test_future_expiration_date_accepted(self, valid_tags):
        """validate_tags() should accept future expiration dates."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        valid_tags["expirationDate"] = future
        assert tag_enforcement.validate_tags(valid_tags) == []

    def test_invalid_date_format_rejected(self, valid_tags):
        """validate_tags() should reject dates not in YYYY-MM-DD format."""
        for bad_date in ["01/01/2027", "2027.01.01", "Jan 1 2027"]:
            valid_tags["expirationDate"] = bad_date
            violations = tag_enforcement.validate_tags(valid_tags)
            assert any("expirationDate" in v for v in violations)
