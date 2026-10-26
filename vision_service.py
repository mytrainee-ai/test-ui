"""One vision request per recognition click, using the selected API provider."""

import base64
import json
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


def _openai_response(client: OpenAI, model: str, image_url: str):
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
    return response.output_parsed, response.usage


def _compatible_response(client: OpenAI, model: str, image_url: str):
    """Use the common vision Chat Completions shape; validate JSON locally."""
    schema = json.dumps(RecognitionResult.model_json_schema(), ensure_ascii=False)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": INSTRUCTION + "\nВерни только JSON-объект без Markdown и пояснений. JSON-схема: " + schema,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Распознай содержимое этой страницы учебника."},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ],
            },
        ],
    )
    if not response.choices or not response.choices[0].message.content:
        raise RecognitionError("Провайдер не вернул JSON-ответ.")
    return json.loads(response.choices[0].message.content), response.usage


def recognize_page(
    image_png: bytes, *, filename: str, page_number: int, provider: str,
    api_key: str, model: str, base_url: str = ""
) -> tuple[RecognitionResult, Usage]:
    if provider not in {"openai", "openai_compatible"}:
        raise RecognitionError("Неизвестный LLM_PROVIDER. Используйте openai или openai_compatible.")
    if not api_key:
        raise RecognitionError("Не задан LLM_API_KEY. Создайте .env по образцу .env.example.")
    if not model:
        raise RecognitionError("Не задан LLM_MODEL в .env.")
    if provider == "openai_compatible" and not base_url:
        raise RecognitionError("Для openai_compatible задайте LLM_BASE_URL в .env.")
    image_url = "data:image/png;base64," + base64.b64encode(image_png).decode("ascii")
    try:
        client = OpenAI(api_key=api_key, **({"base_url": base_url} if provider == "openai_compatible" else {}))
        if provider == "openai":
            parsed, usage = _openai_response(client, model, image_url)
        else:
            parsed, usage = _compatible_response(client, model, image_url)
        result = validate_result(RecognitionResult.model_validate(parsed))
        # Source metadata comes from the local selection, not a model guess.
        result.document.filename = filename
        result.document.page_number = page_number
        if usage is None:
            token_usage = Usage(None, None, None)
        elif provider == "openai_compatible":
            token_usage = Usage(usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)
        else:
            token_usage = Usage(usage.input_tokens, usage.output_tokens, usage.total_tokens)
        return result, token_usage
    except RecognitionError:
        raise
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise RecognitionError("Ошибка авторизации API. Проверьте LLM_API_KEY и доступ к модели.") from exc
    except NotFoundError as exc:
        raise RecognitionError("Модель недоступна. Проверьте LLM_MODEL, LLM_BASE_URL и доступ вашего ключа.") from exc
    except RateLimitError as exc:
        raise RecognitionError("Превышен лимит API провайдера. Проверьте квоту и повторите запрос позже.") from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise RecognitionError("Сетевой запрос к API провайдера не выполнен. Проверьте соединение и LLM_BASE_URL.") from exc
    except BadRequestError as exc:
        raise RecognitionError("API отклонил запрос. Проверьте LLM_MODEL, адрес API и поддержку изображений.") from exc
    except (ValidationError, ValueError) as exc:
        raise RecognitionError("Структурированный ответ модели не соответствует JSON-схеме или порядку элементов.") from exc
    except APIStatusError as exc:
        raise RecognitionError("API провайдера вернул ошибку. Проверьте состояние сервиса и повторите запрос позже.") from exc
