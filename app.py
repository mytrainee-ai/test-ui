"""Russian Streamlit interface for inspecting one-page vision recognition."""

import hashlib
from pathlib import Path

import streamlit as st

from config import get_settings
from markdown_renderer import render_markdown
from pdf_utils import PdfError, page_count, render_page
from vision_service import MAX_FILE_BYTES, RecognitionError, prepare_image, recognize_page


st.set_page_config(page_title="Math Page Vision Lab", layout="wide")
st.title("Math Page Vision Lab")
st.caption("Экспериментальное распознавание страниц учебников математики с помощью Vision LLM")

with st.expander("Как работает распознавание"):
    st.write(
        "Выбранная страница преобразуется в изображение. Один запрос передаёт его "
        "в OpenAI Vision LLM вместе с инструкцией и JSON-схемой. Ответ проверяется "
        "через Pydantic; Markdown строится локально из того же JSON. PDF-текст "
        "напрямую не извлекается. Модель может ошибаться в символах и порядке чтения."
    )

settings = get_settings()
uploaded = st.file_uploader("Загрузите страницу (JPG, JPEG, PNG или PDF; до 15 МБ)", type=["jpg", "jpeg", "png", "pdf"])
st.write(f"Модель: `{settings.model}`")

image_png = None
source_key = None
page_number = 1
error = None

if uploaded is not None:
    data = uploaded.getvalue()
    if len(data) > MAX_FILE_BYTES:
        error = "Файл слишком большой. Максимальный размер — 15 МБ."
    else:
        extension = Path(uploaded.name).suffix.lower()
        try:
            if extension == ".pdf":
                count = page_count(data)
                page_number = st.number_input("Номер страницы PDF", min_value=1, max_value=count, value=1, step=1)
                image_png = render_page(data, int(page_number))
            elif extension in {".jpg", ".jpeg", ".png"}:
                image_png = prepare_image(data)
            else:
                error = "Поддерживаются только JPG, JPEG, PNG и PDF."
        except (PdfError, RecognitionError) as exc:
            error = str(exc)
    if image_png is not None:
        source_key = hashlib.sha256(data).hexdigest() + f":{page_number}:{uploaded.name}"

if st.session_state.get("source_key") != source_key:
    st.session_state.source_key = source_key
    st.session_state.result = None
    st.session_state.usage = None
    st.session_state.recognition_error = None

if error:
    st.error(error)

clicked = st.button("Распознать страницу", disabled=image_png is None)
if clicked and image_png is not None:
    st.session_state.result = None
    st.session_state.recognition_error = None
    with st.spinner("Распознаём выбранную страницу…"):
        try:
            result, usage = recognize_page(
                image_png,
                filename=uploaded.name,
                page_number=int(page_number),
                api_key=settings.api_key,
                model=settings.model,
            )
            st.session_state.result = result
            st.session_state.usage = usage
        except RecognitionError as exc:
            st.session_state.recognition_error = str(exc)

left, right = st.columns(2, gap="large")
with left:
    st.subheader("Исходная страница")
    if image_png is None:
        st.info("Загрузите файл, чтобы увидеть страницу.")
    else:
        st.image(image_png, use_container_width=True)

with right:
    st.subheader("Результат")
    if st.session_state.get("recognition_error"):
        st.error(st.session_state.recognition_error)
    result = st.session_state.get("result")
    if result is None:
        st.info("Результат появится после нажатия «Распознать страницу».")
    else:
        markdown = render_markdown(result)
        json_text = result.model_dump_json(indent=2)
        preview, raw_markdown, raw_json = st.tabs(["Просмотр", "Markdown", "JSON"])
        with preview:
            st.markdown(markdown)
        with raw_markdown:
            st.code(markdown, language="markdown")
        with raw_json:
            st.code(json_text, language="json")
        st.download_button("Скачать Markdown", markdown.encode("utf-8"), "math_page.md", "text/markdown", key="download_md")
        st.download_button("Скачать JSON", json_text.encode("utf-8"), "math_page.json", "application/json", key="download_json")
        usage = st.session_state.get("usage")
        if usage and usage.total_tokens is not None:
            st.caption(f"Токены: вход {usage.input_tokens}, выход {usage.output_tokens}, всего {usage.total_tokens}")
