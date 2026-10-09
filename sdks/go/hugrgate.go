// Package hugrgate is the Go SDK for the HugrGate decision service
// (protocol v1). Slice 431.
//
// A net/http client with versioned requests, taxonomy error mapping,
// exponential-backoff retry on recoverable faults, and batch
// decisions:
//
//	client, err := hugrgate.NewClient("http://127.0.0.1:8377")
//	if err != nil { log.Fatal(err) }
//	result, err := client.Decide(ctx,
//		map[string]any{"signal": 0.7},
//		hugrgate.DecisionSpec{
//			Type:    "categorical",
//			Options: []string{"a", "b"},
//		}, nil)
//	fmt.Println(result.Value)
package hugrgate

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// ProtocolVersion is sent on every /decide request.
const ProtocolVersion = "1.0"

// SDKVersion is sent in the User-Agent header.
const SDKVersion = "2.0"

// DecisionSpec mirrors hugrgate.spec JSON.
type DecisionSpec struct {
	Type     string         `json:"type,omitempty"`
	Options  []string       `json:"options,omitempty"`
	Statement string        `json:"statement,omitempty"`
	Levels   []string       `json:"levels,omitempty"`
	Minimum  *float64       `json:"minimum,omitempty"`
	Maximum  *float64       `json:"maximum,omitempty"`
	Labels   []string       `json:"labels,omitempty"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

// DecisionResult mirrors hugrgate.result JSON.
type DecisionResult struct {
	Value               any              `json:"value"`
	Probability         float64          `json:"probability"`
	Distribution        map[string]float64 `json:"distribution"`
	Uncertainty         float64          `json:"uncertainty"`
	Accepted            bool             `json:"accepted"`
	Backend             string           `json:"backend"`
	Model               string           `json:"model"`
	LatencyMs           float64          `json:"latency_ms"`
	CalibrationProfile  string           `json:"calibration_profile"`
	FallbackUsed        bool             `json:"fallback_used"`
	Metadata            map[string]any   `json:"metadata"`
}

// BackendInfo mirrors GET /backends entries.
type BackendInfo struct {
	Name         string         `json:"name"`
	IsRemote     bool           `json:"is_remote"`
	Capabilities map[string]any `json:"capabilities"`
}

// ProtocolInfo mirrors GET /protocol.
type ProtocolInfo struct {
	ProtocolVersion   string   `json:"protocol_version"`
	SupportedVersions []string `json:"supported_versions"`
	ServiceVersion    string   `json:"service_version"`
}

// errorEnvelope is the wire error body:
// { "error": { "code", "message", "recoverable", "details" } }.
type errorEnvelope struct {
	Code        string         `json:"code"`
	Message     string         `json:"message"`
	Recoverable bool           `json:"recoverable"`
	Details     map[string]any `json:"details"`
}

// Error is a HugrGate taxonomy error.
type Error struct {
	Code        string
	Message     string
	Recoverable bool
	Details     map[string]any
}

func (e *Error) Error() string {
	return fmt.Sprintf("[%s] %s", e.Code, e.Message)
}

// Abstention is raised when the service abstains instead of deciding.
type Abstention struct {
	Message string
	Reason  string
}

func (e *Abstention) Error() string {
	return fmt.Sprintf("[abstention:%s] %s", e.Reason, e.Message)
}

// SDKError is raised when the transport fails after retries.
type SDKError struct {
	Message string
}

func (e *SDKError) Error() string { return "[sdk_error] " + e.Message }

// Options configures a Client.
type Options struct {
	// Timeout per request. Defaults to 10s.
	Timeout time.Duration
	// MaxRetries beyond the first attempt on recoverable faults.
	MaxRetries int
	// RetryBackoff base; actual wait is backoff * 2^attempt.
	RetryBackoff time.Duration
}

func defaultOptions() Options {
	return Options{
		Timeout:      10 * time.Second,
		MaxRetries:   3,
		RetryBackoff: 100 * time.Millisecond,
	}
}

// Client is a HugrGate service client (protocol v1).
//
// Recoverable failures (transport errors, HTTP 502/503/504) are
// retried with exponential backoff; caller bugs (e.g. spec_error)
// are returned immediately as *Error.
type Client struct {
	url        string
	http       *http.Client
	maxRetries int
	backoff    time.Duration
}

// NewClient builds a Client with default options.
func NewClient(url string) (*Client, error) {
	return NewClientWithOptions(url, defaultOptions())
}

// NewClientWithOptions builds a Client with explicit options.
func NewClientWithOptions(url string, opts Options) (*Client, error) {
	if opts.MaxRetries < 0 {
		return nil, fmt.Errorf("hugrgate: MaxRetries must be >= 0")
	}
	if opts.Timeout <= 0 {
		opts.Timeout = 10 * time.Second
	}
	return &Client{
		url:        strings.TrimRight(url, "/"),
		http:       &http.Client{Timeout: opts.Timeout},
		maxRetries: opts.MaxRetries,
		backoff:    opts.RetryBackoff,
	}, nil
}

var retryableStatus = map[int]bool{502: true, 503: true, 504: true}

// doPost posts JSON with retry on recoverable faults.
func (c *Client) doPost(ctx context.Context, path string,
	payload any) (*http.Response, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, &Error{Code: "sdk_error",
			Message: fmt.Sprintf("cannot encode request: %v", err)}
	}
	var lastErr error
	for attempt := 0; ; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost,
			c.url+path, bytes.NewReader(body))
		if err != nil {
			return nil, &Error{Code: "sdk_error",
				Message: fmt.Sprintf("cannot build request: %v", err)}
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("User-Agent", "hugrgate-sdk-go/"+SDKVersion)
		resp, err := c.http.Do(req)
		if err != nil {
			// Transport-level failure: retry, then give up.
			lastErr = err
			if attempt >= c.maxRetries {
				return nil, &SDKError{Message:
					fmt.Sprintf("hugrgate service unreachable: %v", err)}
			}
			c.sleep(attempt)
			continue
		}
		if retryableStatus[resp.StatusCode] && attempt < c.maxRetries {
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			c.sleep(attempt)
			continue
		}
		return resp, nil
	}
}

func (c *Client) sleep(attempt int) {
	if c.backoff > 0 {
		time.Sleep(c.backoff * time.Duration(1<<attempt))
	}
}

// mapError converts an HTTP error response onto the taxonomy.
func mapError(resp *http.Response) error {
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	var wrapped struct {
		Err errorEnvelope `json:"error"`
	}
	if json.Unmarshal(raw, &wrapped) == nil && wrapped.Err.Code != "" {
		return &Error{
			Code:        wrapped.Err.Code,
			Message:     wrapped.Err.Message,
			Recoverable: wrapped.Err.Recoverable,
			Details:     wrapped.Err.Details,
		}
	}
	switch resp.StatusCode {
	case http.StatusUnprocessableEntity:
		return &Error{Code: "spec_error",
			Message: "service rejected request (HTTP 422)"}
	case http.StatusServiceUnavailable:
		return &Error{Code: "backend_unavailable",
			Message:     "service unavailable (HTTP 503)",
			Recoverable: true}
	default:
		return &Error{Code: "backend_error",
			Message:     fmt.Sprintf("service error (HTTP %d)", resp.StatusCode),
			Recoverable: true}
	}
}

type decideRequest struct {
	ProtocolVersion string         `json:"protocol_version"`
	Spec            DecisionSpec   `json:"spec"`
	State           map[string]any `json:"state"`
	BackendName     *string        `json:"backend_name"`
	Context         map[string]any `json:"context"`
	Policy          any            `json:"policy,omitempty"`
}

// Decide makes one decision via the service.
func (c *Client) Decide(ctx context.Context, state map[string]any,
	spec DecisionSpec, policy any, backendName *string,
	context map[string]any) (*DecisionResult, error) {
	resp, err := c.doPost(ctx, "/decide", decideRequest{
		ProtocolVersion: ProtocolVersion,
		Spec:            spec,
		State:           state,
		BackendName:     backendName,
		Context:         context,
		Policy:          policy,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, mapError(resp)
	}
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, &SDKError{Message:
			fmt.Sprintf("cannot decode response: %v", err)}
	}
	if abstained, _ := body["abstained"].(bool); abstained {
		message, _ := body["message"].(string)
		if message == "" {
			message = "service abstained"
		}
		reason, _ := body["reason"].(string)
		if reason == "" {
			reason = "below_threshold"
		}
		return nil, &Abstention{Message: message, Reason: reason}
	}
	decision, _ := body["decision"].(map[string]any)
	if decision == nil {
		decision = body
	}
	if _, ok := decision["value"]; !ok {
		return nil, &SDKError{Message:
			fmt.Sprintf("service returned no decision: %v", body)}
	}
	raw, _ := json.Marshal(decision)
	var result DecisionResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, &SDKError{Message:
			fmt.Sprintf("cannot decode decision: %v", err)}
	}
	if result.Metadata == nil {
		result.Metadata = map[string]any{}
	}
	result.Metadata["client_transport"] = "http"
	result.Metadata["sdk_version"] = SDKVersion
	return &result, nil
}

// BatchOutcome is one item of a DecideBatch report.
type BatchOutcome struct {
	Result *DecisionResult
	Err    error
}

// DecideBatch decides one spec over many states. Per-item errors are
// reported in place, never raised: a batch is a report.
func (c *Client) DecideBatch(ctx context.Context,
	states []map[string]any, spec DecisionSpec, policy any,
	backendName *string) []BatchOutcome {
	outcomes := make([]BatchOutcome, 0, len(states))
	for _, state := range states {
		result, err := c.Decide(ctx, state, spec, policy, backendName, nil)
		outcomes = append(outcomes, BatchOutcome{Result: result, Err: err})
	}
	return outcomes
}

// DecideValue is a convenience returning just the decided value.
func (c *Client) DecideValue(ctx context.Context, state map[string]any,
	spec DecisionSpec, policy any,
	backendName *string) (any, error) {
	result, err := c.Decide(ctx, state, spec, policy, backendName, nil)
	if err != nil {
		return nil, err
	}
	return result.Value, nil
}

func (c *Client) getJSON(ctx context.Context, path string,
	target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		c.url+path, nil)
	if err != nil {
		return &SDKError{Message: fmt.Sprintf("cannot build request: %v", err)}
	}
	req.Header.Set("User-Agent", "hugrgate-sdk-go/"+SDKVersion)
	resp, err := c.http.Do(req)
	if err != nil {
		return &SDKError{Message:
			fmt.Sprintf("hugrgate service unreachable: %v", err)}
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return mapError(resp)
	}
	return json.NewDecoder(resp.Body).Decode(target)
}

// Health is a liveness probe. It never fails on transport: it reports
// reachability.
func (c *Client) Health(ctx context.Context) map[string]any {
	var body map[string]any
	if err := c.getJSON(ctx, "/health", &body); err != nil {
		return map[string]any{"reachable": false, "error": err.Error()}
	}
	body["reachable"] = true
	return body
}

// Backends lists backends known to the service.
func (c *Client) Backends(ctx context.Context) ([]BackendInfo, error) {
	var infos []BackendInfo
	if err := c.getJSON(ctx, "/backends", &infos); err != nil {
		return nil, err
	}
	return infos, nil
}

// Protocol fetches the service's protocol advertisement.
func (c *Client) Protocol(ctx context.Context) (*ProtocolInfo, error) {
	var info ProtocolInfo
	if err := c.getJSON(ctx, "/protocol", &info); err != nil {
		return nil, err
	}
	return &info, nil
}

// Close releases resources (kept for API symmetry; net/http needs none).
func (c *Client) Close() {}
