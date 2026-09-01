package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func newFakeAgent(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/ask", func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"answer":"eco: ` + string(body) + `"}`))
	})
	mux.HandleFunc("/status", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ready":true,"in_flight":0,"models":{}}`))
	})
	return httptest.NewServer(mux)
}

func mustParseURL(t *testing.T, raw string) *url.URL {
	t.Helper()
	u, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("url inválida %q: %v", raw, err)
	}
	return u
}

func TestAskEhEncaminhadoProAgente(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute))
	req := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"oi"}`))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, corpo = %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `eco: {"question":"oi"}`) {
		t.Fatalf("corpo não repassado como esperado: %s", rec.Body.String())
	}
}

func TestStatusEhEncaminhadoProAgente(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute))
	req := httptest.NewRequest(http.MethodGet, "/api/status", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"ready":true`) {
		t.Fatalf("corpo inesperado: %s", rec.Body.String())
	}
}

func TestRateLimitBloqueiaAposOLimiteEmAsk(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 1, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter)

	primeira := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{}`))
	primeira.Header.Set("X-Forwarded-For", "10.0.0.1")
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, primeira)
	if rec1.Code != http.StatusOK {
		t.Fatalf("1ª pergunta deveria passar, status = %d", rec1.Code)
	}

	segunda := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{}`))
	segunda.Header.Set("X-Forwarded-For", "10.0.0.1")
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, segunda)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("2ª pergunta do mesmo IP deveria ser bloqueada, status = %d", rec2.Code)
	}
}

func TestRateLimitEhPorIP(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 1, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter)

	reqA := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{}`))
	reqA.Header.Set("X-Forwarded-For", "10.0.0.1")
	recA := httptest.NewRecorder()
	mux.ServeHTTP(recA, reqA)

	reqB := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{}`))
	reqB.Header.Set("X-Forwarded-For", "10.0.0.2")
	recB := httptest.NewRecorder()
	mux.ServeHTTP(recB, reqB)

	if recA.Code != http.StatusOK || recB.Code != http.StatusOK {
		t.Fatalf("IPs diferentes têm orçamento próprio: A=%d B=%d", recA.Code, recB.Code)
	}
}

func TestStatusNaoEhLimitado(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 1, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter)

	// consome o orçamento de /api/ask pro IP...
	ask := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{}`))
	ask.Header.Set("X-Forwarded-For", "10.0.0.1")
	mux.ServeHTTP(httptest.NewRecorder(), ask)

	// ...mas /api/status continua liberado várias vezes seguidas.
	for i := 0; i < 3; i++ {
		req := httptest.NewRequest(http.MethodGet, "/api/status", nil)
		req.Header.Set("X-Forwarded-For", "10.0.0.1")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("chamada %d a /api/status deveria passar, status = %d", i+1, rec.Code)
		}
	}
}

func TestClientIPUsaXForwardedFor(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Forwarded-For", "203.0.113.9, 10.0.0.1")
	req.RemoteAddr = "172.17.0.5:54321"
	if ip := clientIP(req); ip != "203.0.113.9" {
		t.Fatalf("esperava o 1º IP da lista, veio %q", ip)
	}
}

func TestClientIPCaiParaRemoteAddr(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.RemoteAddr = "172.17.0.5:54321"
	if ip := clientIP(req); ip != "172.17.0.5" {
		t.Fatalf("esperava RemoteAddr sem porta, veio %q", ip)
	}
}

func TestRotaNaoImplementadaContinuaComo501(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute))
	req := httptest.NewRequest(http.MethodGet, "/api/algo-futuro", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status = %d, esperava 501", rec.Code)
	}
}
