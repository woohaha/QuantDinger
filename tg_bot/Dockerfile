FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/

WORKDIR /

# Build context is repo root; this Dockerfile sits in tg_bot/ but the
# docker-compose `context:` is project root so `COPY tg_bot/...` works.
COPY tg_bot/requirements.txt /tg_bot/requirements.txt
RUN pip install -r /tg_bot/requirements.txt

RUN groupadd -r app && useradd -r -g app -d /tg_bot -s /sbin/nologin app && \
    mkdir -p /data && chown -R app:app /tg_bot /data

COPY --chown=app:app tg_bot/ /tg_bot/

USER app
VOLUME ["/data"]

CMD ["python", "-u", "-m", "tg_bot.bot"]
