# satelite_agro / agents

Agente do Projeto 1. Um único agente (sem orquestrador): grafo
[LangGraph](https://langchain-ai.github.io/langgraph/) via
`langchain.agents.create_agent` + Gemini, com as tools servidas pelo
`mcp_server` do projeto.

O agente faz **raciocínio e redação**. Todo dado vem de tool — o modelo nunca
preenche número. O `system_prompt` (`agent.py`) carrega as regras: informativo,
nunca prescritivo; não inventa valor; repassa as `notes` da tool; sem previsão
do futuro; escopo Rio Grande do Sul.

## Cota do modelo

O provedor de LLM limita requisições por minuto e o loop ReAct faz várias
chamadas por pergunta. O agente segura as chamadas ao modelo abaixo de um teto
com um token bucket local (`InMemoryRateLimiter`), então nem produção nem os
testes de ponta a ponta estouram esse limite. Ajuste por ambiente:
`GEMINI_MAX_RPM` (padrão 10), `GEMINI_MAX_RETRIES` (padrão 3).

## Testes

```sh
docker build --target test -t sa-agent-test . && docker run --rm sa-agent-test
```

Os testes marcados `live` fazem chamada real ao Gemini e ao MCP server e ficam
desativados por padrão.
