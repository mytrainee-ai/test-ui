"""One structured vision request per recognition click."""

import base64
from dataclasses import dataclass
from io import BytesIO

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from schemas import RecognitionResult, validate_result


MAX_FILE_BYTES = 15 * 1024 * 1024

INSTRUCTION = """Ты анализируешь изображение одной страницы учебника математики.
Максимально точно извлеки только видимое содержимое. Определи заголовки, абзацы,
определения, теоремы, правила, формулы, примеры, задачи, решения, ответы, таблицы
и рисунки. Сохрани предполагаемый порядок чтения и исходный язык страницы.
Запиши поле latex в LaTeX без разделителей $ или $$. Если формула стоит внутри
предложения, сохрани её в text с разделителями $...$.
Не решай задачи самостоятельно,
не добавляй отсутствующую информацию и не исправляй математический текст.
Если часть содержимого неразборчива, напиши «[неразборчиво]» вместо догадки.
Для таблицы по возможности запиши Markdown-таблицу в поле text. Для рисунка
сохрани видимую подпись в text и краткую интерпретацию в description.
Каждому элементу дай уникальный id вида element_001 и последовательный order
начиная с 1. Поля, которые не применимы, заполни null.
Возвращай данные строго по заданной схеме."""


class RecognitionError(ValueError):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


def prepare_image(data: bytes) -> bytes:
    """Verify the source image and encode it without resizing or sharpening."""
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise RecognitionError("Поддерживаются только изображения JPG, JPEG и PNG.")
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except RecognitionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RecognitionError("Не удалось прочитать изображение. Проверьте файл JPG или PNG.") from exc


def recognize_page(
    image_png: bytes, *, filename: str, page_number: int,
    api_key: str, model: str, base_url: str = ""
) -> tuple[RecognitionResult, Usage]:
    if not api_key:
        raise RecognitionError("Не задан OPENAI_API_KEY. Создайте .env по образцу .env.example.")
    if not model:
        raise RecognitionError("Не задан OPENAI_MODEL в .env.")
    image_url = "data:image/png;base64," + base64.b64encode(image_png).decode("ascii")
    try:
        client = OpenAI(api_key=api_key, base_url=base_url or "https://api.openai.com/v1")
        response = client.responses.parse(
            model=model,
            instructions=INSTRUCTION,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Распознай содержимое этой страницы учебника."},
                        {"type": "input_image", "image_url": image_url, "detail": "high"},
                    ],
                }
            ],
            text_format=RecognitionResult,
        )
        if response.output_parsed is None:
            raise RecognitionError("API не вернул структурированный JSON-ответ.")
        result = validate_result(RecognitionResult.model_validate(response.output_parsed))
        # Source metadata comes from the local selection, not a model guess.
        result.document.filename = filename
        result.document.page_number = page_number
        usage = response.usage
        token_usage = Usage(
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
            usage.total_tokens if usage else None,
        )
        return result, token_usage
    except RecognitionError:
        raise
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise RecognitionError("Ошибка авторизации API. Проверьте OPENAI_API_KEY и доступ к модели.") from exc
    except NotFoundError as exc:
        raise RecognitionError("Модель недоступна. Проверьте OPENAI_MODEL, OPENAI_BASE_URL и доступ вашего ключа.") from exc
    except RateLimitError as exc:
        raise RecognitionError("Превышен лимит API провайдера. Проверьте квоту и повторите запрос позже.") from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise RecognitionError("Сетевой запрос к API не выполнен. Проверьте соединение и OPENAI_BASE_URL.") from exc
    except BadRequestError as exc:
        raise RecognitionError("API отклонил запрос. Проверьте OPENAI_MODEL, адрес API и поддержку изображений и структурированного вывода.") from exc
    except (ValidationError, ValueError) as exc:
        raise RecognitionError("Структурированный ответ модели не соответствует JSON-схеме или порядку элементов.") from exc
    except APIStatusError as exc:
        raise RecognitionError("API провайдера вернул ошибку. Проверьте состояние сервиса и повторите запрос позже.") from exc
