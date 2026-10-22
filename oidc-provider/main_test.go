package main

import (
	"crypto/x509"
	"encoding/pem"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProviderKeepsPublicAuthorityOverInternalTLS(t *testing.T) {
	for _, authority := range []string{"example.com", "127.0.0.1:3443"} {
		t.Run(authority, func(t *testing.T) {
			calls := 0
			upstream := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls++
				if r.Host != authority || r.Header.Get("X-Forwarded-Proto") != "https" {
					t.Errorf("incorrect public authority or scheme")
				}
				if r.Header.Get("Cookie") != "" || r.Header.Get("X-Zitadel-Instance-Host") != "" {
					t.Error("forwarded caller-controlled instance or cookie")
				}
				if r.ProtoMajor != 2 {
					t.Error("expected HTTP/2 upstream")
				}
				if r.URL.Path == "/oauth/v2/token" {
					body, err := io.ReadAll(r.Body)
					if err != nil || string(body) != "code=fixture&code_verifier=pkce" {
						t.Error("token body was not preserved")
					}
				} else if r.Header.Get("Authorization") != "Bearer disposable-token" {
					t.Error("userinfo bearer was not preserved")
				}
				w.Header().Set("Set-Cookie", "must-not-forward")
				w.WriteHeader(http.StatusOK)
			}))
			upstream.EnableHTTP2 = true
			upstream.StartTLS()
			defer upstream.Close()
			handler, err := providerHandler(authority, upstream.Listener.Addr().String(),
				pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: upstream.Certificate().Raw}))
			if err != nil {
				t.Fatal(err)
			}
			for _, path := range []string{"/oauth/v2/token", "/oidc/v1/userinfo"} {
				method := http.MethodGet
				if path == "/oauth/v2/token" {
					method = http.MethodPost
				}
				req := httptest.NewRequest(method, path, strings.NewReader("code=fixture&code_verifier=pkce"))
				req.Header.Set("Authorization", "Bearer disposable-token")
				req.Header.Set("Cookie", "caller-cookie")
				req.Header.Set("X-Zitadel-Instance-Host", "another-tenant")
				result := httptest.NewRecorder()
				handler.ServeHTTP(result, req)
				if result.Code != http.StatusOK || result.Header().Get("Cache-Control") != "no-store" ||
					result.Header().Get("Set-Cookie") != "" {
					t.Fatalf("unexpected proxy response: %d", result.Code)
				}
			}
			if calls != 2 {
				t.Fatalf("unexpected repeat requests: %d", calls)
			}
			ready := httptest.NewRecorder()
			handler.ServeHTTP(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
			if ready.Code != http.StatusOK || calls != 2 {
				t.Fatal("TLS readiness must not issue another OAuth request")
			}
		})
	}
}

func TestProviderRejectsMismatchedUpstreamIdentity(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("invalid upstream identity was accepted")
	}))
	defer upstream.Close()
	for _, authority := range []string{"wrong.invalid", "192.0.2.10:3443"} {
		handler, err := providerHandler(authority, upstream.Listener.Addr().String(),
			pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: upstream.Certificate().Raw}))
		if err != nil {
			t.Fatal(err)
		}
		result := httptest.NewRecorder()
		handler.ServeHTTP(result, httptest.NewRequest(http.MethodGet, "/oidc/v1/userinfo", nil))
		if result.Code != http.StatusBadGateway {
			t.Fatalf("wrong certificate accepted: %d", result.Code)
		}
		ready := httptest.NewRecorder()
		handler.ServeHTTP(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
		if ready.Code != http.StatusServiceUnavailable {
			t.Fatal("incorrect TLS identity must keep provider unready")
		}
	}
}

