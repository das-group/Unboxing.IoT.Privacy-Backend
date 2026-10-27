FROM python:3.14-alpine

WORKDIR /workdir

COPY requirements.txt requirements.txt

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

COPY ./app.py .

COPY ./src/* ./src/

COPY ./templates ./templates

EXPOSE 4040

ENTRYPOINT [ "granian" ]
CMD ["--host", "0.0.0.0", "--port", "4040","--interface", "asgi", "app:app"]