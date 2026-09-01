# satelite_agro / agents

Agente do Projeto 1. Arquitetura multi-agente sobre
[LangGraph](https://langchain-ai.github.io/langgraph/): um **Supervisor**
decide quais especialistas a pergunta precisa e reescreve a sub-pergunta de
cada um; os especialistas (**Clima**, **Uso-da-Terra**, **Metodologia**) rodam
em paralelo, cada um um agente ReAct (`create_agent`) com o subconjunto de
tools do seu domínio, servidas pelo `mcp_server` — os dois primeiros sobre
dado de monitoramento, o terceiro faz busca por similaridade num corpus RAG
dos documentos de metodologia; uma etapa de **síntese** junta as respostas
quando mais de um especialista age. A saída é a mesma da versão de um agente
só (`answer`, `tool_calls`, `data`) mais o campo `specialists`.

Os agentes fazem **raciocínio e redação**. Todo dado vem de tool — o modelo
nunca preenche número. O `system_prompt` (`agent.py`) carrega as regras comuns:
informativo, nunca prescritivo; não inventa valor; repassa as `notes` da tool;
sem previsão do futuro; sem análise causal; escopo Rio Grande do Sul.

## Modelos e cota

O provedor de LLM limita requisições por minuto (por modelo) e o grafo faz
várias chamadas por pergunta. Duas defesas:

- **Alternância de modelos** — `GEMINI_MODELS` (lista) distribui os papéis
  (supervisor, especialistas, síntese) entre modelos equivalentes; cada modelo
  tem o seu próprio orçamento. `GEMINI_MODEL` (singular) força modelo único.
- **Token bucket local** por modelo (`InMemoryRateLimiter`) abaixo de
  `GEMINI_MAX_RPM` (padrão 10). `GEMINI_MAX_RETRIES` padrão 3.

## Trace de roteamento

Com `MLFLOW_TRACKING_URI` setado, cada requisição registra **só metadado
estrutural** (especialistas acionados, tools chamadas, modelo por papel,
latência) — nunca o texto da pergunta ou da resposta. Sem a variável, sem
trace.

## Testes

```sh
docker build --target test -t sa-agent-test . && docker run --rm sa-agent-test
```

Os testes marcados `live` fazem chamada real ao Gemini e ao MCP server e ficam
desativados por padrão.
