FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY bbrun ./bbrun

RUN uv pip install --system --no-cache .

ENTRYPOINT ["bb-run"]
CMD ["--help"]
