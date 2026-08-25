# build 2026.08.1
FROM ghcr.io/home-assistant/base-python:latest

RUN apk add --no-cache ffmpeg

RUN pip3 install --no-cache-dir aiohttp aiomqtt tzdata

COPY app/ /app/
COPY icon.png /app/icon.png

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
