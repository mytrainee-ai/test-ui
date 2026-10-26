"""The single structured result shared by the API, UI, and Markdown renderer."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, ValidationError


class ElementType(str, Enum):
    heading = "heading"
    paragraph = "paragraph"
    definition = "definition"
    theorem = "theorem"
    rule = "rule"
    formula = "formula"
    example = "example"
    problem = "problem"
    solution = "solution"
    answer = "answer"
    table = "table"
    figure = "figure"
    other = "other"


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    page_number: int
    language: str


class Element(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    order: int
    type: ElementType
    text: str | None
    latex: str | None
    description: str | None


class RecognitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: Document
    elements: list[Element]


def validate_result(result: RecognitionResult) -> RecognitionResult:
    """Check rules that JSON Schema cannot express simply."""
    if not result.elements:
        raise ValueError("Модель не вернула ни одного элемента страницы.")
    ids = [item.id for item in result.elements]
    orders = [item.order for item in result.elements]
    if len(ids) != len(set(ids)):
        raise ValueError("В ответе модели повторяются идентификаторы элементов.")
    if orders != list(range(1, len(orders) + 1)):
        raise ValueError("Порядковые номера элементов должны идти от 1 без пропусков.")
    return result
