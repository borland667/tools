FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROUTER_HOST=0.0.0.0 \
    ROUTER_PORT=8010

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY omlx_auto_router.py .

EXPOSE 8010

CMD ["python", "omlx_auto_router.py"]
