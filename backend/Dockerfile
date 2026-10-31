FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY trialmatch ./trialmatch
RUN pip install --no-cache-dir .
ENV CRITERIA_CACHE_PATH=/data/criteria.sqlite3
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "trialmatch.api:app", "--host", "0.0.0.0", "--port", "8000"]
