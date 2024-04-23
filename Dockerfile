FROM python:3.12-slim

WORKDIR /app
COPY src/ /app/src
COPY pyproject.toml /app
COPY README.md /app
COPY LICENSE /app

RUN apt update && apt install -y build-essential libpython3-dev
RUN pip install .[all]

CMD ["python", "-m", "gptbot"]