import json
import re
from dataclasses import dataclass
from typing import TypeAlias

from package.ui.visualization import PreparedVisualization, prepare_inline_visualization


_OPENING_RE = re.compile(r"(?m)^```visualization[ \t]*\r?\n")
_CLOSING_RE = re.compile(r"(?m)^```[ \t]*(?:\r?\n|$)")
_OPENING_TOKEN = "```visualization"
MAX_INLINE_VISUALIZATIONS = 5


@dataclass(frozen=True, slots=True)
class MarkdownBlock:
    content: str


@dataclass(frozen=True, slots=True)
class VisualizationBlock:
    visualization: PreparedVisualization


@dataclass(frozen=True, slots=True)
class PendingVisualizationBlock:
    pass


@dataclass(frozen=True, slots=True)
class InvalidVisualizationBlock:
    reason: str


RichContentBlock: TypeAlias = (
    MarkdownBlock
    | VisualizationBlock
    | PendingVisualizationBlock
    | InvalidVisualizationBlock
)


def parse_rich_content(
    content: str,
    *,
    allow_partial: bool = False,
    max_visualizations: int = MAX_INLINE_VISUALIZATIONS,
) -> tuple[RichContentBlock, ...]:
    if not content:
        return ()

    blocks: list[RichContentBlock] = []
    position = 0
    visualization_count = 0

    while position < len(content):
        opening = _OPENING_RE.search(content, position)
        if opening is None:
            tail = content[position:]
            partial_index = _partial_opening_index(tail) if allow_partial else None
            if partial_index is None:
                _append_markdown(blocks, tail)
            else:
                _append_markdown(blocks, tail[:partial_index])
                blocks.append(PendingVisualizationBlock())
            break

        _append_markdown(blocks, content[position : opening.start()])
        closing = _CLOSING_RE.search(content, opening.end())
        if closing is None:
            if allow_partial:
                blocks.append(PendingVisualizationBlock())
            break

        raw_payload = content[opening.end() : closing.start()].strip()
        if visualization_count >= max_visualizations:
            blocks.append(
                InvalidVisualizationBlock(
                    reason=f"A resposta excedeu o limite de {max_visualizations} visualizações."
                )
            )
        else:
            block = _parse_visualization_block(raw_payload)
            blocks.append(block)
            if isinstance(block, VisualizationBlock):
                visualization_count += 1

        position = closing.end()

    return tuple(blocks)


def strip_visualization_blocks(content: str) -> str:
    """Remove visualization directives without parsing or validating their payloads.

    This path is intentionally lexical so streaming UI updates can expose the
    narrative text without repeatedly deserializing completed visualization JSON
    on every model delta. Complete directives and an in-flight directive at the
    end of the stream are both hidden until the final rich-content render.
    """
    if not content:
        return ""

    markdown: list[str] = []
    position = 0

    while position < len(content):
        opening = _OPENING_RE.search(content, position)
        if opening is None:
            tail = content[position:]
            partial_index = _partial_opening_index(tail)
            if partial_index is not None:
                tail = tail[:partial_index]
            if tail:
                markdown.append(tail)
            break

        prefix = content[position : opening.start()]
        if prefix:
            markdown.append(prefix)

        closing = _CLOSING_RE.search(content, opening.end())
        if closing is None:
            break
        position = closing.end()

    return "\n".join(part.strip("\n") for part in markdown if part.strip()).strip()


def _parse_visualization_block(raw_payload: str) -> RichContentBlock:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return InvalidVisualizationBlock(reason="JSON de visualização inválido.")

    if not isinstance(payload, dict):
        return InvalidVisualizationBlock(reason="A visualização deve ser um objeto JSON.")

    try:
        visualization = prepare_inline_visualization(payload)
    except ValueError as exc:
        return InvalidVisualizationBlock(reason=str(exc))

    return VisualizationBlock(visualization=visualization)


def _append_markdown(blocks: list[RichContentBlock], content: str) -> None:
    if content:
        blocks.append(MarkdownBlock(content=content))


def _partial_opening_index(content: str) -> int | None:
    line_start = content.rfind("\n") + 1
    candidate = content[line_start:].rstrip("\r")
    if not candidate:
        return None
    if _OPENING_TOKEN.startswith(candidate):
        return line_start
    if candidate.startswith(_OPENING_TOKEN) and "\n" not in candidate:
        return line_start
    return None
