"""Local checks without an API key or a paid request."""

import unittest
import os
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf as fitz
from PIL import Image

from config import get_settings
from markdown_renderer import render_markdown
from pdf_utils import PdfError, page_count, render_page
from schemas import RecognitionResult, validate_result
from vision_service import RecognitionError, prepare_image, recognize_page


SAMPLE = {
    "document": {"filename": "guessed.png", "page_number": 9, "language": "ru"},
    "elements": [
        {"id": "element_001", "order": 1, "type": "heading", "text": "Квадратные уравнения", "latex": None, "description": None},
        {"id": "element_002", "order": 2, "type": "definition", "text": "Квадратное уравнение имеет вид:", "latex": "ax^2+bx+c=0", "description": None},
        {"id": "element_003", "order": 3, "type": "problem", "text": "Решите уравнение", "latex": "x^2-5x+6=0", "description": None},
        {"id": "element_004", "order": 4, "type": "answer", "text": "Ответ", "latex": "x=2, x=3", "description": None},
    ],
}


class LocalChecks(unittest.TestCase):
    def test_openai_configuration(self):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "provider-key", "OPENAI_MODEL": "openai/gpt-4.1-mini",
            "OPENAI_BASE_URL": "https://api.proxyapi.ru/v1",
        }):
            settings = get_settings()
            self.assertEqual(settings.api_key, "provider-key")
            self.assertEqual(settings.model, "openai/gpt-4.1-mini")
            self.assertEqual(settings.base_url, "https://api.proxyapi.ru/v1")

    def test_image_preparation(self):
        source = BytesIO()
        Image.new("RGBA", (80, 50), (0, 0, 0, 0)).save(source, format="PNG")
        prepared = prepare_image(source.getvalue())
        with Image.open(BytesIO(prepared)) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (80, 50))
        with self.assertRaises(RecognitionError):
            prepare_image(b"broken")

    def test_pdf_one_page_rendering_and_error(self):
        document = fitz.open()
        document.new_page().insert_text((40, 40), "page one")
        document.new_page().insert_text((40, 40), "page two")
        data = document.tobytes()
        document.close()
        self.assertEqual(page_count(data), 2)
        with Image.open(BytesIO(render_page(data, 2))) as image:
            self.assertGreater(image.width, 1000)
        with self.assertRaises(PdfError):
            page_count(b"broken pdf")

    def test_schema_and_markdown(self):
        result = validate_result(RecognitionResult.model_validate(SAMPLE))
        markdown = render_markdown(result)
        self.assertIn("# Квадратные уравнения", markdown)
        self.assertIn("$$\nax^2+bx+c=0\n$$", markdown)
        self.assertIn("$x=2, x=3$", markdown)
        self.assertNotIn("**Решение**", markdown)
        self.assertEqual(result.model_dump(mode="json")["elements"][1]["type"], "definition")
        bad = result.model_copy(deep=True)
        bad.elements[1].order = 1
        with self.assertRaises(ValueError):
            validate_result(bad)

    def test_one_structured_api_call_with_selected_image(self):
        
        parsed = RecognitionResult.model_validate(SAMPLE)
        response = SimpleNamespace(output_parsed=parsed, usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30))
        with patch("vision_service.OpenAI") as client_class:
            client_class.return_value.responses.parse.return_value = response
            result, usage = recognize_page(b"png", filename="real.png", page_number=2, api_key="test", model="gpt-4.1-mini")
            client_class.assert_called_once_with(api_key="test", base_url="https://api.openai.com/v1")
            client_class.return_value.responses.parse.assert_called_once()
            arguments = client_class.return_value.responses.parse.call_args.kwargs
            self.assertIs(arguments["text_format"], RecognitionResult)
            self.assertTrue(arguments["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,"))
            self.assertEqual(result.document.filename, "real.png")
            self.assertEqual(result.document.page_number, 2)
            self.assertEqual(usage.total_tokens, 30)

    def test_custom_base_url_uses_same_structured_responses_call(self):
        response = SimpleNamespace(
            output_parsed=RecognitionResult.model_validate(SAMPLE),
            usage=SimpleNamespace(input_tokens=11, output_tokens=22, total_tokens=33),
        )
        with patch("vision_service.OpenAI") as client_class:
            client_class.return_value.responses.parse.return_value = response
            result, usage = recognize_page(
                b"png", filename="page.png", page_number=1,
                api_key="provider-test", model="openai/gpt-4.1-mini", base_url="https://api.proxyapi.ru/v1",
            )
            client_class.assert_called_once_with(api_key="provider-test", base_url="https://api.proxyapi.ru/v1")
            client_class.return_value.responses.parse.assert_called_once()
            client_class.return_value.chat.completions.create.assert_not_called()
            request = client_class.return_value.responses.parse.call_args.kwargs
            self.assertEqual(request["model"], "openai/gpt-4.1-mini")
            self.assertIs(request["text_format"], RecognitionResult)
            self.assertTrue(request["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,"))
            self.assertEqual(result.document.filename, "page.png")
            self.assertEqual(usage.total_tokens, 33)

    def test_missing_api_key(self):
        with self.assertRaisesRegex(RecognitionError, "OPENAI_API_KEY"):
            recognize_page(b"png", filename="a.png", page_number=1, api_key="", model="m")


if __name__ == "__main__":
    unittest.main()
