import re

from google.adk.tools.agent_tool import AgentTool

from aurora.agents.runtime import build_app
from aurora.config import DATA_DIR

MAIN = "gemini-teste-principal"
SPECIALISTS = "gemini-teste-especialistas"


def _app():
    return build_app(main_model=MAIN, specialists_model=SPECIALISTS)


def _bylaws_lines():
    return (DATA_DIR / "regulamento.md").read_text(encoding="utf-8").splitlines()


def test_root_agent_is_the_assistant():
    app = _app()
    assert app.root_agent.name == "assistente"
    assert app.name == "aurora"


def test_assistant_has_exactly_three_specialists():
    root = _app().root_agent
    assert [a.name for a in root.sub_agents] == ["reservas", "visitantes"]
    agent_tools = [t for t in root.tools if isinstance(t, AgentTool)]
    assert [t.agent.name for t in agent_tools] == ["regulamento"]
    assert len(root.find_sub_agent("reservas").sub_agents) == 0
    assert 1 + len(root.sub_agents) + len(agent_tools) == 4


def test_assistant_has_no_data_tool():
    root = _app().root_agent
    assert len(root.tools) == 1
    assert isinstance(root.tools[0], AgentTool)
    declaration = root.tools[0]._get_declaration()
    assert list(declaration.parameters_json_schema["properties"]) == ["request"]


def test_sub_agents_cannot_transfer():
    for agent in _app().root_agent.sub_agents:
        assert agent.disallow_transfer_to_parent is True
        assert agent.disallow_transfer_to_peers is True


def test_models_follow_the_parameters():
    root = _app().root_agent
    assert root.model == MAIN
    assert [a.model for a in root.sub_agents] == [SPECIALISTS, SPECIALISTS]
    assert root.tools[0].agent.model == SPECIALISTS


def test_assistant_instruction_has_no_bylaws_text():
    instruction = _app().root_agent.instruction
    for line in _bylaws_lines():
        if len(line) >= 40:
            assert line not in instruction
        if line.startswith("## "):
            assert line[3:] not in instruction
    assert "Art." not in instruction
    assert len(instruction) < 4000
    assert not re.search(r"\b(RSV-\d+|\d{3})\b", instruction)


def test_assistant_instruction_names_the_specialists():
    instruction = _app().root_agent.instruction
    for name in ("reservas", "visitantes", "regulamento"):
        assert name in instruction
    assert "português" in instruction


def test_specialist_shells_have_no_tools():
    root = _app().root_agent
    for agent in [*root.sub_agents, root.tools[0].agent]:
        assert agent.tools == []


def test_factories_return_new_objects():
    first, second = _app(), _app()
    assert first.root_agent is not second.root_agent
    assert first.root_agent.sub_agents[0] is not second.root_agent.sub_agents[0]
