FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app
RUN pip install poetry==2.2.1
COPY pyproject.toml poetry.lock ./
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev --no-root --no-interaction --no-ansi; \
    else \
      poetry install --only main --no-root --no-interaction --no-ansi; \
    fi

RUN useradd --create-home --uid 10001 cinema \
    && mkdir /app/beat-data && chown cinema:cinema /app/beat-data
COPY --chown=cinema:cinema src ./src
COPY --chown=cinema:cinema alembic.ini ./
USER cinema
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
