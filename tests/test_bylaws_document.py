import logging
from pathlib import Path

import pytest

from aurora.agents.bylaws_document import (
    BYLAWS_FILE,
    LEAD_CHARS,
    load_bylaws,
    parse_bylaws,
    render_index,
)
from aurora.config import DATA_DIR

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def loaded():
    return load_bylaws(DATA_DIR)


@pytest.fixture(scope="module")
def source_lines():
    return (DATA_DIR / BYLAWS_FILE).read_text(encoding="utf-8").splitlines()


def test_load_reads_fourteen_chapters(loaded):
    assert [c.number for c in loaded.chapters] == list(range(1, 15))


def test_chapter_titles_come_from_headings(loaded):
    assert loaded.chapter(1).title == "Disposições gerais"
    assert loaded.chapter(4).title == "Piscina"
    assert loaded.chapter(14).title == "Disposições finais"


def test_chapter_text_starts_at_its_heading(loaded):
    text = loaded.chapter(4).text
    assert text.startswith("## Capítulo IV: Piscina")
    assert "## Capítulo V" not in text


def test_chapter_text_has_the_sunday_rule(loaded):
    line = "II. Aos domingos e feriados, a piscina funciona das 9h às 20h."
    assert line in loaded.chapter(4).text.splitlines()


def test_chapters_cover_the_whole_file(loaded, source_lines):
    first = next(i for i, line in enumerate(source_lines) if line.startswith("## Capítulo"))
    covered = [line for c in loaded.chapters for line in c.text.splitlines()]
    expected = [line for line in source_lines[first:]]
    assert [line for line in covered if line.strip()] == [line for line in expected if line.strip()]
    for line in expected:
        if line.strip():
            assert sum(c.text.splitlines().count(line) for c in loaded.chapters) >= 1


def test_articles_are_numbered_from_the_file(loaded):
    numbers = [a.number for c in loaded.chapters for a in c.articles]
    assert numbers == list(range(1, 97))
    pool = loaded.chapter(4).articles
    assert (pool[0].number, pool[-1].number) == (21, 28)


def test_article_markers_with_ordinal_and_dot(loaded):
    numbers = {a.number for c in loaded.chapters for a in c.articles}
    assert {1, 10} <= numbers
    text = "## Capítulo I: A\n\n**Art. 1º** Um.\n\n**Art. 10.** Dez.\n"
    parsed = parse_bylaws(text)
    assert [(a.number, a.lead) for a in parsed.chapter(1).articles] == [(1, "Um."), (10, "Dez.")]


def test_lead_is_cut_at_a_word(loaded):
    article = next(a for c in loaded.chapters for a in c.articles if a.number == 21)
    assert article.lead.endswith("…")
    body = article.lead[:-1]
    assert len(body) <= LEAD_CHARS
    full = next(
        line
        for line in (DATA_DIR / BYLAWS_FILE).read_text(encoding="utf-8").splitlines()
        if line.startswith("**Art. 21.**")
    )
    rest = full.split("**", 2)[2].strip()
    assert rest.startswith(body)
    assert rest[len(body)] == " "


def test_short_lead_is_kept_whole(loaded):
    article = next(a for c in loaded.chapters for a in c.articles if a.number == 22)
    assert article.lead == "A piscina observa os seguintes períodos de uso:"


def test_index_lists_chapters_and_articles(loaded):
    lines = render_index(loaded).splitlines()
    assert sum(1 for line in lines if not line.startswith("   - ")) == 14
    assert sum(1 for line in lines if line.startswith("   - Art. ")) == 96
    assert "4. Piscina (Art. 21 a 28)" in lines
    assert "14. Disposições finais (Art. 93 a 96)" in lines


def test_index_has_no_long_line_of_the_file(loaded, source_lines):
    index = render_index(loaded)
    for line in source_lines:
        if len(line) >= 40:
            assert line not in index


def test_chapter_lookup_out_of_range(loaded):
    assert loaded.chapter(0) is None
    assert loaded.chapter(15) is None


def test_chapter_without_articles_has_no_parentheses():
    parsed = parse_bylaws("## Capítulo I: Vazio\n\nsem artigos\n")
    assert render_index(parsed) == "1. Vazio"


def test_parse_without_chapters_returns_nothing():
    assert parse_bylaws("# Título\n\nnada de capítulos aqui\n") is None


def test_load_missing_file_returns_nothing(caplog):
    with caplog.at_level(logging.ERROR):
        assert load_bylaws(FIXTURES / "bylaws_missing") is None
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_load_unreadable_file_returns_nothing():
    assert load_bylaws(FIXTURES / "bylaws_unreadable") is None


def test_load_file_without_chapters_returns_nothing():
    assert load_bylaws(FIXTURES / "bylaws_no_chapters") is None


def test_load_failure_log_has_no_file_content(caplog):
    folder = FIXTURES / "bylaws_no_chapters"
    content = (folder / BYLAWS_FILE).read_text(encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        load_bylaws(folder)
        load_bylaws(FIXTURES / "bylaws_missing")
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert str(folder) in logged
    assert "FileNotFoundError" in logged
    assert "Texto solto" not in logged and content.strip() not in logged


def test_load_does_not_change_the_file():
    path = DATA_DIR / BYLAWS_FILE
    before = path.read_bytes()
    load_bylaws(DATA_DIR)
    assert path.read_bytes() == before
