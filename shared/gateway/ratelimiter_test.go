package main

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newTestLimiter(t *testing.T, limit int64, window time.Duration) (*RateLimiter, *miniredis.Miniredis) {
	t.Helper()
	srv := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: srv.Addr()})
	return NewRateLimiter(client, limit, window), srv
}

func TestAllowDentroDoLimite(t *testing.T) {
	limiter, _ := newTestLimiter(t, 3, time.Minute)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		if !limiter.Allow(ctx, "k") {
			t.Fatalf("requisição %d deveria ser permitida", i+1)
		}
	}
}

func TestAllowBloqueiaAcimaDoLimite(t *testing.T) {
	limiter, _ := newTestLimiter(t, 2, time.Minute)
	ctx := context.Background()
	limiter.Allow(ctx, "k")
	limiter.Allow(ctx, "k")
	if limiter.Allow(ctx, "k") {
		t.Fatal("3ª requisição deveria ser bloqueada com limite=2")
	}
}

func TestAllowEhPorChave(t *testing.T) {
	limiter, _ := newTestLimiter(t, 1, time.Minute)
	ctx := context.Background()
	if !limiter.Allow(ctx, "ip-a") {
		t.Fatal("1ª chamada de ip-a deveria passar")
	}
	if !limiter.Allow(ctx, "ip-b") {
		t.Fatal("ip-b tem orçamento próprio, não deveria ser afetado por ip-a")
	}
	if limiter.Allow(ctx, "ip-a") {
		t.Fatal("2ª chamada de ip-a deveria ser bloqueada")
	}
}

func TestAllowResetaDepoisDaJanela(t *testing.T) {
	limiter, srv := newTestLimiter(t, 1, time.Minute)
	ctx := context.Background()
	limiter.Allow(ctx, "k")
	if limiter.Allow(ctx, "k") {
		t.Fatal("2ª chamada dentro da janela deveria ser bloqueada")
	}
	srv.FastForward(time.Minute + time.Second)
	if !limiter.Allow(ctx, "k") {
		t.Fatal("depois da janela expirar, o contador deveria reiniciar")
	}
}

func TestAllowFailOpenSemCliente(t *testing.T) {
	limiter := NewRateLimiter(nil, 1, time.Minute)
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		if !limiter.Allow(ctx, "k") {
			t.Fatal("sem cliente configurado, nunca deveria bloquear")
		}
	}
}

func TestAllowFailOpenComLimiteZero(t *testing.T) {
	limiter, _ := newTestLimiter(t, 0, time.Minute)
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		if !limiter.Allow(ctx, "k") {
			t.Fatal("limite <= 0 significa rate limit desligado")
		}
	}
}

func TestSnapshotRefleteUsoAtual(t *testing.T) {
	limiter, _ := newTestLimiter(t, 5, time.Minute)
	ctx := context.Background()
	limiter.Allow(ctx, "k")
	limiter.Allow(ctx, "k")
	limiter.Allow(ctx, "k")

	snap := limiter.Snapshot(ctx, "k")
	if !snap.Configured {
		t.Fatal("com cliente e limite > 0, deveria vir Configured=true")
	}
	if snap.Used != 3 {
		t.Fatalf("Used = %d, esperava 3", snap.Used)
	}
	if snap.Limit != 5 {
		t.Fatalf("Limit = %d, esperava 5", snap.Limit)
	}
	if snap.ResetSeconds <= 0 {
		t.Fatalf("ResetSeconds = %d, esperava > 0 (janela ainda ativa)", snap.ResetSeconds)
	}
}

func TestSnapshotNaoIncrementaOContador(t *testing.T) {
	limiter, _ := newTestLimiter(t, 1, time.Minute)
	ctx := context.Background()
	limiter.Snapshot(ctx, "k")
	limiter.Snapshot(ctx, "k")
	if !limiter.Allow(ctx, "k") {
		t.Fatal("Snapshot não deveria consumir orçamento — 1ª chamada de Allow ainda devia passar")
	}
}

func TestSnapshotChaveAindaNaoUsadaDevolveZero(t *testing.T) {
	limiter, _ := newTestLimiter(t, 5, time.Minute)
	snap := limiter.Snapshot(context.Background(), "nunca-usada")
	if !snap.Configured || snap.Used != 0 || snap.ResetSeconds != 0 {
		t.Fatalf("esperava Configured=true, Used=0, ResetSeconds=0 (sem janela ativa), obtive %+v", snap)
	}
}

func TestSnapshotNaoConfiguradoSemCliente(t *testing.T) {
	limiter := NewRateLimiter(nil, 5, time.Minute)
	snap := limiter.Snapshot(context.Background(), "k")
	if snap.Configured {
		t.Fatal("sem cliente configurado, Snapshot deveria devolver Configured=false")
	}
}
