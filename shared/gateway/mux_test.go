package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

type fakeAgent struct {
	*httptest.Server
	askCalls *int32
}

func newFakeAgent(t *testing.T) *fakeAgent {
	t.Helper()
	return newFakeAgentWithStatus(t, http.StatusOK)
}

// newFakeAgentWithStatus faz /ask sempre devolver o status dado — usado pra
// testar que respostas de erro nunca ficam cacheadas.
func newFakeAgentWithStatus(t *testing.T, status int) *fakeAgent {
	t.Helper()
	var calls int32
	mux := http.NewServeMux()
	mux.HandleFunc("/ask", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&calls, 1)
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(`{"answer":"eco: ` + string(body) + `"}`))
	})
	mux.HandleFunc("/status", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ready":true,"in_flight":0,"models":{}}`))
	})
	mux.HandleFunc("/land_use/summary", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"available":true,"region_query":"` + r.URL.Query().Get("region") + `"}`))
	})
	srv := httptest.NewServer(mux)
	return &fakeAgent{Server: srv, askCalls: &calls}
}

func (f *fakeAgent) AskCalls() int32 { return atomic.LoadInt32(f.askCalls) }

func mustParseURL(t *testing.T, raw string) *url.URL {
	t.Helper()
	u, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("url inválida %q: %v", raw, err)
	}
	return u
}

// noCache devolve um cache sempre desligado (ttl=0) — pros testes que não
// são sobre cache, não quero que um hit inesperado esconda um bug.
func noCache() *ResponseCache {
	return NewResponseCache(nil, 0)
}

// noBreaker devolve um circuit breaker sempre desligado (threshold=0) — pros
// testes que não são sobre o breaker.
func noBreaker() *CircuitBreaker {
	return NewCircuitBreaker(0, 0)
}

func newTestCache(t *testing.T, ttl time.Duration) *ResponseCache {
	t.Helper()
	srv := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: srv.Addr()})
	return NewResponseCache(client, ttl)
}

func TestAskEhEncaminhadoProAgente(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute), noCache(), noBreaker())
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

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute), noCache(), noBreaker())
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
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), noBreaker())

	primeira := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"a"}`))
	primeira.Header.Set("X-Forwarded-For", "10.0.0.1")
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, primeira)
	if rec1.Code != http.StatusOK {
		t.Fatalf("1ª pergunta deveria passar, status = %d", rec1.Code)
	}

	segunda := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"b"}`))
	segunda.Header.Set("X-Forwarded-For", "10.0.0.1")
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, segunda)
	if rec2.Code != http.StatusTooManyRequests {
		t.Fatalf("2ª pergunta (diferente, sem cache) do mesmo IP deveria ser bloqueada, status = %d", rec2.Code)
	}
}

func TestRateLimitEhPorIP(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 1, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), noBreaker())

	reqA := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"a"}`))
	reqA.Header.Set("X-Forwarded-For", "10.0.0.1")
	recA := httptest.NewRecorder()
	mux.ServeHTTP(recA, reqA)

	reqB := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"a"}`))
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
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), noBreaker())

	// consome o orçamento de /api/ask pro IP...
	ask := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"a"}`))
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

func TestAskCacheHitNaoBateNoAgente(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	cache := newTestCache(t, time.Minute)
	limiter, _ := newTestLimiter(t, 100, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, cache, noBreaker())

	pergunta := `{"question":"mesma pergunta"}`
	req1 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(pergunta))
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK || rec1.Header().Get("X-Cache") == "hit" {
		t.Fatalf("1ª chamada deveria ser miss (proxiada), status=%d X-Cache=%q", rec1.Code, rec1.Header().Get("X-Cache"))
	}

	req2 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(pergunta))
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK || rec2.Header().Get("X-Cache") != "hit" {
		t.Fatalf("2ª chamada (mesma pergunta) deveria ser cache hit, status=%d X-Cache=%q", rec2.Code, rec2.Header().Get("X-Cache"))
	}
	if rec1.Body.String() != rec2.Body.String() {
		t.Fatalf("corpo do hit deveria ser igual ao da resposta original: %q vs %q", rec1.Body.String(), rec2.Body.String())
	}
	if calls := agent.AskCalls(); calls != 1 {
		t.Fatalf("agente deveria ter recebido só 1 chamada, recebeu %d", calls)
	}
}

