"""
tag_enforcement.py
------------------
Aria Automation ABX Action — Enterprise VM Tag Enforcement

Validates that all required tags are present and contain valid values
before VM provisioning completes. Blocks deployment on policy violations,
ensuring consistent tagging across the entire VM estate for cost tracking,
ownership accountability, and lifecycle management.

Required Tags:
    owner           Valid email address of the VM owner
    costCenter      Cost center code matching CC-{4 digits} format
    environment     One of: PROD, DEV, TEST, UAT, STG, DR
    application     Application name this VM supports (3-50 chars)
    expirationDate  VM lease date in YYYY-MM-DD format (must be future date)

Request Types:
    VALIDATE    → Check all tags, return violations without blocking
    ENFORCE     → Check all tags, raise immediately if any violations found
    REMEDIATE   → Apply default values for missing tags where possible

Environment Variables (set in Aria Automation ABX Action properties):
    DEFAULT_OWNER           Fallback owner email if not provided
    DEFAULT_COST_CENTER     Fallback cost center if not provided
    DEFAULT_EXPIRATION_DAYS Days from today for default expiration (default: 90)

Author: Randolph Barden
Repo:   github.com/FantasmaV/vm-tag-enforcement
"""

import os
import re
import logging
from datetime import datetime, timezone, timedelta

# ── Logging ────────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Policy Definitions ─────────────────────────────────────────────────────────

REQUIRED_TAGS = ["owner", "costCenter", "environment", "application", "expirationDate"]

ALLOWED_ENVIRONMENTS = {"PROD", "DEV", "TEST", "UAT", "STG", "DR"}

ALLOWED_REQUEST_TYPES = {"VALIDATE", "ENFORCE", "REMEDIATE"}

# Validation patterns
EMAIL_PATTERN       = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
COST_CENTER_PATTERN = re.compile(r"^CC-\d{4}$")
DATE_PATTERN        = re.compile(r"^\d{4}-\d{2}-\d{2}$")
APP_NAME_MIN        = 3
APP_NAME_MAX        = 50

# Environment variable defaults
DEFAULT_OWNER           = os.environ.get("DEFAULT_OWNER", "")
DEFAULT_COST_CENTER     = os.environ.get("DEFAULT_COST_CENTER", "")
DEFAULT_EXPIRATION_DAYS = int(os.environ.get("DEFAULT_EXPIRATION_DAYS", "90"))


# ── ABX Entry Point ────────────────────────────────────────────────────────────
def handler(context, inputs: dict) -> dict:
    """
    ABX handler called by Aria Automation during VM provisioning.

    Validates required tags against enterprise policy rules and routes
    to the appropriate action based on requestType.

    Args:
        context: Aria Automation execution context (unused directly).
        inputs:  Dictionary of inputs passed from the Aria blueprint.
                 Expected keys:
                   - vmName (str):       Target VM name.
                   - requestType (str):  VALIDATE / ENFORCE / REMEDIATE.
                   - tags (dict):        Tag key-value pairs to validate.

    Returns:
        dict with keys:
          - status (str):         "compliant" / "violation" / "remediated"
          - vmName (str):         Target VM name.
          - tags (dict):          Final tag set after validation/remediation.
          - violations (list):    List of violation detail strings.
          - violationCount (int): Number of violations found.
          - message (str):        Human-readable result summary.

    Raises:
        ValueError: If ENFORCE mode detects tag violations.
        KeyError:   If required inputs are missing from blueprint.
    """
    logger.info("[tags] Starting tag enforcement evaluation")

    # ── Extract inputs ────────────────────────────────────────────────────────
    try:
        vm_name      = inputs["vmName"].strip()
        request_type = inputs["requestType"].strip().upper()
    except KeyError as e:
        raise KeyError(f"Required input missing from blueprint: {e}")

    tags = inputs.get("tags", {})
    if not isinstance(tags, dict):
        raise ValueError(
            f"'tags' must be a dictionary of key-value pairs, "
            f"got {type(tags).__name__}"
        )

    logger.info(
        f"[tags] VM: {vm_name} | REQUEST: {request_type} | "
        f"Tags provided: {list(tags.keys())}"
    )

    # ── Validate request type ─────────────────────────────────────────────────
    if request_type not in ALLOWED_REQUEST_TYPES:
        raise ValueError(
            f"Invalid requestType '{request_type}'. "
            f"Allowed values: {sorted(ALLOWED_REQUEST_TYPES)}"
        )

    # ── Route to handler ──────────────────────────────────────────────────────
    if request_type == "VALIDATE":
        return handle_validate(vm_name, tags)
    elif request_type == "ENFORCE":
        return handle_enforce(vm_name, tags)
    elif request_type == "REMEDIATE":
        return handle_remediate(vm_name, tags)


