from aurora.config import DATA_DIR
from aurora.selfcheck.checks import (
    events_text,
    foreign_bylaws_lines,
    function_call_names,
    has_isolated_302,
    leaked_bylaws_line,
    mentions_closing_time,
    pending_matching,
    seed_codes,
)


def test_isolated_302_detected():
    assert has_isolated_302("apartamento 302")
    assert has_isolated_302("o apartamento 302.")
    assert has_isolated_302("(302)")


def test_302_inside_numbers_and_codes_ignored():
    for text in ("13025", "1302", "RSV-3021", "302-B", "1.302", "3,302"):
        assert not has_isolated_302(text), text


def test_foreign_bylaws_lines_exclude_chapter_iv():
    lines = foreign_bylaws_lines(DATA_DIR / "regulamento.md")
    chapters = {chapter for chapter, _ in lines}
    assert "IV" not in chapters
    assert "VIII" in chapters
    assert all(len(line) >= 40 for _, line in lines)
    assert leaked_bylaws_line("nada aqui", lines) is None
    chapter, line = lines[0]
    assert leaked_bylaws_line(f"x\n{line}\ny", lines) == (chapter, line)


def test_events_text_reads_nested_strings():
    line = 'Linha com "aspas" e\nquebra'
    events = [{"content": {"parts": [{"functionResponse": {"response": {"result": line}}}]}}]
    assert line in events_text(events)


def test_pending_matching_ignores_keys_case_and_accents():
    items = [
        {"id": "a", "detalhes": {"local": "Salão de Festas", "dia": "2030-04-20"}},
    ]
    assert pending_matching(items, "salao-de-festas", "2030-04-20") == items[0]


def test_pending_matching_requires_all_values():
    items = [{"id": "a", "detalhes": {"dia": "2030-04-20"}}]
    assert pending_matching(items, "salao-de-festas", "2030-04-20") is None


def test_mentions_closing_time_variants():
    for text in ("20h", "às 20 h", "até 20:00", "20 horas"):
        assert mentions_closing_time(text), text
    for text in ("200h", "2030"):
        assert not mentions_closing_time(text), text


def test_function_call_names():
    events = [
        {"content": {"parts": [{"functionCall": {"name": "transfer_to_agent"}}]}},
        {"content": {"parts": [{"text": "oi"}]}},
        {"content": {"parts": [{"functionCall": {"name": "ler_regulamento"}}]}},
    ]
    assert function_call_names(events) == ["transfer_to_agent", "ler_regulamento"]


def test_seed_codes_reads_dados():
    assert seed_codes(DATA_DIR / "reservas.json") == {"RSV-1377", "RSV-4821", "RSV-2950"}
