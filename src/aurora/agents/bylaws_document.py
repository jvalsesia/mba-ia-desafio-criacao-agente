import logging
import re
from dataclasses import dataclass
from pathlib import Path

from aurora.config import DATA_DIR

BYLAWS_FILE = "regulamento.md"
LEAD_CHARS = 60

logger = logging.getLogger(__name__)

_CHAPTER = re.compile(r"^## Capítulo [IVXLCDM]+: (?P<title>.*\S)\s*$")
_ARTICLE = re.compile(r"^\*\*Art\. (?P<number>\d+)(?:º|\.)\*\*\s*(?P<rest>.*)$")


@dataclass(frozen=True)
class Article:
    number: int
    lead: str


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    articles: tuple[Article, ...]
    text: str


@dataclass(frozen=True)
class Bylaws:
    chapters: tuple[Chapter, ...]

    def chapter(self, number: int) -> Chapter | None:
        if 1 <= number <= len(self.chapters):
            return self.chapters[number - 1]
        return None


def _lead(rest: str) -> str:
    rest = rest.strip()
    if len(rest) <= LEAD_CHARS:
        return rest
    cut = rest[:LEAD_CHARS].rsplit(" ", 1)[0].rstrip(",;: ")
    return f"{cut}…"


def _build_chapter(number: int, title: str, lines: list[str]) -> Chapter:
    articles = []
    for line in lines:
        match = _ARTICLE.match(line)
        if match:
            articles.append(Article(int(match["number"]), _lead(match["rest"])))
    return Chapter(number, title, tuple(articles), "\n".join(lines).strip("\n"))


def parse_bylaws(text: str) -> Bylaws | None:
    chapters: list[Chapter] = []
    title: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = _CHAPTER.match(line)
        if match:
            if title is not None:
                chapters.append(_build_chapter(len(chapters) + 1, title, lines))
            title, lines = match["title"].strip(), [line]
        elif title is not None:
            lines.append(line)
    if title is None:
        return None
    chapters.append(_build_chapter(len(chapters) + 1, title, lines))
    return Bylaws(tuple(chapters))


def load_bylaws(data_dir: Path = DATA_DIR) -> Bylaws | None:
    path = Path(data_dir) / BYLAWS_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        logger.error("bylaws unreadable: %s at %s", type(error).__name__, path)
        return None
    bylaws = parse_bylaws(text)
    if bylaws is None:
        logger.error("bylaws without chapters: %s", path)
    return bylaws


def render_index(bylaws: Bylaws) -> str:
    lines = []
    for chapter in bylaws.chapters:
        head = f"{chapter.number}. {chapter.title}"
        if chapter.articles:
            first, last = chapter.articles[0].number, chapter.articles[-1].number
            head += f" (Art. {first} a {last})"
        lines.append(head)
        lines.extend(f"   - Art. {a.number}: {a.lead}" for a in chapter.articles)
    return "\n".join(lines)
