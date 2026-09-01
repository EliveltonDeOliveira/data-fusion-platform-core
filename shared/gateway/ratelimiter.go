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
