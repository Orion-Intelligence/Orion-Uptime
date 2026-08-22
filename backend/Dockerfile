FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --no-install-recommends --yes python3 python3-venv iputils-ping ca-certificates libcap2-bin \
    && setcap -r /usr/bin/ping \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt \
    && pip uninstall -y pip

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY --chown=app:app main.py ./
COPY --chown=app:app configs ./configs
COPY --chown=app:app orion ./orion
COPY --chown=app:app routes ./routes
COPY --chown=app:app seeder ./seeder
COPY --chown=app:app build ./build

USER app

EXPOSE 8000

CMD ["hypercorn", "main:app", "--bind", "0.0.0.0:8000", "--workers", "1"]
