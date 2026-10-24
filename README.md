# Zephyr Squad & Jira Server/DC Test Management MCP Server

An enterprise-grade, end-to-end **Model Context Protocol (MCP)** server built by Senior QA Test Architects. It automates the parsing of Jira User Stories, synthesizes structured Zephyr Squad test cases (happy path, negative, boundary value, and authorization), and establishes bidirectional traceability links between Jira Stories and Zephyr Test issues.

---

## 📂 Repository File Structure & Architecture Map

```text
zephyr_mcp/
├── .env.example                     # Environment template for Jira Server/DC & Zephyr credentials
├── .gitignore                       # Standard Python ignore rules (venv, pycache, egg-info)
├── pyproject.toml                   # Project metadata, build configuration & dependencies
├── README.md                        # Primary documentation & agent scraping manual
├── llms.txt                         # Machine-readable overview for LLMs & autonomous agents
├── src/
│   └── zephyr_jira_mcp/
│       ├── __init__.py              # Package declaration & version metadata (1.0.0)
│       ├── config.py                # Pydantic Settings, environment loading, and PAT/Basic auth
│       ├── models.py                # Domain schemas: TestCaseSpec, TestPlanSpec, TestStepSpec, PublishResult
│       ├── jira_client.py           # Async HTTP client for Jira REST API v2 (issues, links, search)
│       ├── zephyr_client.py         # Async HTTP client for Zephyr Squad ZAPI (test steps, batches, retries)
│       ├── story_analyzer.py        # Acceptance Criteria parser (plain text, Jira wiki, ADF nodes)
│       ├── test_synthesizer.py      # QA test synthesis engine (positive, negative, boundary, idempotency hashes)
│       ├── plan_manager.py          # Plan cache, approval lifecycle, and two-phase publishing orchestrator
│       └── server.py                # Official MCPServer implementation (tools, resources, and prompts)
└── tests/
    ├── __init__.py                  # Test package marker
    ├── conftest.py                  # Pytest fixtures and mock Jira/Zephyr data
    ├── test_story_analyzer.py       # Unit tests for story parsing, ADF traversal & BDD detection
    ├── test_test_synthesizer.py     # Unit tests for test case generation, coverage, and idempotency
    ├── test_jira_client.py          # Mock transport tests for Jira issue creation & issue linking
    ├── test_zephyr_client.py        # Mock transport tests for ZAPI test steps & retry backoff
    ├── test_plan_manager.py         # Tests for plan storage, review, dry-run & live execution
    └── test_server.py               # Integration tests for all MCP server tools and resources
```

---

## 🔄 End-to-End Data Flow

```text
+-----------------------------------------------------------------------------------+
|                                MCP CLIENT (Claude / IDE)                          |
+-----------------------------------------------------------------------------------+
       |                                                         |
       | 1. get_jira_story("PAY-101")                            | 3. publish_test_plan(plan_id)
       v                                                         v
+-----------------------------+                           +-----------------------------+
|    Phase 1: Safe Read-Only  |                           |  Phase 2: Controlled Write  |
|                             |                           |                             |
|  - StoryAnalyzer:           |                           |  - JiraClient:              |
|    Parses AC (Text/ADF/BDD) |                           |    POST /rest/api/2/issue   |
|  - TestSynthesizer:         |                           |    (Create 'Test' issue)    |
|    Positive / Negative /    |                           |  - ZephyrClient:            |
|    Boundary Scenarios       |                           |    POST /teststep/{issueId} |
|  - PlanManager:             |                           |    (Batch add test steps)   |
|    Computes SHA256 hashes   |                           |  - JiraClient:              |
|    Builds Traceability      |                           |    POST /rest/api/2/issueLink
|    Returns Plan ID          |                           |    (Link Test to Story)     |
+-----------------------------+                           +-----------------------------+
```

---

## 🛠️ MCP Tool Reference & Agent Contracts

Every tool exposes strict Pydantic-validated contracts:

### 1. `get_jira_story`
- **Description**: Extracts Jira Story summary, description, parsed Acceptance Criteria, components, labels, and already linked tests.
- **Arguments**:
  - `story_key` (`string`, required): Jira issue key (e.g. `'PROJ-101'`).
- **Returns**: JSON `JiraStoryContext` object.

### 2. `generate_test_plan` *(Phase 1: Safe Read-Only)*
- **Description**: Synthesizes QA test cases, boundary conditions, and a full Traceability Matrix from a Jira Story. Does **not** modify Jira or Zephyr.
- **Arguments**:
  - `story_key` (`string`, required): Jira issue key.
  - `max_cases` (`integer`, default: `8`): Maximum number of test cases to synthesize.
  - `include_negative` (`boolean`, default: `true`): Include validation/negative tests.
  - `include_boundary` (`boolean`, default: `true`): Include boundary value analysis tests.
  - `include_security` (`boolean`, default: `false`): Include authorization tests.
- **Returns**: JSON summary containing `plan_id`, `traceability_matrix`, `unmapped_criteria`, and test case previews.

