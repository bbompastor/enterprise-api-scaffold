# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/false --create-home app

COPY api/ ./api/

USER 1000

EXPOSE 8080
ENV PORT=8080

CMD ["python", "-m", "api.main"]
