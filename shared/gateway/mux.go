package main

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

// newMux monta as rotas do gateway: proxy pro agente atrás de /api/ask
// (limitado por IP) e /api/status (livre — só consulta a fila, não gasta
// cota de LLM).
func newMux(agentURL *url.URL, limiter *RateLimiter) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthzHandler)
	mux.Handle("POST /api/ask", rateLimitMiddleware(limiter, newUpstreamProxy(agentURL, "/ask")))
	mux.Handle("GET /api/status", newUpstreamProxy(agentURL, "/status"))
	mux.HandleFunc("/api/", func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "não implementado", http.StatusNotImplemented)
	})
	return mux
}

func healthzHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	fmt.Fprintln(w, "ok")
}

// newUpstreamProxy encaminha pro agente sempre no mesmo path fixo do
// upstream — cada rota do gateway mapeia 1:1 pra uma rota do agente, então
// não precisa de reescrita de prefixo.
func newUpstreamProxy(agentURL *url.URL, upstreamPath string) http.Handler {
	proxy := httputil.NewSingleHostReverseProxy(agentURL)
	director := proxy.Director
	proxy.Director = func(req *http.Request) {
		director(req)
		req.URL.Path = upstreamPath
	}
	return proxy
}

// rateLimitMiddleware aplica o RateLimiter por IP do cliente. O IP nunca é
// logado nem persistido — só usado como chave transiente no Valkey (TTL da
// janela) via RateLimiter.
func rateLimitMiddleware(limiter *RateLimiter, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !limiter.Allow(r.Context(), "ratelimit:"+clientIP(r)) {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.Header().Set("Retry-After", "60")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(
				`{"detail":"muitas perguntas em pouco tempo — aguarde um pouco e tente de novo"}`,
			))
			return
		}
		next.ServeHTTP(w, r)
	})
}

// clientIP lê o 1º IP de X-Forwarded-For (o proxy reverso adiciona,
// mesmo sem gravar no access log) e cai pro RemoteAddr da conexão direta.
func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		first, _, _ := strings.Cut(xff, ",")
		return strings.TrimSpace(first)
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
