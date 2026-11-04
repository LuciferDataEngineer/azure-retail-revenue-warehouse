FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
COPY azure /app/azure
RUN pip install --no-cache-dir . -r azure/requirements.txt
RUN useradd --uid 10001 --create-home retail
USER 10001
ENTRYPOINT ["python", "azure/producer.py"]
# Deployment is a separate approved action. No credentials embedded in the image.
CMD ["--upload"]