func TestProviderEmptyCAUsesSystemRootsWithoutSkippingVerification(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("untrusted upstream was reached")
	}))
	defer upstream.Close()
	handler, err := providerHandler("example.com", upstream.Listener.Addr().String(), nil)
	if err != nil {
		t.Fatal(err)
	}
	result := httptest.NewRecorder()
	handler.ServeHTTP(result, httptest.NewRequest(http.MethodGet, "/oidc/v1/userinfo", nil))
	if result.Code != http.StatusBadGateway {
		t.Fatalf("untrusted upstream returned %d, want 502", result.Code)
	}
	ready := httptest.NewRecorder()
	handler.ServeHTTP(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if ready.Code != http.StatusServiceUnavailable {
		t.Fatalf("untrusted upstream readiness returned %d, want 503", ready.Code)
	}
}

func TestProviderEmptyCAAcceptsTrustedSystemRoot(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()
	loaded := false
	handler, err := providerHandlerWithSystemRoots("example.com", upstream.Listener.Addr().String(), nil,
		func() (*x509.CertPool, error) {
			loaded = true
			pool := x509.NewCertPool()
			pool.AddCert(upstream.Certificate())
			return pool, nil
		})
	if err != nil || !loaded {
		t.Fatalf("system roots not loaded: %v", err)
	}
	ready := httptest.NewRecorder()
	handler.ServeHTTP(ready, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if ready.Code != http.StatusOK {
		t.Fatalf("trusted upstream readiness returned %d, want 200", ready.Code)
	}
	result := httptest.NewRecorder()
	handler.ServeHTTP(result, httptest.NewRequest(http.MethodGet, "/oidc/v1/userinfo", nil))
	if result.Code != http.StatusOK {
		t.Fatalf("trusted upstream returned %d, want 200", result.Code)
	}
}

func TestProviderEmptyCAFailsClosedWithoutSystemRoots(t *testing.T) {
	_, err := providerHandlerWithSystemRoots("example.com", "127.0.0.1:8080", nil,
		func() (*x509.CertPool, error) { return nil, errors.New("roots unavailable") })
	if err == nil || err.Error() != "system certificate roots are unavailable" {
		t.Fatalf("missing system roots should fail closed: %v", err)
	}
}

func TestProviderRejectsMalformedNonemptyCA(t *testing.T) {
	if _, err := providerHandler("example.com", "127.0.0.1:8080", []byte("not a PEM certificate")); err == nil || err.Error() != "invalid upstream CA" {
		t.Fatalf("malformed CA should fail closed: %v", err)
	}
}

func TestProviderTrustBundleCanBeAbsentButNotUnreadable(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ca.crt")
	ca, err := loadUpstreamCA(path)
	if err != nil || ca != nil {
		t.Fatalf("missing optional CA returned %q, %v", ca, err)
	}
	if err := os.Mkdir(path, 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := loadUpstreamCA(path); err == nil {
		t.Fatal("unreadable CA path must not fall back to system roots")
	}
}

func TestProviderRejectsRedirectsAndUnrelatedRoutes(t *testing.T) {
	calls := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls++
		w.Header().Set("Location", "https://unreachable.invalid/")
		w.WriteHeader(http.StatusFound)
	}))
	defer upstream.Close()
	handler, err := providerHandler("127.0.0.1:3443", upstream.Listener.Addr().String(),
		pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: upstream.Certificate().Raw}))
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		method, path string
		status       int
	}{
		{http.MethodGet, "/oidc/v1/userinfo", http.StatusBadGateway},
		{http.MethodPost, "/api/v1/auth/users", http.StatusNotFound},
		{http.MethodGet, "/oauth/v2/token", http.StatusMethodNotAllowed},
		{http.MethodPost, "/oidc/v1/userinfo", http.StatusMethodNotAllowed},
		{http.MethodGet, "/oidc/v1/userinfo?access_token=fixture", http.StatusBadRequest},
	} {
		result := httptest.NewRecorder()
		handler.ServeHTTP(result, httptest.NewRequest(test.method, test.path, nil))
		if result.Code != test.status {
			t.Fatalf("%s returned %d, want %d", test.path, result.Code, test.status)
		}
	}
	if calls != 1 {
		t.Fatalf("redirect or forbidden route forwarded: %d", calls)
	}
}
