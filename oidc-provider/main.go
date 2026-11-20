// A deployment-owned TLS bridge for Grafana's server-side OAuth requests.
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func providerHandler(authority, address string, ca []byte) (http.Handler, error) {
	return providerHandlerWithSystemRoots(authority, address, ca, x509.SystemCertPool)
}

func providerHandlerWithSystemRoots(authority, address string, ca []byte,
	systemRoots func() (*x509.CertPool, error)) (http.Handler, error) {
	target, err := url.Parse("https://" + authority)
	if err != nil || target.Hostname() == "" || target.User != nil || target.Path != "" ||
		target.RawQuery != "" || target.Fragment != "" {
		return nil, errors.New("invalid provider authority")
	}
	if _, _, err := net.SplitHostPort(address); err != nil {
		return nil, errors.New("invalid internal upstream address")
	}
	roots, err := upstreamRoots(ca, systemRoots)
	if err != nil {
		return nil, err
	}
	transport := &http.Transport{
		// Ignore proxy environment variables; this hop always stays internal.
		Proxy: nil,
		DialContext: func(ctx context.Context, network, _ string) (net.Conn, error) {
			return (&net.Dialer{Timeout: 5 * time.Second}).DialContext(ctx, network, address)
		},
		TLSClientConfig:   &tls.Config{RootCAs: roots, ServerName: target.Hostname(), MinVersion: tls.VersionTLS12},
		ForceAttemptHTTP2: true, TLSHandshakeTimeout: 5 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second, IdleConnTimeout: 60 * time.Second,
	}
	proxy := &httputil.ReverseProxy{
		Transport: transport,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.Out.Host = target.Host
			// Only forward OAuth inputs, never caller-selected tenant/instance headers.
			r.Out.Header = http.Header{}
			for _, name := range []string{"Authorization", "Content-Type"} {
				r.Out.Header.Set(name, r.In.Header.Get(name))
			}
			r.Out.Header.Set("X-Forwarded-Proto", "https")
		},
		ModifyResponse: func(r *http.Response) error {
			if r.StatusCode >= 300 && r.StatusCode < 400 {
				return errors.New("provider redirects are not permitted")
			}
			r.Header.Del("Cache-Control")
			r.Header.Del("Set-Cookie")
			return nil
		},
		ErrorLog: log.New(io.Discard, "", 0),
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			http.Error(w, "provider unavailable", http.StatusBadGateway)
		},
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		if r.URL.RawQuery != "" {
			http.Error(w, "query parameters are not permitted", http.StatusBadRequest)
			return
		}
		switch r.URL.Path {
		case "/ready":
			ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
			defer cancel()
			conn, err := (&tls.Dialer{NetDialer: &net.Dialer{Timeout: 5 * time.Second},
				Config: transport.TLSClientConfig}).DialContext(ctx, "tcp", address)
			if err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			conn.Close()
			w.WriteHeader(http.StatusOK)
			return
		case "/oauth/v2/token":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
		case "/oidc/v1/userinfo":
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
		default:
			w.WriteHeader(http.StatusNotFound)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 35*time.Second)
		defer cancel()
		r.Body = http.MaxBytesReader(w, r.Body, 16*1024)
		proxy.ServeHTTP(w, r.WithContext(ctx))
	}), nil
}

func upstreamRoots(ca []byte, systemRoots func() (*x509.CertPool, error)) (*x509.CertPool, error) {
	if len(ca) == 0 {
		// Uploaded public certificates need no extra trust anchor. Never skip
		// verification: Go still validates the issuer and canonical hostname.
		roots, err := systemRoots()
		if err != nil {
			return nil, errors.New("system certificate roots are unavailable")
		}
		return roots, nil
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return nil, errors.New("invalid upstream CA")
	}
	return roots, nil
}

func loadUpstreamCA(path string) ([]byte, error) {
	ca, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	return ca, err
}

func main() {
	ca, err := loadUpstreamCA("/run/upstream-ca/ca.crt")
	if err != nil {
		log.Fatal("provider upstream trust is unavailable")
	}
	handler, err := providerHandler(os.Getenv("ZITADEL_AUTHORITY"), os.Getenv("ZITADEL_ADDRESS"), ca)
	if err != nil {
		// Validation errors contain no certificate data or credentials.
		log.Fatalf("provider configuration is invalid: %v", err)
	}
	server := &http.Server{Addr: ":8443", Handler: handler,
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second,
		WriteTimeout: 40 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 8192,
		TLSConfig: &tls.Config{MinVersion: tls.VersionTLS12}, ErrorLog: log.New(io.Discard, "", 0)}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()
	shutdownDone := make(chan struct{})
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
		defer cancel()
		server.Shutdown(shutdownCtx)
		close(shutdownDone)
	}()
	if err := server.ListenAndServeTLS("/run/provider-tls/tls.crt", "/run/provider-tls/tls.key"); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal("provider listener stopped")
	}
	<-shutdownDone
}
