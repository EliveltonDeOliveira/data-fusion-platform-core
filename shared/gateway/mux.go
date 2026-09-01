package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
)

type ctxKey int

const askCacheKeyCtx ctxKey = iota

// newMux monta as rotas do gateway: proxy pro agente atrás de /api/ask
// (cache de resposta + rate limit por IP) e /api/status (livre — só
// consulta a fila, não gasta cota de LLM).
func newMux(agentURL *url.URL, limiter *RateLimiter, cache *ResponseCache) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", healthzHandler)
	mux.Handle("POST /api/ask", newAskHandler(agentURL, limiter, cache))
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

// newAskHandler encadeia cache → rate limit → proxy: um hit de cache nunca
// consome o orçamento por IP (não bate no LLM); só um miss passa pelo
// limiter e, se a resposta do agente vier 200, fica guardada pro próximo.
func newAskHandler(agentURL *url.URL, limiter *RateLimiter, cache *ResponseCache) http.Handler {
	proxy := httputil.NewSingleHostReverseProxy(agentURL)
	director := proxy.Director
	proxy.Director = func(req *http.Request) {
		director(req)
		req.URL.Path = "/ask"
	}
	proxy.ModifyResponse = func(resp *http.Response) error {
		if resp.StatusCode != http.StatusOK {
			return nil
		}
		key, _ := resp.Request.Context().Value(askCacheKeyCtx).(string)
		if key == "" {
			return nil
		}
		respBody, err := io.ReadAll(resp.Body)
		if err != nil {
			return err
		}
		_ = resp.Body.Close()
		resp.Body = io.NopCloser(bytes.NewReader(respBody))
		resp.ContentLength = int64(len(respBody))
		resp.Header.Set("Content-Length", strconv.Itoa(len(respBody)))
		cache.Set(resp.Request.Context(), key, respBody)
		return nil
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "corpo inválido", http.StatusBadRequest)
			return
		}
		_ = r.Body.Close()

		key := askCacheKey(body)
		if cached, ok := cache.Get(r.Context(), key); ok {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.Header().Set("X-Cache", "hit")
			_, _ = w.Write(cached)
			return
		}

		if !limiter.Allow(r.Context(), "ratelimit:"+clientIP(r)) {
			writeTooManyRequests(w)
			return
		}

		r.Body = io.NopCloser(bytes.NewReader(body))
		r.ContentLength = int64(len(body))
		ctx := context.WithValue(r.Context(), askCacheKeyCtx, key)
		proxy.ServeHTTP(w, r.WithContext(ctx))
	})
}

func writeTooManyRequests(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Retry-After", "60")
	w.WriteHeader(http.StatusTooManyRequests)
	_, _ = w.Write([]byte(
		`{"detail":"muitas perguntas em pouco tempo — aguarde um pouco e tente de novo"}`,
	))
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
