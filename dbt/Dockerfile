FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MATCHPOINT_DBT_JIT=off

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/dbt

COPY requirements.txt /tmp/dbt-requirements.txt

RUN python -m pip install --no-cache-dir \
    -r /tmp/dbt-requirements.txt \
    && python -m pip check

ENTRYPOINT ["python", "/workspace/dbt/run_dbt.py"]
