"""Checks the delivery README against the code, `.env.example` and `pyproject.toml`."""

import re
import subprocess
import tomllib
from pathlib import Path

from google.adk.tools.agent_tool import AgentTool
from sqlalchemy.ext.asyncio import create_async_engine

from aurora.agents.assistant import ASSISTANT_NAME, build_assistant
from aurora.agents.bylaws import BYLAWS_NAME
from aurora.agents.reservations import RESERVATIONS_NAME
from aurora.agents.visitors import VISITORS_NAME
from aurora.config import PROJECT_ROOT

README = PROJECT_ROOT / "README.md"
STATEMENT = PROJECT_ROOT / "tests" / "fixtures" / "challenge_statement" / "README.md"
ROOT_STATEMENT_COPY = PROJECT_ROOT / "README-ORIGINAL.md"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

SECTIONS = ["Arquitetura", "Garantias", "Como rodar"]
AGENTS = [ASSISTANT_NAME, RESERVATIONS_NAME, VISITORS_NAME, BYLAWS_NAME]
AGENT_LABELS = ["**Responsabilidade:**", "**Como é acionado:**", "**Por quê:**"]
REASON_LABEL = "**Por que não depende do modelo:**"
ANCHORS = {
    1: "request_confirmation",
    2: "APARTMENT_KEY",
    3: "DatabaseSessionService",
    4: "AgentTool",
    5: "status = 'active'",
}
LONG_LINE = 40

