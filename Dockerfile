FROM python:3.12-alpine
RUN apk add --no-cache docker-cli
WORKDIR /app
COPY app /app
EXPOSE 8484
CMD ["python", "/app/server.py"]
