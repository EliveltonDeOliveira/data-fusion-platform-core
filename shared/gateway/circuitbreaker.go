package main

import (
	"sync"
	"time"
)

type cbState int

const (
	cbClosed cbState = iota
	cbOpen
	cbHalfOpen
)

// CircuitBreaker protege o agente (e, por trás dele, o provedor de LLM) de
// receber tráfego durante uma degradação sustentada: depois de várias
// falhas seguidas, para de tentar por um tempo de resfriamento e falha
// rápido — em vez de cada requisição esperar o timeout inteiro contra um
// upstream capenga (na prática, já vimos o Gemini devolver 503 "high
// demand" ao vivo). Estado só em memória do processo — não precisa ser
// compartilhado entre instâncias, já que só roda 1 gateway.
type CircuitBreaker struct {
	mu        sync.Mutex
	state     cbState
	failures  int
	openUntil time.Time

	threshold int
	cooldown  time.Duration
	now       func() time.Time
}

func NewCircuitBreaker(threshold int, cooldown time.Duration) *CircuitBreaker {
	return newCircuitBreaker(threshold, cooldown, time.Now)
}

// newCircuitBreaker permite injetar o relógio nos testes (determinismo sem
// sleep real esperando o resfriamento passar).
func newCircuitBreaker(threshold int, cooldown time.Duration, now func() time.Time) *CircuitBreaker {
	return &CircuitBreaker{threshold: threshold, cooldown: cooldown, now: now}
}

// Allow decide se a requisição pode seguir pro upstream. Quando o circuito
// está aberto mas o resfriamento já passou, deixa 1 requisição de teste
// passar (half-open) sem fechar o circuito ainda — só RecordSuccess fecha.
func (b *CircuitBreaker) Allow() bool {
	if b == nil || b.threshold <= 0 {
		return true
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.state != cbOpen {
		return true
	}
	if b.now().Before(b.openUntil) {
		return false
	}
	b.state = cbHalfOpen
	return true
}

// RecordSuccess fecha o circuito e zera o contador de falhas.
func (b *CircuitBreaker) RecordSuccess() {
	if b == nil {
		return
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures = 0
	b.state = cbClosed
}

// RecordFailure conta uma falha; no estado half-open, qualquer falha reabre
// na hora (não espera acumular o threshold de novo).
func (b *CircuitBreaker) RecordFailure() {
	if b == nil || b.threshold <= 0 {
		return
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.state == cbHalfOpen {
		b.trip()
		return
	}
	b.failures++
	if b.failures >= b.threshold {
		b.trip()
	}
}

func (b *CircuitBreaker) trip() {
	b.state = cbOpen
	b.openUntil = b.now().Add(b.cooldown)
	b.failures = 0
}

// RetryAfterSeconds devolve quanto falta pro fim do resfriamento (mínimo 1s,
// pra sempre mandar um valor útil no header quando o circuito está aberto).
func (b *CircuitBreaker) RetryAfterSeconds() int {
	if b == nil {
		return 0
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	remaining := b.openUntil.Sub(b.now())
	if remaining <= 0 {
		return 1
	}
	return int(remaining.Seconds()) + 1
}
