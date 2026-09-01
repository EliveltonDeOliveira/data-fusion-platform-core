# tests/eval

Dataset dourado por projeto — perguntas de referencia com as propriedades que a
resposta do agente precisa ter, para checagem deterministica de regressao.

- `cases/<projeto>.json` — as perguntas e o que se espera de cada uma.
- `checks.py` — as checagens (funcoes puras), agnosticas de tool: a tool certa
  foi chamada, os especialistas certos foram acionados, a regiao/ano/nivel
  resolveu, nao ha numero nem classe sem lastro na tool, o texto nao recomenda
  manejo, e perguntas de correlacao trazem dado das duas dimensoes.
- `run.py` — envia cada pergunta a um agente no ar e aplica as checagens.
- `test_checks.py` — testes das checagens, offline.

O dataset de `satelite_agro` cobre clima (3 perguntas-ancora + fora do escopo +
pedido de recomendacao), uso da terra (composicao por municipio e por estado,
consulta por ponto, variacao entre dois anos, ano sem cobertura, fora do escopo,
pedido de recomendacao) e correlacao entre clima e uso da terra (roteamento para
dois especialistas). Cada `expect` liga so os checadores que fazem sentido.

## Rodar

Checagens (offline, sem rede):

    docker build -t df-eval tests/eval
    docker run --rm df-eval -m unittest discover

Dataset contra um agente no ar (consome cota do provedor de LLM):

    docker run --rm -e AGENT_URL=<url-do-agente> df-eval
