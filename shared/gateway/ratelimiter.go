package main

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)

// RateLimiter aplica um teto de requisições por janela (ex.: por minuto) por
// chave (IP do cliente), contado no Valkey via INCR+EXPIRE — janela fixa,
// sem persistir a chave em disco (Valkey roda com --save "").
//
// Falha aberta: se o Valkey não responder, a requisição passa. Preferível a
// derrubar tráfego legítimo por uma falha de infra que não é culpa do
// cliente — o teto real de custo (cota do Gemini) já é aplicado mais adiante
// pelo agente (TrackedRateLimiter), então esta camada é só a 1ª linha de
// defesa contra um único cliente monopolizar essa cota compartilhada.
type RateLimiter struct {
	client *redis.Client
	limit  int64
	window time.Duration
}

func NewRateLimiter(client *redis.Client, limit int64, window time.Duration) *RateLimiter {
	return &RateLimiter{client: client, limit: limit, window: window}
}

// Allow incrementa o contador da chave nesta janela e devolve false quando o
// limite já foi excedido. Sem cliente configurado (Valkey ausente) ou limite
// <= 0, sempre permite.
func (r *RateLimiter) Allow(ctx context.Context, key string) bool {
	if r == nil || r.client == nil || r.limit <= 0 {
		return true
	}
	count, err := r.client.Incr(ctx, key).Result()
	if err != nil {
		return true // fail-open
	}
	if count == 1 {
		r.client.Expire(ctx, key, r.window)
	}
	return count <= r.limit
}

// RateLimitSnapshot é o estado atual da janela de uma chave, pra mostrar ao
// próprio cliente quanto da cota já usou — sem alterar o contador nem influenciar
// o próximo Allow. Configured=false quando o rate limiter está desligado
// (sem Valkey ou limite <= 0): a UI sabe distinguir "sem limite configurado"
// de "0 usado".
type RateLimitSnapshot struct {
	Used         int64
	Limit        int64
	ResetSeconds int
	Configured   bool
}

// Snapshot lê o contador e o TTL da chave sem incrementar (GET+TTL, não
// INCR). Usado pelo /api/status pra devolver ao cliente sua própria cota
// restante nesta janela — mais preciso que uma posição de fila inventada,
// já que o mecanismo real é um teto por IP por minuto, não uma fila FIFO.
func (r *RateLimiter) Snapshot(ctx context.Context, key string) RateLimitSnapshot {
	if r == nil || r.client == nil || r.limit <= 0 {
		return RateLimitSnapshot{}
	}
	used, err := r.client.Get(ctx, key).Int64()
	if err != nil {
		used = 0 // chave ainda não existe nesta janela (fail-open também aqui: mostra 0, não erro)
	}
	resetSeconds := 0
	if ttl, err := r.client.TTL(ctx, key).Result(); err == nil && ttl > 0 {
		resetSeconds = int(ttl.Seconds())
	}
	return RateLimitSnapshot{Used: used, Limit: r.limit, ResetSeconds: resetSeconds, Configured: true}
}
