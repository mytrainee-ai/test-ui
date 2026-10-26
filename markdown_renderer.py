"""Deterministic Markdown built only from the validated JSON result."""

from pathlib import Path

from schemas import Element, ElementType, RecognitionResult


LABELS = {
    ElementType.definition: "Определение",
    ElementType.theorem: "Теорема",
    ElementType.rule: "Правило",
    ElementType.example: "Пример",
    ElementType.problem: "Задача",
    ElementType.solution: "Решение",
    ElementType.answer: "Ответ",
}


def _render_element(item: Element) -> str:
    text = (item.text or "").strip()
    latex = (item.latex or "").strip().strip("$").strip()
    description = (item.description or "").strip()

    if item.type == ElementType.heading:
        return f"# {text or '[Неразборчивый заголовок]'}"
    if item.type == ElementType.formula:
        return f"$$\n{latex}\n$$" if latex else (text or "[Неразборчивая формула]")
    if item.type == ElementType.table:
        return text or "[Неразборчивая таблица]"
    if item.type == ElementType.figure:
        return "\n\n".join(part for part in [f"**Рисунок.** {text}" if text else "**Рисунок**", description] if part)

    parts = []
    if item.type in LABELS:
        parts.append(f"**{LABELS[item.type]}**")
    parts.append(text or "[Неразборчивый текст]")
    if latex:
        parts.append(f"${latex}$" if item.type == ElementType.answer else f"$$\n{latex}\n$$")
    if description:
        parts.append(description)
    return "\n\n".join(parts)


def render_markdown(result: RecognitionResult) -> str:
    return "\n\n".join(_render_element(item) for item in result.elements) + "\n"


def save_outputs(result: RecognitionResult, directory: Path) -> tuple[Path, Path]:
    """Write the same JSON and Markdown shown in the UI to the project folder."""
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / "math_page.md"
    json_path = directory / "math_page.json"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return markdown_path, json_path
