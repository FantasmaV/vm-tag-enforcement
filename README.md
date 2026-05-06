# vm-tag-enforcement

**Aria Automation ABX Action — Enterprise VM Tag Enforcement**

Validates that all required tags are present and contain valid values before VM provisioning completes in VMware Aria Automation. Blocks deployment on policy violations, ensuring consistent tagging across the entire VM estate for cost tracking, ownership accountability, and lifecycle management.

---

## Required Tags

| Tag | Format | Example |
|---|---|---|
| `owner` | Valid email address | `rbarden@company.com` |
| `costCenter` | `CC-{4 digits}` | `CC-1234` |
| `environment` | Allowed values only | `PROD` |
| `application` | 3–50 characters | `WebPortal` |
| `expirationDate` | `YYYY-MM-DD` (future date) | `2026-12-31` |

**Allowed environments:** `PROD`, `DEV`, `TEST`, `UAT`, `STG`, `DR`

---

## Request Types

| Type | Description |
|---|---|
| `VALIDATE` | Check all tags, return violations without blocking provisioning |
| `ENFORCE` | Check all tags, **block provisioning** if any violations found |
| `REMEDIATE` | Auto-apply defaults for missing tags where possible, then validate |

---

## Remediation Defaults

| Tag | Remediable | Source |
|---|---|---|
| `owner` | ✅ | `DEFAULT_OWNER` env var |
| `costCenter` | ✅ | `DEFAULT_COST_CENTER` env var |
| `expirationDate` | ✅ | Today + `DEFAULT_EXPIRATION_DAYS` |
| `environment` | ❌ | Must be explicit — cannot auto-default |
| `application` | ❌ | Must be explicit — cannot auto-default |

---

## Inputs / Outputs

**Inputs (from Aria blueprint):**

| Key | Type | Required | Description |
|---|---|---|---|
| `vmName` | string | ✅ | Target VM name |
| `requestType` | string | ✅ | VALIDATE / ENFORCE / REMEDIATE |
| `tags` | dict | ✅ | Tag key-value pairs to validate |

**Outputs:**

| Key | Type | Description |
|---|---|---|
| `status` | string | `compliant` / `violation` / `remediated` |
| `vmName` | string | Target VM name |
| `tags` | dict | Final tag set after validation/remediation |
| `violations` | list | List of violation detail strings |
| `violationCount` | int | Number of violations found |
| `message` | string | Human-readable result summary |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_OWNER` | `""` | Fallback owner email for REMEDIATE mode |
| `DEFAULT_COST_CENTER` | `""` | Fallback cost center for REMEDIATE mode |
| `DEFAULT_EXPIRATION_DAYS` | `90` | Days from today for default expiration date |

---

## Running Tests

```bash
pip install pytest
pytest tests/test_tag_enforcement.py -v
```

---

## Author

**Randolph Barden** — [@FantasmaV](https://github.com/FantasmaV)

Senior VCF / Aria Automation Engineer | VMware by Broadcom

