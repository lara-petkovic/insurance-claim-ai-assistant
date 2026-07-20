import pytest
from pydantic import ValidationError

from core.models.agent import AgentMessage, AgentResponse, AgentStatus, AgentType, MessageType


def test_agent_enums_serialize_as_api_strings():
    response = AgentResponse(
        agent_name="TestAgent",
        agent_type=AgentType.VALIDATOR,
        status=AgentStatus.WARNING,
        messages=[AgentMessage(from_agent="TestAgent", message_type=MessageType.FEEDBACK, content="Review")],
    )

    serialized = response.model_dump(mode="json")
    assert serialized["agent_type"] == "validator"
    assert serialized["status"] == "warning"
    assert serialized["messages"][0]["message_type"] == "feedback"


def test_agent_enums_reject_unknown_values():
    with pytest.raises(ValidationError):
        AgentResponse(agent_name="TestAgent", agent_type="unknown")