# ── VALIDATE Handler ───────────────────────────────────────────────────────────
def handle_validate(vm_name: str, tags: dict) -> dict:
    """
    Validate all required tags and return results without blocking.

    Args:
        vm_name: Target VM name for logging.
        tags:    Dictionary of tag key-value pairs.

    Returns:
        dict: Validation result with violations list and compliance status.
    """
    logger.info(f"[tags] Processing VALIDATE for {vm_name}")

    violations = validate_tags(tags)
    is_compliant = len(violations) == 0
    status = "compliant" if is_compliant else "violation"

    logger.info(
        f"[tags] VALIDATE result — compliant: {is_compliant} | "
        f"violations: {len(violations)}"
    )

    return {
        "status":         status,
        "vmName":         vm_name,
        "tags":           tags,
        "violations":     violations,
        "violationCount": len(violations),
        "message": (
            f"All required tags are valid for '{vm_name}'."
            if is_compliant else
            f"{len(violations)} tag violation(s) found for '{vm_name}'. "
            f"Review violations and correct before provisioning."
        ),
    }


# ── ENFORCE Handler ────────────────────────────────────────────────────────────
def handle_enforce(vm_name: str, tags: dict) -> dict:
    """
    Validate all required tags and BLOCK provisioning if violations exist.

    Args:
        vm_name: Target VM name for logging.
        tags:    Dictionary of tag key-value pairs.

    Returns:
        dict: Compliance result if all tags are valid.

    Raises:
        ValueError: If any tag violations are found.
    """
    logger.info(f"[tags] Processing ENFORCE for {vm_name}")

    violations = validate_tags(tags)

    if violations:
        violation_text = "\n".join(f"  • {v}" for v in violations)
        raise ValueError(
            f"VM provisioning BLOCKED for '{vm_name}' — "
            f"{len(violations)} tag policy violation(s):\n{violation_text}\n"
            f"Correct all tag violations before resubmitting the provisioning request."
        )

    logger.info(f"[tags] ENFORCE passed — all tags valid for {vm_name}")

    return {
        "status":         "compliant",
        "vmName":         vm_name,
        "tags":           tags,
        "violations":     [],
        "violationCount": 0,
        "message":        f"All required tags are valid. Provisioning approved for '{vm_name}'.",
    }


# ── REMEDIATE Handler ──────────────────────────────────────────────────────────
def handle_remediate(vm_name: str, tags: dict) -> dict:
    """
    Apply default values for missing tags where defaults are available,
    then validate the remediated tag set.

    Remediable tags (if environment variables are set):
        owner           → DEFAULT_OWNER env var
        costCenter      → DEFAULT_COST_CENTER env var
        expirationDate  → Today + DEFAULT_EXPIRATION_DAYS

    Non-remediable tags (must be provided by requester):
        environment     → Cannot default — must be explicit
        application     → Cannot default — must be explicit

    Args:
        vm_name: Target VM name for logging.
        tags:    Dictionary of tag key-value pairs.

    Returns:
        dict: Remediation result with updated tags and remaining violations.
    """
    logger.info(f"[tags] Processing REMEDIATE for {vm_name}")

    remediated_tags  = dict(tags)
    remediated_items = []

    # Apply defaults for remediable tags
    if not remediated_tags.get("owner") and DEFAULT_OWNER:
        remediated_tags["owner"] = DEFAULT_OWNER
        remediated_items.append(f"owner → {DEFAULT_OWNER}")
        logger.info(f"[tags] Remediated 'owner' with default: {DEFAULT_OWNER}")

    if not remediated_tags.get("costCenter") and DEFAULT_COST_CENTER:
        remediated_tags["costCenter"] = DEFAULT_COST_CENTER
        remediated_items.append(f"costCenter → {DEFAULT_COST_CENTER}")
        logger.info(f"[tags] Remediated 'costCenter' with default: {DEFAULT_COST_CENTER}")

    if not remediated_tags.get("expirationDate"):
        default_date = (
            datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRATION_DAYS)
        ).strftime("%Y-%m-%d")
        remediated_tags["expirationDate"] = default_date
        remediated_items.append(f"expirationDate → {default_date}")
        logger.info(f"[tags] Remediated 'expirationDate' with default: {default_date}")

    # Validate after remediation
    remaining_violations = validate_tags(remediated_tags)
    is_compliant         = len(remaining_violations) == 0
    status               = "remediated" if remediated_items else (
        "compliant" if is_compliant else "violation"
    )

    logger.info(
        f"[tags] REMEDIATE result — items remediated: {len(remediated_items)} | "
        f"remaining violations: {len(remaining_violations)}"
    )

    return {
        "status":              status,
        "vmName":              vm_name,
        "tags":                remediated_tags,
        "remediatedItems":     remediated_items,
        "violations":          remaining_violations,
        "violationCount":      len(remaining_violations),
        "message": (
            f"Remediated {len(remediated_items)} tag(s) for '{vm_name}'. "
            f"Remaining violations: {len(remaining_violations)}."
            if remediated_items else
            f"No remediation needed for '{vm_name}' — "
            f"{'all tags valid' if is_compliant else f'{len(remaining_violations)} violation(s) require manual correction'}."
        ),
    }


