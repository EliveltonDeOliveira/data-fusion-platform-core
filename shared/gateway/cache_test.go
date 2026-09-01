package main

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestAskCacheKeyEhEstavelEDistingueCorpo(t *testing.T) {
	a := askCacheKey([]byte(`{"question":"x"}`))
	b := askCacheKey([]byte(`{"question":"x"}`))
	c := askCacheKey([]byte(`{"question":"y"}`))
	if a != b {
		t.Fatal("mesmo corpo deveria gerar a mesma chave")
	}
	if a == c {
		t.Fatal("corpos diferentes não deveriam colidir na chave")
	}
}

func TestResponseCacheSetEGet(t *testing.T) {
	srv := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: srv.Addr()})
	cache := NewResponseCache(client, time.Minute)
	ctx := context.Background()

	if _, ok := cache.Get(ctx, "k"); ok {
		t.Fatal("não deveria ter nada guardado ainda")
	}
	cache.Set(ctx, "k", []byte("resposta"))
	got, ok := cache.Get(ctx, "k")
	if !ok || string(got) != "resposta" {
		t.Fatalf("esperava hit com 'resposta', veio ok=%v got=%q", ok, got)
	}
}

func TestResponseCacheExpiraDepoisDoTTL(t *testing.T) {
	srv := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: srv.Addr()})
	cache := NewResponseCache(client, time.Minute)
	ctx := context.Background()

	cache.Set(ctx, "k", []byte("resposta"))
	srv.FastForward(time.Minute + time.Second)
	if _, ok := cache.Get(ctx, "k"); ok {
		t.Fatal("depois do TTL deveria ser miss")
	}
}

func TestResponseCacheDesligadaComTTLZero(t *testing.T) {
	srv := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: srv.Addr()})
	cache := NewResponseCache(client, 0)
	ctx := context.Background()

	cache.Set(ctx, "k", []byte("resposta"))
	if _, ok := cache.Get(ctx, "k"); ok {
		t.Fatal("TTL <= 0 significa cache desligado — nunca deveria dar hit")
	}
}

func TestResponseCacheSemClienteEhSempreMiss(t *testing.T) {
	cache := NewResponseCache(nil, time.Minute)
	ctx := context.Background()
	cache.Set(ctx, "k", []byte("resposta")) // não deve entrar em pânico sem cliente
	if _, ok := cache.Get(ctx, "k"); ok {
		t.Fatal("sem cliente configurado, nunca deveria dar hit")
	}
}
