package main

import (
	"testing"
	"time"
)

func TestCircuitBreakerAbreNoLimiteDeFalhas(t *testing.T) {
	b := NewCircuitBreaker(2, time.Minute)
	if !b.Allow() {
		t.Fatal("deveria começar fechado")
	}
	b.RecordFailure()
	if !b.Allow() {
		t.Fatal("1 falha não deveria abrir (limite=2)")
	}
	b.RecordFailure()
	if b.Allow() {
		t.Fatal("2ª falha deveria abrir o circuito")
	}
}

func TestCircuitBreakerMeioAbreDepoisDoResfriamentoEFechaComSucesso(t *testing.T) {
	clock := time.Now()
	now := func() time.Time { return clock }
	b := newCircuitBreaker(1, time.Second, now)

	b.RecordFailure() // abre (limite=1)
	if b.Allow() {
		t.Fatal("deveria estar aberto logo após a falha")
	}

	clock = clock.Add(2 * time.Second) // passa do resfriamento
	if !b.Allow() {
		t.Fatal("depois do resfriamento deveria permitir 1 tentativa (half-open)")
	}

	b.RecordSuccess()
	if !b.Allow() {
		t.Fatal("sucesso no half-open deveria fechar o circuito")
	}
}

func TestCircuitBreakerFalhaNoHalfOpenReabreNaHora(t *testing.T) {
	clock := time.Now()
	now := func() time.Time { return clock }
	b := newCircuitBreaker(1, time.Second, now)

	b.RecordFailure()
	clock = clock.Add(2 * time.Second)
	if !b.Allow() {
		t.Fatal("deveria permitir a tentativa de teste (half-open)")
	}
	b.RecordFailure() // a tentativa de teste falhou de novo
	if b.Allow() {
		t.Fatal("falha no half-open deveria reabrir imediatamente, sem esperar novo threshold")
	}
}

func TestCircuitBreakerDesligadoComThresholdZero(t *testing.T) {
	b := NewCircuitBreaker(0, time.Minute)
	for i := 0; i < 10; i++ {
		b.RecordFailure()
		if !b.Allow() {
			t.Fatal("threshold <= 0 significa circuit breaker desligado — nunca deveria bloquear")
		}
	}
}

func TestCircuitBreakerRetryAfterSecondsProximoDoResfriamento(t *testing.T) {
	clock := time.Now()
	now := func() time.Time { return clock }
	b := newCircuitBreaker(1, 30*time.Second, now)
	b.RecordFailure()
	if got := b.RetryAfterSeconds(); got < 1 || got > 31 {
		t.Fatalf("esperava algo perto de 30s, veio %d", got)
	}
}

func TestCircuitBreakerNilEhSeguro(t *testing.T) {
	var b *CircuitBreaker
	if !b.Allow() {
		t.Fatal("breaker nil deveria sempre permitir")
	}
	b.RecordFailure()
	b.RecordSuccess()
	if got := b.RetryAfterSeconds(); got != 0 {
		t.Fatalf("breaker nil deveria devolver 0, veio %d", got)
	}
}
