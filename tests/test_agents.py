import re

from google.adk.tools.agent_tool import AgentTool
from sqlalchemy.ext.asyncio import create_async_engine

from aurora.agents.bylaws import MSG_NOT_FOUND as BYLAWS_NOT_FOUND
from aurora.agents.bylaws import build_bylaws_agent, shorten
from aurora.agents.runtime import build_app
from aurora.config import DATA_DIR

MAIN = "gemini-teste-principal"
SPECIALISTS = "gemini-teste-especialistas"


TOOL_NAMES = [
    "reservar_area",
    "cancelar_reserva",
    "listar_minhas_reservas",
    "consultar_disponibilidade",
    "listar_areas",
]


def _app():
    # An engine that never connects: these tests only inspect the agent tree.
    engine = create_async_engine("postgresql+asyncpg://aurora:aurora@localhost:5999/aurora_test")
    return build_app(main_model=MAIN, specialists_model=SPECIALISTS, engine=engine)


def _reservations_tools():
    return _app().root_agent.find_sub_agent("reservas").tools


def _visitors_tools():
    return _app().root_agent.find_sub_agent("visitantes").tools


def _properties(tool):
    schema = tool._get_declaration().parameters_json_schema
    return schema["properties"] if schema else {}


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


def test_reservations_agent_has_the_five_tools():
    assert [t.name for t in _reservations_tools()] == TOOL_NAMES


def test_tool_declarations_match_the_contract():
    tools = {t.name: t for t in _reservations_tools()}
    assert list(_properties(tools["reservar_area"])) == ["area", "data"]
    assert list(_properties(tools["cancelar_reserva"])) == ["area", "data", "codigo"]
    assert list(_properties(tools["consultar_disponibilidade"])) == ["area", "data"]
    assert _properties(tools["listar_minhas_reservas"]) == {}
    assert _properties(tools["listar_areas"]) == {}


def test_no_tool_declares_an_apartment_parameter():
    for tool in _reservations_tools():
        for name in _properties(tool):
            assert name != "apartamento"
            assert "apart" not in name and "apto" not in name
            assert "context" not in name


def test_cancel_parameters_are_optional():
    tool = next(t for t in _reservations_tools() if t.name == "cancelar_reserva")
    schema = tool._get_declaration().parameters_json_schema
    assert not schema.get("required")
    assert all(p["type"] == "string" for p in schema["properties"].values())


def test_reservations_instruction_has_no_resident_data():
    instruction = _app().root_agent.find_sub_agent("reservas").instruction
    assert "RSV-" not in instruction
    assert not re.search(r"\b\d{3}\b", instruction)
    assert not re.search(r"\d+[.,]\d{2}", instruction)
    for name in ("Marina", "Paulo", "Duarte", "Nogueira"):
        assert name not in instruction


def test_reservations_instruction_names_areas_and_date_format():
    instruction = _app().root_agent.find_sub_agent("reservas").instruction
    for area in ("salao-de-festas", "churrasqueira", "quadra"):
        assert area in instruction
    assert "AAAA-MM-DD" in instruction
    assert "português" in instruction


def test_reservations_agent_keeps_transfer_locks():
    agent = _app().root_agent.find_sub_agent("reservas")
    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True


def _bylaws_agent():
    return _app().root_agent.tools[0].agent


def test_bylaws_specialist_has_the_read_tool():
    assert [t.name for t in _bylaws_agent().tools] == ["ler_capitulo"]


def test_bylaws_tool_keeps_the_request_declaration():
    tool = _app().root_agent.tools[0]
    assert tool.name == "regulamento"
    assert list(_properties(tool)) == ["request"]


def test_bylaws_instruction_has_the_index_and_rules():
    instruction = _bylaws_agent().instruction
    assert "4. Piscina (Art. 21 a 28)" in instruction
    assert "ler_capitulo" in instruction
    assert BYLAWS_NOT_FOUND in instruction
    assert "português" in instruction


def test_bylaws_instruction_has_no_resident_data():
    instruction = _bylaws_agent().instruction
    assert "RSV-" not in instruction
    for name in ("Marina", "Paulo", "Duarte", "Nogueira", "Joana", "Ribeiro"):
        assert name not in instruction


def test_unavailable_bylaws_agent_has_no_tools():
    agent = build_bylaws_agent(SPECIALISTS, None)
    assert agent.tools == []
    assert "Piscina" not in agent.instruction
    assert agent.before_agent_callback is not None


def test_assistant_instruction_asks_for_a_complete_question():
    instruction = _app().root_agent.instruction
    assert "dúvida completa" in instruction


def test_shorten_keeps_short_text():
    text = "a" * 800
    assert shorten(text) == text


def test_shorten_cuts_at_a_sentence_end():
    text = "Primeira frase completa. " * 60
    result = shorten(text)
    assert len(result) <= 800
    assert result.endswith(".")
    assert result == text[: len(result)].strip()


def test_shorten_does_not_cut_after_art():
    prefix = "Primeira regra. "
    text = prefix + "y" * (800 - len(prefix) - len(" Art.")) + " Art." + " 22 " + "z " * 200
    assert text[:800].endswith("Art.") and text[800] == " "
    assert shorten(text) == "Primeira regra."


def test_shorten_without_sentence_end():
    result = shorten("palavra " * 300)
    assert len(result) <= 800
    assert result.endswith("…")


def test_visitors_agent_has_the_two_tools():
    assert [t.name for t in _visitors_tools()] == ["autorizar_visitante", "listar_meus_visitantes"]


def test_visitor_tool_declarations_match_the_contract():
    tools = {t.name: t for t in _visitors_tools()}
    assert list(_properties(tools["autorizar_visitante"])) == ["nome", "data"]
    schema = tools["autorizar_visitante"]._get_declaration().parameters_json_schema
    assert schema["required"] == ["nome", "data"]
    assert _properties(tools["listar_meus_visitantes"]) == {}


def test_no_visitor_tool_declares_apartment_or_confirmation():
    for tool in _visitors_tools():
        for name in _properties(tool):
            assert name != "apartamento"
            assert "apart" not in name and "apto" not in name
            assert "confirm" not in name
            assert "context" not in name


def test_visitors_instruction_has_no_resident_data():
    instruction = _app().root_agent.find_sub_agent("visitantes").instruction
    assert not re.search(r"\b\d{3}\b", instruction)
    for name in ("Marina", "Paulo", "Duarte", "Nogueira", "Joana", "Ribeiro"):
        assert name not in instruction


def test_visitors_instruction_names_tools_and_date_format():
    instruction = _app().root_agent.find_sub_agent("visitantes").instruction
    assert "autorizar_visitante" in instruction and "listar_meus_visitantes" in instruction
    assert "AAAA-MM-DD" in instruction
    assert "português" in instruction


def test_visitors_agent_keeps_transfer_locks():
    agent = _app().root_agent.find_sub_agent("visitantes")
    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True


def test_factories_return_new_tool_lists():
    first, second = _bylaws_agent().tools, _bylaws_agent().tools
    assert first is not second
    assert all(a is not b for a, b in zip(first, second, strict=True))
    first, second = _reservations_tools(), _reservations_tools()
    assert first is not second
    assert all(a is not b for a, b in zip(first, second, strict=True))
    first, second = _visitors_tools(), _visitors_tools()
    assert first is not second
    assert all(a is not b for a, b in zip(first, second, strict=True))


def test_factories_return_new_objects():
    first, second = _app(), _app()
    assert first.root_agent is not second.root_agent
    assert first.root_agent.sub_agents[0] is not second.root_agent.sub_agents[0]
