FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8050
EXPOSE 8050
CMD gunicorn app.app:server --bind 0.0.0.0:$PORT --workers 2 --preload
