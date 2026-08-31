# syntax=docker/dockerfile:1
# Harness do dataset dourado (tests/eval). So stdlib — nenhum pip install.
#   testes das checagens:  docker run --rm <img> -m unittest discover
#   eval contra um agente:  docker run --rm -e AGENT_URL=<url> <img>
FROM python:3.11-slim
WORKDIR /eval
COPY . .
ENTRYPOINT ["python"]
CMD ["run.py"]
