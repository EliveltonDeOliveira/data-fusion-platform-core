// Gateway (Go) — proxy único de entrada pros agentes. Aplica rate limit por
// IP (Valkey, janela de 1 min) na frente de /api/ask, protegendo a cota
// compartilhada do LLM de um único cliente monopolizá-la.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
)

func main() {
	healthcheck := flag.Bool("healthcheck", false, "consulta /healthz localmente e sai (0 ok, 1 falha)")
	flag.Parse()

	port := envOr("GATEWAY_PORT", "8080")

	if *healthcheck {
		os.Exit(runHealthcheck(port))
	}

	agentURL, err := url.Parse(envOr("AGENT_URL", "http://agent-satelite-agro:8000"))
	if err != nil {
		log.Fatalf("AGENT_URL inválido: %v", err)
	}

	valkey := buildValkeyClient()
	limit := envOrInt("GATEWAY_RATE_LIMIT_RPM", 6)
	limiter := NewRateLimiter(valkey, int64(limit), time.Minute)
	cacheTTL := time.Duration(envOrInt("GATEWAY_ASK_CACHE_TTL", 300)) * time.Second
	cache := NewResponseCache(valkey, cacheTTL)

	mux := newMux(agentURL, limiter, cache)

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("gateway ouvindo em :%s (agente=%s)", port, agentURL)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("erro no servidor: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}

// buildValkeyClient devolve nil se VALKEY_URL não estiver configurada — dev
// local sem a infra completa não deve travar (rate limiter e cache ficam
// sem-op automaticamente com client nil, ver ratelimiter.go/cache.go).
func buildValkeyClient() *redis.Client {
	valkeyURL := os.Getenv("VALKEY_URL")
	if valkeyURL == "" {
		return nil
	}
	opts, err := redis.ParseURL(valkeyURL)
	if err != nil {
		log.Printf("VALKEY_URL inválida, rate limit e cache desligados: %v", err)
		return nil
	}
	return redis.NewClient(opts)
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envOrInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func runHealthcheck(port string) int {
	client := http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://localhost:" + port + "/healthz")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "status %d\n", resp.StatusCode)
		return 1
	}
	return 0
}
