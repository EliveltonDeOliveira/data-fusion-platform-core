# tests/eval

Dataset dourado por projeto — perguntas de referencia com as propriedades que a
resposta do agente precisa ter, para checagem deterministica de regressao.

- `cases/<projeto>.json` — as perguntas e o que se espera de cada uma.
- `checks.py` — as checagens (funcoes puras): a tool certa foi chamada, a regiao
  resolveu, nao ha numero sem lastro na tool, o texto nao recomenda manejo.
- `run.py` — envia cada pergunta a um agente no ar e aplica as checagens.
- `test_checks.py` — testes das checagens, offline.

O dataset de `satelite_agro` cobre as tres perguntas-ancora da fatia inicial,
uma consulta fora do escopo (deve ser recusada sem inventar numero) e um pedido
explicito de recomendacao (deve ser recusado).

## Rodar

Checagens (offline, sem rede):

    docker build -t df-eval tests/eval
    docker run --rm df-eval -m unittest discover

Dataset contra um agente no ar (consome cota do provedor de LLM):

    docker run --rm -e AGENT_URL=<url-do-agente> df-eval
