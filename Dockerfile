FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GALLERY_DB=/tmp/gallery.db
COPY pyproject.toml ./
COPY gallery ./gallery
RUN pip install --no-cache-dir .
COPY web ./web
COPY replay_cache ./replay_cache
EXPOSE 8000
CMD ["uvicorn", "gallery.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