func TestAskCacheHitNaoContaNoRateLimit(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	cache := newTestCache(t, time.Minute)
	limiter, _ := newTestLimiter(t, 1, time.Minute) // só 1 pergunta/min por IP
	mux := newMux(mustParseURL(t, agent.URL), limiter, cache, noBreaker())

	mesma := `{"question":"repete"}`
	ip := "10.0.0.9"

	// 1ª: miss, consome o único slot do rate limit.
	req1 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(mesma))
	req1.Header.Set("X-Forwarded-For", ip)
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("1ª deveria passar, status = %d", rec1.Code)
	}

	// 2ª: mesma pergunta, mesmo IP sem orçamento — mas é cache hit, não deveria ser bloqueada.
	req2 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(mesma))
	req2.Header.Set("X-Forwarded-For", ip)
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK || rec2.Header().Get("X-Cache") != "hit" {
		t.Fatalf("cache hit não deveria ser bloqueado pelo rate limit, status=%d", rec2.Code)
	}

	// 3ª: pergunta diferente, mesmo IP, sem orçamento — essa sim deve ser bloqueada.
	req3 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"outra"}`))
	req3.Header.Set("X-Forwarded-For", ip)
	rec3 := httptest.NewRecorder()
	mux.ServeHTTP(rec3, req3)
	if rec3.Code != http.StatusTooManyRequests {
		t.Fatalf("pergunta nova sem orçamento deveria ser bloqueada, status = %d", rec3.Code)
	}
}

func TestAskNaoCacheiaResposta5xx(t *testing.T) {
	agent := newFakeAgentWithStatus(t, http.StatusBadGateway)
	defer agent.Close()

	cache := newTestCache(t, time.Minute)
	limiter, _ := newTestLimiter(t, 100, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, cache, noBreaker())

	pergunta := `{"question":"falha"}`
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(pergunta))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusBadGateway {
			t.Fatalf("chamada %d: status = %d, esperava 502", i+1, rec.Code)
		}
	}
	if calls := agent.AskCalls(); calls != 2 {
		t.Fatalf("erro nunca deveria ser cacheado — esperava 2 chamadas ao agente, teve %d", calls)
	}
}

func TestLandUseSummaryEhEncaminhadoProAgenteComQueryString(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute), noCache(), noBreaker())
	req := httptest.NewRequest(http.MethodGet, "/api/land_use/summary?region=Porto+Alegre&year=2025", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, corpo = %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"region_query":"Porto Alegre"`) {
		t.Fatalf("query string não repassada como esperado: %s", rec.Body.String())
	}
}

func TestLandUseNaoEhLimitadoNemPassaPeloCircuitBreaker(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 1, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), noBreaker())

	// consome o único slot do rate limit em /api/ask...
	ask := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"a"}`))
	ask.Header.Set("X-Forwarded-For", "10.0.0.1")
	mux.ServeHTTP(httptest.NewRecorder(), ask)

	// ...mas /api/land_use/* não é afetado (consulta determinística, não gasta cota do LLM).
	for i := 0; i < 3; i++ {
		req := httptest.NewRequest(http.MethodGet, "/api/land_use/summary?region=RS", nil)
		req.Header.Set("X-Forwarded-For", "10.0.0.1")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("chamada %d a /api/land_use/summary deveria passar, status = %d", i+1, rec.Code)
		}
	}
}

func TestAskCircuitBreakerAbreDepoisDeFalhasEBloqueiaSemBaterNoAgente(t *testing.T) {
	agent := newFakeAgentWithStatus(t, http.StatusBadGateway)
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 100, time.Minute)
	breaker := NewCircuitBreaker(2, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), breaker)

	perguntas := []string{`{"question":"q1"}`, `{"question":"q2"}`}
	for i, p := range perguntas {
		req := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(p))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusBadGateway {
			t.Fatalf("chamada %d: status = %d, esperava 502 (repassado do agente)", i+1, rec.Code)
		}
	}
	if calls := agent.AskCalls(); calls != 2 {
		t.Fatalf("esperava 2 chamadas ao agente antes do circuito abrir, teve %d", calls)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"depois de abrir"}`))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("com o circuito aberto esperava 503, veio %d", rec.Code)
	}
	if calls := agent.AskCalls(); calls != 2 {
		t.Fatalf("com o circuito aberto o agente não deveria receber mais chamadas, teve %d", calls)
	}
}

func TestAskCacheHitFuncionaMesmoComCircuitoAberto(t *testing.T) {
	agent := newFakeAgent(t)
	defer agent.Close()

	cache := newTestCache(t, time.Minute)
	limiter, _ := newTestLimiter(t, 100, time.Minute)
	breaker := NewCircuitBreaker(1, time.Hour)
	mux := newMux(mustParseURL(t, agent.URL), limiter, cache, breaker)

	pergunta := `{"question":"vai pro cache"}`
	req1 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(pergunta))
	mux.ServeHTTP(httptest.NewRecorder(), req1)

	breaker.RecordFailure() // simula uma degradação depois que a resposta já estava cacheada
	if breaker.Allow() {
		t.Fatal("sanity check: circuito deveria estar aberto agora")
	}

	req2 := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(pergunta))
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK || rec2.Header().Get("X-Cache") != "hit" {
		t.Fatalf("cache hit deveria funcionar mesmo com o circuito aberto, status=%d", rec2.Code)
	}
}

func TestAskSucessoZeraOContadorDeFalhas(t *testing.T) {
	agent := newFakeAgent(t) // sempre 200
	defer agent.Close()

	limiter, _ := newTestLimiter(t, 100, time.Minute)
	breaker := NewCircuitBreaker(2, time.Minute)
	mux := newMux(mustParseURL(t, agent.URL), limiter, noCache(), breaker)

	breaker.RecordFailure() // 1 falha manual — ainda fechado (limite=2)

	req := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(`{"question":"ok"}`))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("deveria passar normalmente, status = %d", rec.Code)
	}

	// o sucesso (200) deveria ter zerado o contador — só 1 falha nova não pode abrir.
	breaker.RecordFailure()
	if !breaker.Allow() {
		t.Fatal("sucesso deveria zerar o contador de falhas: 1 falha nova (limite=2) não deveria abrir")
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

	mux := newMux(mustParseURL(t, agent.URL), NewRateLimiter(nil, 0, time.Minute), noCache(), noBreaker())
	req := httptest.NewRequest(http.MethodGet, "/api/algo-futuro", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status = %d, esperava 501", rec.Code)
	}
}