### 3. `review_test_plan`
- **Description**: Retrieves an existing test plan from the storage cache by its ID.
- **Arguments**:
  - `plan_id` (`string`, required): Plan ID returned by `generate_test_plan`.
- **Returns**: Complete JSON `TestPlanSpec`.

### 4. `publish_test_plan` *(Phase 2: Controlled Execution)*
- **Description**: Publishes the approved test plan into Jira Server/DC as native `Test` issues, adds steps via Zephyr ZAPI, and links them back to the Story.
- **Arguments**:
  - `plan_id` (`string`, required): Plan ID to execute.
  - `dry_run` (`boolean`, default: `false`): When `true`, simulates execution without network writes.
- **Returns**: JSON `PublishResult` with created test keys, issue IDs, and status.

### 5. `create_single_test_case`
- **Description**: Directly creates and links an ad-hoc custom Zephyr test case to a Jira Story.
- **Arguments**:
  - `story_key` (`string`, required): Target Jira Story key.
  - `title` (`string`, required): Descriptive test case title.
  - `summary` (`string`, required): Jira Test issue summary.
  - `description` (`string`, required): Test objective.
  - `preconditions` (`string`, required): Environment prerequisites.
  - `steps` (`list[object]`, required): List of step dicts: `{"step": str, "data": str, "result": str}`.
  - `priority` (`string`, default: `"Medium"`): `"Highest"`, `"High"`, `"Medium"`, `"Low"`, `"Lowest"`.
  - `dry_run` (`boolean`, default: `false`): Simulate write actions.
- **Returns**: JSON `CreatedTestRecord`.

### 6. `verify_story_traceability`
- **Description**: Audits the test coverage of a Jira Story, inspecting linked tests and step counts.
- **Arguments**:
  - `story_key` (`string`, required): Jira issue key.
- **Returns**: JSON audit report with `acceptance_criteria_count`, `linked_tests_count`, and `coverage_adequate`.

---

## 🌐 API Landscape & Endpoint Matrix

### Jira Server & Data Center REST API v2
| Operation | HTTP Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| Get Issue | `GET` | `/rest/api/2/issue/{issueIdOrKey}` | Retrieve story fields, description, and issue links |
| Create Test Issue | `POST` | `/rest/api/2/issue` | Create Jira issue with `issuetype: {"name": "Test"}` |
| Link Test to Story | `POST` | `/rest/api/2/issueLink` | Establish bidirectional link (`Tests` / `Tested by`) |
| JQL Search | `GET` | `/rest/api/2/search` | Search existing tests by project or story key |

### Zephyr Squad ZAPI Endpoints
| Operation | HTTP Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| Get Test Steps | `GET` | `/rest/zapi/latest/teststep/{issueId}` | Fetch existing step definitions |
| Add Test Step | `POST` | `/rest/zapi/latest/teststep/{issueId}` | Post step action, test data, and expected result |
| Update Test Step | `PUT` | `/rest/zapi/latest/teststep/{issueId}/{stepId}` | Modify an existing step definition |
| Delete Test Step | `DELETE` | `/rest/zapi/latest/teststep/{issueId}/{stepId}` | Remove an obsolete test step |

---

## ⚙️ Configuration

Set the following environment variables (or create a `.env` file from `.env.example`):

```bash
# Jira Server / Data Center URL
JIRA_BASE_URL=https://jira.yourcompany.com

# Personal Access Token (PAT) for Jira Server/DC 8.14+
JIRA_PAT=your_personal_access_token_here

# Alternatively, Basic Auth (if PAT is not supported):
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password

# Issue Types & Links
JIRA_TEST_ISSUE_TYPE=Test
JIRA_TEST_LINK_TYPE=Tests
JIRA_DEFAULT_PROJECT_KEY=PROJ

# Zephyr Squad ZAPI
ZEPHYR_ZAPI_BASE_PATH=/rest/zapi/latest
ZEPHYR_REQUEST_TIMEOUT=30.0
ZEPHYR_MAX_RETRIES=3

# Local storage cache for generated test plans
STORAGE_DIR=~/.zephyr_jira_mcp
```

---

## 🚀 Client Setup Guide

### 1. Installation

```bash
git clone https://github.com/pam2728tester/zephyr_mcp.git
cd zephyr_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure in Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "zephyr-jira": {
      "command": "/absolute/path/to/zephyr_mcp/.venv/bin/python",
      "args": [
        "-m",
        "zephyr_jira_mcp.server"
      ],
      "env": {
        "JIRA_BASE_URL": "https://jira.yourcompany.com",
        "JIRA_PAT": "your_jira_pat",
        "JIRA_TEST_ISSUE_TYPE": "Test",
        "JIRA_TEST_LINK_TYPE": "Tests"
      }
    }
  }
}
```

---

## 🧪 Automated Test Suite

Run the full pytest suite:

```bash
pytest -v
```

All 21 unit and integration tests execute with zero remote side effects using mocked HTTP transports.
