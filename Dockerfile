FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# app/static/avatars needs to exist (owned by authuser) *before* the volume
# mount defined in compose.yaml overlays it -- otherwise Docker initializes
# the named volume from a root-owned mountpoint and uploads fail with EACCES.
RUN mkdir -p app/static/avatars && useradd -m authuser && chown -R authuser /app
USER authuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]