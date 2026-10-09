package hugrgate

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func okBody() map[string]any {
	return map[string]any{
		"value": "a", "probability": 1.0,
		"distribution":    map[string]any{"a": 1.0},
		"uncertainty":     0.0,
		"accepted":        true,
		"backend":         "stub",
		"model":           "stub-1",
		"latency_ms":      0.1,
		"calibration_profile": "none",
		"fallback_used":       false,
		"metadata":            map[string]any{},
	}
}

func errBody(code string, recoverable bool) map[string]any {
	return map[string]any{
		"error": map[string]any{
			"code": code, "message": code + " happened",
			"recoverable": recoverable, "details": map[string]any{},
		},
	}
}

// scriptedServer plays a script of responses and records requests.
type scriptedServer struct {
	t        *testing.T
	script   []scriptedResp
	requests []recordedReq
}

type scriptedResp struct {
	status int
	body   any
}

type recordedReq struct {
	path string
	body map[string]any
	ua   string
}

func (s *scriptedServer) handler(w http.ResponseWriter, r *http.Request) {
	var body map[string]any
	_ = json.NewDecoder(r.Body).Decode(&body)
	s.requests = append(s.requests, recordedReq{
		path: r.URL.Path, body: body,
		ua:   r.Header.Get("User-Agent"),
	})
	if len(s.script) == 0 {
		s.t.Fatal("no scripted response left")
	}
	next := s.script[0]
	s.script = s.script[1:]
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(next.status)
	_ = json.NewEncoder(w).Encode(next.body)
}

func newScripted(t *testing.T, script ...scriptedResp) (*Client, *scriptedServer) {
	s := &scriptedServer{t: t, script: script}
	srv := httptest.NewServer(http.HandlerFunc(s.handler))
	t.Cleanup(srv.Close)
	client, err := NewClientWithOptions(srv.URL, Options{
		Timeout: 2 * time.Second, MaxRetries: 3, RetryBackoff: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	return client, s
}

func TestProtocolVersionSent(t *testing.T) {
	client, s := newScripted(t, scriptedResp{200, okBody()})
	_, err := client.Decide(context.Background(), map[string]any{"f": 1.0},
		DecisionSpec{Type: "categorical", Options: []string{"a", "b"}}, nil, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(s.requests) != 1 || s.requests[0].path != "/decide" {
		t.Fatalf("unexpected requests: %+v", s.requests)
	}
	if s.requests[0].body["protocol_version"] != ProtocolVersion {
		t.Fatalf("missing protocol_version: %+v", s.requests[0].body)
	}
	if s.requests[0].ua != "hugrgate-sdk-go/"+SDKVersion {
		t.Fatalf("bad user-agent: %q", s.requests[0].ua)
	}
}

func TestDecideStampsMetadata(t *testing.T) {
	client, _ := newScripted(t, scriptedResp{200, okBody()})
	result, err := client.Decide(context.Background(), map[string]any{},
		DecisionSpec{Type: "categorical", Options: []string{"a", "b"}}, nil, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if result.Value != "a" {
		t.Fatalf("bad value: %v", result.Value)
	}
	if result.Metadata["sdk_version"] != SDKVersion {
		t.Fatalf("missing sdk_version: %+v", result.Metadata)
	}
}

func TestAbstention(t *testing.T) {
	client, _ := newScripted(t, scriptedResp{200, map[string]any{
		"abstained": true, "reason": "below_threshold", "message": "low",
	}})
	_, err := client.Decide(context.Background(), map[string]any{},
		DecisionSpec{}, nil, nil, nil)
	abs, ok := err.(*Abstention)
	if !ok {
		t.Fatalf("expected *Abstention, got %T (%v)", err, err)
	}
	if abs.Reason != "below_threshold" {
		t.Fatalf("bad reason: %q", abs.Reason)
	}
}

func TestNoRetryOnCallerBug(t *testing.T) {
	client, s := newScripted(t,
		scriptedResp{422, errBody("spec_error", false)})
	_, err := client.Decide(context.Background(), map[string]any{},
		DecisionSpec{}, nil, nil, nil)
	hgErr, ok := err.(*Error)
	if !ok || hgErr.Code != "spec_error" {
		t.Fatalf("expected spec_error, got %T (%v)", err, err)
	}
	if hgErr.Recoverable {
		t.Fatal("spec_error must not be recoverable")
	}
	if len(s.requests) != 1 {
		t.Fatalf("caller bugs must not be retried: %d requests", len(s.requests))
	}
}

func TestRetry503ThenSucceeds(t *testing.T) {
	client, s := newScripted(t,
		scriptedResp{503, errBody("backend_unavailable", true)},
		scriptedResp{200, okBody()})
	result, err := client.Decide(context.Background(), map[string]any{},
		DecisionSpec{}, nil, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if result.Value != "a" {
		t.Fatalf("bad value: %v", result.Value)
	}
	if len(s.requests) != 2 {
		t.Fatalf("expected 2 requests, got %d", len(s.requests))
	}
}

func TestNegativeMaxRetriesRejected(t *testing.T) {
	if _, err := NewClientWithOptions("http://x", Options{MaxRetries: -1}); err == nil {
		t.Fatal("expected error for negative MaxRetries")
	}
}

func TestBatchReportsPerItemErrors(t *testing.T) {
	client, _ := newScripted(t,
		scriptedResp{200, okBody()},
		scriptedResp{422, errBody("spec_error", false)})
	outcomes := client.DecideBatch(context.Background(),
		[]map[string]any{{"f": 1.0}, {"f": 2.0}},
		DecisionSpec{}, nil, nil)
	if len(outcomes) != 2 {
		t.Fatalf("expected 2 outcomes, got %d", len(outcomes))
	}
	if outcomes[0].Err != nil || outcomes[0].Result.Value != "a" {
		t.Fatalf("bad first outcome: %+v", outcomes[0])
	}
	if outcomes[1].Err == nil {
		t.Fatal("expected error on second outcome")
	}
}

func TestDecideValue(t *testing.T) {
	client, _ := newScripted(t, scriptedResp{200, okBody()})
	value, err := client.DecideValue(context.Background(), map[string]any{},
		DecisionSpec{}, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if value != "a" {
		t.Fatalf("bad value: %v", value)
	}
}

func TestHealthNeverFails(t *testing.T) {
	client, err := NewClientWithOptions("http://127.0.0.1:1",
		Options{Timeout: 50 * time.Millisecond, MaxRetries: 0})
	if err != nil {
		t.Fatal(err)
	}
	h := client.Health(context.Background())
	if h["reachable"] != false {
		t.Fatalf("expected unreachable, got %+v", h)
	}
}

func TestProtocolAdvertisement(t *testing.T) {
	client, _ := newScripted(t, scriptedResp{200, map[string]any{
		"protocol_version": "1.0",
		"supported_versions": []string{"1.0"},
		"service_version":  "0.1.0",
	}})
	info, err := client.Protocol(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if info.ProtocolVersion != "1.0" {
		t.Fatalf("bad protocol version: %+v", info)
	}
}

func TestBackends(t *testing.T) {
	client, _ := newScripted(t, scriptedResp{200, []map[string]any{
		{"name": "uniform", "is_remote": false, "capabilities": map[string]any{}},
	}})
	infos, err := client.Backends(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(infos) != 1 || infos[0].Name != "uniform" {
		t.Fatalf("bad backends: %+v", infos)
	}
}

func TestErrorString(t *testing.T) {
	e := &Error{Code: "spec_error", Message: "bad"}
	if !strings.Contains(e.Error(), "[spec_error]") {
		t.Fatalf("bad error string: %q", e.Error())
	}
}
