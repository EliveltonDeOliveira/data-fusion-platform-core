package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"time"

	"github.com/redis/go-redis/v9"
)

// ResponseCache guarda a resposta de /ask no Valkey por um TTL curto — a
// mesma pergunta repetida (comum sob teste, ou 2 usuários perguntando a
// mesma coisa) não gasta cota do LLM de novo. Só respostas 200 são
// cacheadas — erro nunca fica cacheado, senão uma falha temporária do
// provedor "gruda" pelo TTL inteiro.
type ResponseCache struct {
	client *redis.Client
	ttl    time.Duration
}

func NewResponseCache(client *redis.Client, ttl time.Duration) *ResponseCache {
	return &ResponseCache{client: client, ttl: ttl}
}

func (c *ResponseCache) Get(ctx context.Context, key string) ([]byte, bool) {
	if c == nil || c.client == nil || c.ttl <= 0 || key == "" {
		return nil, false
	}
	val, err := c.client.Get(ctx, key).Bytes()
	if err != nil {
		return nil, false
	}
	return val, true
}

func (c *ResponseCache) Set(ctx context.Context, key string, body []byte) {
	if c == nil || c.client == nil || c.ttl <= 0 || key == "" {
		return
	}
	c.client.Set(ctx, key, body, c.ttl)
}

// askCacheKey identifica a pergunta pelo corpo cru da requisição — a UI
// sempre manda o mesmo formato (`{"question": "..."}`), então o hash do
// corpo já é uma chave estável sem precisar parsear/normalizar o JSON.
func askCacheKey(body []byte) string {
	sum := sha256.Sum256(body)
	return "askcache:" + hex.EncodeToString(sum[:])
}
