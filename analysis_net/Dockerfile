FROM python:3.14-alpine

WORKDIR /workdir

RUN apk add --no-cache tshark

COPY requirements.txt requirements.txt

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

COPY ./app.py ./app.py

COPY ./src ./src

EXPOSE 8080

VOLUME [ "/workdir/data" ]

ENTRYPOINT [ "granian" ]
CMD ["--host", "0.0.0.0", "--port", "8080","--interface","asgi", "app:app"]