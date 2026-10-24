# Zephyr Squad & Jira Server/DC Test Management MCP Server

An enterprise-grade, end-to-end **Model Context Protocol (MCP)** server built by Senior QA Test Architects. It automates the parsing of Jira User Stories, synthesizes structured Zephyr Squad test cases (happy path, negative, boundary value, and authorization), and establishes bidirectional traceability links between Jira Stories and Zephyr Test issues.

---

## 🎯 Key Architectural Capabilities

- **Senior QA Rigor**:
  - Automatically parses Acceptance Criteria from plain text, Jira Wiki markup, and Atlassian Document Format (ADF).
  - Categorizes scenarios into `POSITIVE`, `NEGATIVE`, `BOUNDARY`, `SECURITY`, and `EDGE_CASE`.
  - Enforces deterministic test case anatomy: clear preconditions, sequential actions, exact test inputs, and verifiable expected results.
- **Two-Phase Human-in-the-Loop Safety**:
  - **Phase 1 (Safe Read-Only)**: `generate_test_plan` creates and caches an exhaustive test plan with full traceability mapping without mutating remote systems.
  - **Phase 2 (Controlled Execution)**: `publish_test_plan` executes remote mutations (creates Jira `Test` issues, adds steps via Zephyr ZAPI, and establishes bidirectional issue links) only upon explicit review.
- **Zephyr Squad (ZAPI) Native Integration**:
  - Uses native Jira Server / Data Center `Test` issue types.
  - Utilizes Zephyr Squad ZAPI (`/rest/zapi/latest/teststep/{issueId}`) with built-in retry backoff for transient HTTP errors.
- **Deterministic Idempotency**:
  - Computes SHA256 hashes of test specifications to prevent accidental duplication during re-runs.

---

## 🛠️ MCP Tool Reference

| Tool Name | Phase / Mode | Description |
| :--- | :--- | :--- |
| `get_jira_story` | Read-Only | Extracts Jira Story summary, description, parsed Acceptance Criteria, components, labels, and already linked tests. |
| `generate_test_plan` | Phase 1 (Safe) | Synthesizes positive, negative, and boundary test cases with preconditions and steps. Generates a Traceability Matrix and caches the plan with a `plan_id`. |
| `review_test_plan` | Phase 1 (Safe) | Inspects a generated test plan and all test case specifications before publishing. |
| `publish_test_plan` | Phase 2 (Write) | Creates Jira `Test` issues, batches steps to Zephyr ZAPI, and links them back to the Story. Supports `dry_run=True` simulation. |
| `create_single_test_case` | On-Demand | Directly creates and links a bespoke custom test case with Zephyr steps. |
| `verify_story_traceability` | Audit | Audits a Jira Story's test coverage, verifying existing linked tests and step counts. |

---

## ⚙️ Configuration & Environment Variables

Copy `.env.example` to `.env` or provide environment variables:

```bash
# Jira Server / Data Center Configuration
JIRA_BASE_URL=https://jira.yourcompany.com

# Authentication: Personal Access Token (PAT) recommended for Jira Server/DC 8.14+
JIRA_PAT=your_personal_access_token_here

# Alternatively, Basic Auth (if PAT is disabled):
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password

# Jira & Zephyr Issue Settings
JIRA_TEST_ISSUE_TYPE=Test
JIRA_TEST_LINK_TYPE=Tests
JIRA_DEFAULT_PROJECT_KEY=PROJ

# Zephyr Squad ZAPI
ZEPHYR_ZAPI_BASE_PATH=/rest/zapi/latest
ZEPHYR_REQUEST_TIMEOUT=30.0
ZEPHYR_MAX_RETRIES=3

# Local storage cache for test plans
STORAGE_DIR=~/.zephyr_jira_mcp
```

---

## 🚀 Installation & Client Setup

### 1. Local Setup

```bash
cd /Users/apple/Projects/zephyr-jira-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure in Claude Desktop or Antigravity MCP Settings

Add the following to your `claude_desktop_config.json` or `antigravity.mcp.json`:

```json
{
  "mcpServers": {
    "zephyr-jira": {
      "command": "/Users/apple/Projects/zephyr-jira-mcp/.venv/bin/python",
      "args": [
        "-m",
        "zephyr_jira_mcp.server"
      ],
      "env": {
        "JIRA_BASE_URL": "https://jira.yourcompany.com",
        "JIRA_PAT": "your-jira-personal-access-token",
        "JIRA_TEST_ISSUE_TYPE": "Test",
        "JIRA_TEST_LINK_TYPE": "Tests"
      }
    }
  }
}
```

---

## 🧪 Testing & Verification

The suite includes comprehensive unit, integration, and contract tests with mock transports:

```bash
cd /Users/apple/Projects/zephyr-jira-mcp
.venv/bin/pytest -v
```

---

## 📖 Example Workflow

1. **Analyze Story & Generate Plan**:
   ```json
   // Call tool: generate_test_plan
   {
     "story_key": "PAY-101",
     "max_cases": 6,
     "include_negative": true,
     "include_boundary": true
   }
   ```
   *Returns `plan_id`: `PLAN-PAY-101-a1b2c3d4` with preview of all synthesized test cases and traceability matrix.*

2. **Review Plan**:
   ```json
   // Call tool: review_test_plan
   {
     "plan_id": "PLAN-PAY-101-a1b2c3d4"
   }
   ```

3. **Publish to Jira & Zephyr**:
   ```json
   // Call tool: publish_test_plan
   {
     "plan_id": "PLAN-PAY-101-a1b2c3d4",
     "dry_run": false
   }
   ```
   *Result:*
   - Creates Jira issues `PAY-201`, `PAY-202`, etc. with `issuetype: Test`
   - Posts step details (`step`, `data`, `result`) via ZAPI `/rest/zapi/latest/teststep/{issueId}`
   - Issues bidirectional links (`PAY-101` <-> `PAY-201`) with relationship `Tests`.
