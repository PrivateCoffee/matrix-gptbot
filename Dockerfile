FROM python:3.13-slim

WORKDIR /app
COPY src/ /app/src
COPY pyproject.toml /app
COPY README.md /app
COPY LICENSE /app

RUN apt update
RUN apt install -y build-essential libpython3-dev ffmpeg
RUN pip install .[all]
RUN pip install 'future==1.0.0'

CMD ["python", "-m", "gptbot"]