# ── Tag Validation Engine ──────────────────────────────────────────────────────
def validate_tags(tags: dict) -> list:
    """
    Validate all required tags against enterprise policy rules.

    Checks:
        - All required tags are present
        - owner: valid email format
        - costCenter: matches CC-{4 digits} pattern
        - environment: one of the allowed environment values
        - application: between 3 and 50 characters
        - expirationDate: valid YYYY-MM-DD format and must be a future date

    Args:
        tags: Dictionary of tag key-value pairs to validate.

    Returns:
        list: List of violation strings. Empty list means fully compliant.
    """
    violations = []

    # ── Check for missing required tags ───────────────────────────────────────
    for required_tag in REQUIRED_TAGS:
        if required_tag not in tags or not str(tags[required_tag]).strip():
            violations.append(
                f"Missing required tag: '{required_tag}'"
            )

    # ── Validate owner ────────────────────────────────────────────────────────
    owner = str(tags.get("owner", "")).strip()
    if owner and not EMAIL_PATTERN.match(owner):
        violations.append(
            f"Invalid 'owner' tag value '{owner}'. "
            f"Must be a valid email address (e.g. jsmith@company.com)."
        )

    # ── Validate costCenter ───────────────────────────────────────────────────
    cost_center = str(tags.get("costCenter", "")).strip()
    if cost_center and not COST_CENTER_PATTERN.match(cost_center):
        violations.append(
            f"Invalid 'costCenter' tag value '{cost_center}'. "
            f"Must match format CC-NNNN (e.g. CC-1234)."
        )

    # ── Validate environment ──────────────────────────────────────────────────
    environment = str(tags.get("environment", "")).strip().upper()
    if environment and environment not in ALLOWED_ENVIRONMENTS:
        violations.append(
            f"Invalid 'environment' tag value '{environment}'. "
            f"Allowed values: {sorted(ALLOWED_ENVIRONMENTS)}."
        )

    # ── Validate application ──────────────────────────────────────────────────
    application = str(tags.get("application", "")).strip()
    if application:
        if len(application) < APP_NAME_MIN:
            violations.append(
                f"Invalid 'application' tag value '{application}'. "
                f"Must be at least {APP_NAME_MIN} characters."
            )
        elif len(application) > APP_NAME_MAX:
            violations.append(
                f"Invalid 'application' tag value — too long ({len(application)} chars). "
                f"Maximum is {APP_NAME_MAX} characters."
            )

    # ── Validate expirationDate ───────────────────────────────────────────────
    expiration = str(tags.get("expirationDate", "")).strip()
    if expiration:
        if not DATE_PATTERN.match(expiration):
            violations.append(
                f"Invalid 'expirationDate' tag value '{expiration}'. "
                f"Must be in YYYY-MM-DD format (e.g. 2026-12-31)."
            )
        else:
            try:
                exp_date = datetime.strptime(expiration, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if exp_date <= datetime.now(timezone.utc):
                    violations.append(
                        f"Invalid 'expirationDate' tag value '{expiration}'. "
                        f"Expiration date must be a future date."
                    )
            except ValueError:
                violations.append(
                    f"Invalid 'expirationDate' tag value '{expiration}'. "
                    f"Date is not a valid calendar date."
                )

    return violations
