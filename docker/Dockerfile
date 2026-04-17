# syntax=docker/dockerfile:1
FROM python:3.13.7

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN pip install -U git+https://github.com/opengeos/anymap
RUN pip install -U gdown
RUN pip install -U localtileserver

EXPOSE 7000

COPY app /app

COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]

