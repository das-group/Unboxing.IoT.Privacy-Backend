FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /workdir



COPY requirements.txt requirements.txt

RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium

COPY ./app.py ./app.py

COPY ./src ./src

EXPOSE 8080

COPY start.sh start.sh
RUN chmod +x start.sh
EXPOSE 8000
CMD ["bash", "start.sh"]

#ENTRYPOINT [ "granian" ]
#CMD ["--host", "0.0.0.0", "--port", "8080","--interface","asgi", "app:app"]
