# The Docker CLI is copied at build time; no package installation during startup.
FROM docker:27-cli AS dockercli
FROM python:3.12-alpine
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
RUN docker --version
WORKDIR /app
COPY app/ /app/
EXPOSE 8484
ENV PYTHONUNBUFFERED=1 \
    DOCKER_HOST=unix:///run/mrstore/docker.sock
CMD ["python", "/app/server.py"]
