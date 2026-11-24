// MarkeTOB offline rebuild probe. Apache-2.0, see repository LICENSE/NOTICE.
// This disposable client uses the existing Go toolchain's standard library.
package main

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

func client(roots *x509.CertPool) *http.Client {
	return &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{
		TLSClientConfig:   &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
		ForceAttemptHTTP2: true,
	}}
}

func check(ca string) error {
	raw, err := os.ReadFile(ca)
	if err != nil {
		return err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(raw) {
		return fmt.Errorf("missing test CA")
	}
	trusted := client(roots)
	defer trusted.CloseIdleConnections()
	response, err := trusted.Get("https://localhost:8443/rebuild")
	if err != nil {
		return err
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 100))
	response.Body.Close()
	if err != nil {
		return err
	}
	if response.StatusCode != 200 || response.ProtoMajor != 2 || string(body) != "offline-rebuild-ok" {
		return fmt.Errorf("unexpected HTTPS/HTTP2 response")
	}
	untrusted := client(x509.NewCertPool())
	defer untrusted.CloseIdleConnections()
	unexpected, err := untrusted.Get("https://localhost:8443/rebuild")
	if unexpected != nil {
		unexpected.Body.Close()
	}
	var authority x509.UnknownAuthorityError
	if !errors.As(err, &authority) {
		return fmt.Errorf("expected untrusted CA rejection: %v", err)
	}
	unexpected, err = trusted.Get("https://127.0.0.1:8443/rebuild")
	if unexpected != nil {
		unexpected.Body.Close()
	}
	var hostname x509.HostnameError
	if !errors.As(err, &hostname) {
		return fmt.Errorf("expected hostname rejection: %v", err)
	}
	return nil
}

func main() {
	if len(os.Args) != 2 {
		panic("expected disposable CA path")
	}
	var last error
	for deadline := time.Now().Add(20 * time.Second); time.Now().Before(deadline); {
		last = check(os.Args[1])
		if last == nil {
			json.NewEncoder(os.Stdout).Encode(map[string]any{
				"result": "PASS", "https": true, "http2": true,
				"untrusted_ca_rejected": true, "wrong_hostname_rejected": true,
			})
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	fmt.Fprintln(os.Stderr, last)
	os.Exit(1)
}