_FENCE = "```"
_HEADING = re.compile(r"^(#{1,6}) (.+?)\s*$")
_REFERENCE = re.compile(r"^\*\*Arquivo:\*\* `([^`]+)`\s*$")
_ENV_NAME = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`")
_UV_RUN = re.compile(r"\buv run ([A-Za-z0-9_.-]+)")


def _text() -> str:
    return README.read_text(encoding="utf-8")


def _headings(text: str) -> list[tuple[int, str]]:
    """(level, title) for every heading outside fenced code blocks."""
    found = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(_FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def sections(text: str, level: int) -> dict[str, str]:
    """Title -> body for headings of `level`; a heading of that level or above ends a body."""
    result: dict[str, str] = {}
    title: str | None = None
    body: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(_FENCE):
            in_fence = not in_fence
        match = None if in_fence or line.lstrip().startswith(_FENCE) else _HEADING.match(line)
        if match and len(match.group(1)) <= level:
            if title is not None:
                result[title] = "\n".join(body)
            title = match.group(2) if len(match.group(1)) == level else None
            body = []
            continue
        if title is not None:
            body.append(line)
    if title is not None:
        result[title] = "\n".join(body)
    return result


def references(body: str) -> list[tuple[str, str]]:
    """(path, block) for each `**Arquivo:**` line followed by the next fenced block."""
    lines = body.splitlines()
    found = []
    index = 0
    while index < len(lines):
        match = _REFERENCE.match(lines[index].strip())
        index += 1
        if not match:
            continue
        while index < len(lines) and not lines[index].lstrip().startswith(_FENCE):
            if _REFERENCE.match(lines[index].strip()):
                break
            index += 1
        if index >= len(lines) or not lines[index].lstrip().startswith(_FENCE):
            found.append((match.group(1), ""))
            continue
        start = index + 1
        end = start
        while end < len(lines) and not lines[end].lstrip().startswith(_FENCE):
            end += 1
        found.append((match.group(1), "\n".join(lines[start:end])))
        index = end + 1
    return found


def block_in_file(block: str, path: Path) -> bool:
    """The non-blank block lines, stripped, appear as consecutive stripped lines of the file."""
    wanted = [line.strip() for line in block.splitlines() if line.strip()]
    if not wanted:
        return False
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    size = len(wanted)
    return any(lines[i : i + size] == wanted for i in range(len(lines) - size + 1))


def env_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0].strip())
    return names


def _section(name: str) -> str:
    return sections(_text(), 2)[name]


def _agents() -> dict[str, str]:
    return sections(_section("Arquitetura"), 3)


def _guarantees() -> dict[str, str]:
    return sections(_section("Garantias"), 3)


def _label(body: str, label: str) -> str:
    for line in body.splitlines():
        if line.strip().startswith(label):
            return line.strip()[len(label) :].strip()
    return ""


def _code_lines(body: str) -> list[str]:
    lines = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith(_FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(line.strip())
    return lines


def _scripts() -> dict[str, str]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]


def _all_references() -> list[tuple[str, str]]:
    return [ref for body in _guarantees().values() for ref in references(body)]


# Structure


def test_title_and_three_sections():
    text = _text()
    headings = _headings(text)
    first = next(line for line in text.splitlines() if line.strip())
    assert first.startswith("# ")
    assert [title for level, title in headings if level == 1] == [first[2:].strip()]
    assert [title for level, title in headings if level == 2] == SECTIONS


def test_no_challenge_statement_text():
    text = _text()
    long_lines = [
        line.strip()
        for line in STATEMENT.read_text(encoding="utf-8").splitlines()
        if len(line.strip()) >= LONG_LINE
    ]
    assert long_lines
    leaked = [line for line in long_lines if line in text]
    assert leaked == []
    assert "## Fluxo do avaliador" not in text
    assert "## Critérios de aceite" not in text


def test_fixture_is_original_statement():
    statement = STATEMENT.read_text(encoding="utf-8")
    assert statement.startswith("# Regra é regra")
    assert "## Fluxo do avaliador" in statement


def test_root_statement_copy_is_untouched():
    assert ROOT_STATEMENT_COPY.read_bytes() == STATEMENT.read_bytes()


# Architecture


def test_architecture_lists_the_four_agents():
    assert list(_agents()) == AGENTS


def test_each_agent_has_three_labels():
    for name, body in _agents().items():
        for label in AGENT_LABELS:
            assert _label(body, label), f"{name}: {label} ausente ou vazio"


def test_agent_invocation_matches_code():
    # An engine that never connects: the test only inspects the agent tree.
    engine = create_async_engine("postgresql+asyncpg://aurora:aurora@localhost:5999/aurora_test")
    root = build_assistant(
        model="gemini-teste", specialists_model="gemini-teste", engine=engine, bylaws=None
    )
    agents = _agents()
    how = {name: _label(body, "**Como é acionado:**") for name, body in agents.items()}

    assert root.name == ASSISTANT_NAME
    assert "Runner" in how[ASSISTANT_NAME]

    assert [agent.name for agent in root.sub_agents] == [RESERVATIONS_NAME, VISITORS_NAME]
    for name in (RESERVATIONS_NAME, VISITORS_NAME):
        assert "subagente" in how[name]

    agent_tools = [tool for tool in root.tools if isinstance(tool, AgentTool)]
    assert [tool.agent.name for tool in agent_tools] == [BYLAWS_NAME]
    assert "agent-tool" in how[BYLAWS_NAME]


def test_specialists_mention_resume():
    agents = _agents()
    assert "retom" in agents[RESERVATIONS_NAME]
    assert "retom" in agents[VISITORS_NAME]


# Guarantees


def test_five_guarantees_in_order():
    titles = list(_guarantees())
    assert len(titles) == 5
    for number, title in enumerate(titles, start=1):
        assert re.match(rf"Garantia {number}\b", title), title


def test_each_guarantee_has_reference_and_reason():
    for title, body in _guarantees().items():
        refs = references(body)
        assert refs, f"{title}: nenhuma referência"
        assert all(block.strip() for _path, block in refs), f"{title}: bloco vazio"
        assert _label(body, REASON_LABEL), f"{title}: {REASON_LABEL} ausente ou vazio"


def test_referenced_files_exist():
    for path, _block in _all_references():
        assert (PROJECT_ROOT / path).is_file(), path
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )
        assert tracked.returncode == 0, f"{path} não é rastreado pelo git"


def test_excerpts_are_verbatim():
    for path, block in _all_references():
        first = next((line.strip() for line in block.splitlines() if line.strip()), "")
        assert block_in_file(block, PROJECT_ROOT / path), f"{path}: {first}"


def test_guarantee_anchors():
    for number, body in enumerate(_guarantees().values(), start=1):
        blocks = [block for _path, block in references(body)]
        assert any(ANCHORS[number] in block for block in blocks), f"Garantia {number}"


# How to run


def test_env_variables_match_example():
    section = _section("Como rodar")
    expected = env_names(ENV_EXAMPLE)
    cited = set(_ENV_NAME.findall(section))
    assert expected
    assert expected <= cited
    suspicious = {
        name for name in cited if name.endswith(("_KEY", "_URL")) or name.startswith("GEMINI_")
    }
    assert suspicious <= expected
    assert "cp .env.example .env" in section


def test_commands_in_order():
    lines = _code_lines(_section("Como rodar"))

    def position(predicate) -> int:
        return next(i for i, line in enumerate(lines) if predicate(line))

    order = [
        position(lambda line: line == "uv sync"),
        position(lambda line: line.startswith("docker compose up")),
        position(lambda line: line == "uv run aurora-restore"),
        position(lambda line: line == "uv run aurora-api"),
    ]
    assert order == sorted(order)


def test_uv_run_commands_are_registered():
    names = _UV_RUN.findall(_section("Como rodar"))
    assert names
    scripts = _scripts()
    assert [name for name in names if name not in scripts] == []


def test_selfcheck_documented_after_api():
    section = _section("Como rodar")
    assert section.index("uv run aurora-selfcheck") > section.index("uv run aurora-api")
    assert "aurora-selfcheck" in _scripts()
    selfcheck = next(
        body for title, body in sections(section, 3).items() if title.startswith("Self-check")
    )
    assert "uv run aurora-selfcheck" in selfcheck
    assert "cota" in selfcheck
    assert "8000" in selfcheck


def test_initial_data_check_documented():
    section = _section("Como rodar")
    assert "/apartamentos/101/reservas" in section
    assert "RSV-1377" in section


def test_prerequisites_documented():
    section = _section("Como rodar")
    for word in ("Python 3.12", "uv", "Docker", "Compose"):
        assert word in section
