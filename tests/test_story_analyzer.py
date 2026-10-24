"""Tests for StoryAnalyzer: Jira Story parsing and Acceptance Criteria extraction."""

from zephyr_jira_mcp.story_analyzer import StoryAnalyzer


def test_parse_acceptance_criteria_from_text():
    text = """
    We need user registration.
    
    Acceptance Criteria:
    1. User enters valid email and password (min 8 chars) -> Account created.
    2. Given an existing email, When user signs up, Then display duplicate error.
    3. Password must contain at least 1 uppercase and 1 number.
    
    Technical Notes:
    - Use bcrypt for password hashing.
    """
    criteria = StoryAnalyzer.parse_acceptance_criteria(text)
    assert len(criteria) == 3
    assert criteria[0].id == "AC-1"
    assert "User enters valid email" in criteria[0].text
    assert criteria[1].id == "AC-2"
    assert criteria[1].is_bdd is True
    assert "duplicate error" in criteria[1].text
    assert criteria[2].id == "AC-3"
    assert criteria[2].is_bdd is False


def test_extract_from_adf_structure():
    adf_dict = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Feature description overview."}
                ]
            },
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [
                    {"type": "text", "text": "Acceptance Criteria:"}
                ]
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Valid JWT allows API call."}]
                            }
                        ]
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Expired JWT returns 401."}]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    extracted_text = StoryAnalyzer.extract_text_from_jira_description(adf_dict)
    assert "Feature description overview" in extracted_text
    assert "Valid JWT allows API call" in extracted_text

    criteria = StoryAnalyzer.parse_acceptance_criteria(extracted_text)
    assert len(criteria) >= 2


def test_from_jira_issue_dict(sample_jira_story_dict):
    ctx = StoryAnalyzer.from_jira_issue_dict(sample_jira_story_dict)
    assert ctx.key == "PAY-101"
    assert ctx.id == "10550"
    assert ctx.summary == "Implement Instant UPI Refund Processing"
    assert ctx.components == ["Payments", "RefundGateway"]
    assert "upi" in ctx.labels
    assert len(ctx.acceptance_criteria) == 4
    assert "PAY-50" in ctx.linked_tests
