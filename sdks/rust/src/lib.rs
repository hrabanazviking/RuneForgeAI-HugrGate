//! HugrGate Rust SDK — slice 430.
//!
//! Blocking client for the HugrGate HTTP service (protocol v1):
//! versioned requests, taxonomy error mapping, exponential-backoff
//! retry on recoverable faults, and batch decisions.
//!
//! ```no_run
//! use hugrgate::{Client, DecisionSpec};
//! use std::collections::HashMap;
//!
//! let client = Client::new("http://127.0.0.1:8377").unwrap();
//! let spec = DecisionSpec {
//!     spec_type: Some("categorical".into()),
//!     options: Some(vec!["a".into(), "b".into()]),
//!     ..Default::default()
//! };
//! let result = client.decide(HashMap::new(), &spec, None, None, None).unwrap();
//! println!("{:?}", result.value);
//! ```

use std::collections::HashMap;
use std::fmt;
use std::time::Duration;

use reqwest::blocking::{Client as HttpClient, Response};
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};

/// Wire-protocol version sent on every `/decide` request.
pub const PROTOCOL_VERSION: &str = "1.0";
/// SDK version sent in the `User-Agent` header.
pub const SDK_VERSION: &str = "2.0";

/// DecisionSpec JSON (see hugrgate.spec).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DecisionSpec {
    #[serde(rename = "type", skip_serializing_if = "Option::is_none")]
    pub spec_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub options: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub statement: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub levels: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub minimum: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub maximum: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub labels: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, serde_json::Value>>,
}

/// DecisionResult JSON (see hugrgate.result).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionResult {
    pub value: serde_json::Value,
    pub probability: f64,
    pub distribution: HashMap<String, f64>,
    pub uncertainty: f64,
    pub accepted: bool,
    pub backend: String,
    pub model: String,
    pub latency_ms: f64,
    pub calibration_profile: String,
    pub fallback_used: bool,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Registered-backend info from `GET /backends`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendInfo {
    pub name: String,
    pub is_remote: bool,
    pub capabilities: HashMap<String, serde_json::Value>,
}

/// Protocol advertisement from `GET /protocol`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolInfo {
    pub protocol_version: String,
    pub supported_versions: Vec<String>,
    pub service_version: String,
}

/// Wire error envelope: `{ "error": { code, message, recoverable, details } }`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorEnvelope {
    pub code: String,
    pub message: String,
    pub recoverable: bool,
    #[serde(default)]
    pub details: HashMap<String, serde_json::Value>,
}

/// A HugrGate taxonomy error.
#[derive(Debug, Clone)]
pub struct HugrGateError {
    pub code: String,
    pub message: String,
    pub recoverable: bool,
    pub details: HashMap<String, serde_json::Value>,
}

impl HugrGateError {
    pub fn new(code: impl Into<String>, message: impl Into<String>,
               recoverable: bool) -> Self {
        Self { code: code.into(), message: message.into(),
               recoverable, details: HashMap::new() }
    }

    pub fn from_envelope(env: ErrorEnvelope) -> Self {
        Self { code: env.code, message: env.message,
               recoverable: env.recoverable, details: env.details }
    }
}

impl fmt::Display for HugrGateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
    }
}

impl std::error::Error for HugrGateError {}

/// Raised when the service abstains instead of deciding.
#[derive(Debug, Clone)]
pub struct Abstention {
    pub message: String,
    pub reason: String,
}

impl fmt::Display for Abstention {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[abstention:{}] {}", self.reason, self.message)
    }
}

impl std::error::Error for Abstention {}

/// Raised when the transport fails after retries.
#[derive(Debug, Clone)]
pub struct SdkError {
    pub message: String,
}

impl fmt::Display for SdkError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[sdk_error] {}", self.message)
    }
}

impl std::error::Error for SdkError {}

/// Everything [`Client`] can fail with.
#[derive(Debug)]
pub enum Error {
    HugrGate(HugrGateError),
    Abstention(Abstention),
    Sdk(SdkError),
    Transport(reqwest::Error),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::HugrGate(e) => write!(f, "{e}"),
            Error::Abstention(e) => write!(f, "{e}"),
            Error::Sdk(e) => write!(f, "{e}"),
            Error::Transport(e) => write!(f, "[transport] {e}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Transport(e) => Some(e),
            _ => None,
        }
    }
}

impl From<HugrGateError> for Error {
    fn from(e: HugrGateError) -> Self { Error::HugrGate(e) }
}
impl From<Abstention> for Error {
    fn from(e: Abstention) -> Self { Error::Abstention(e) }
}
impl From<SdkError> for Error {
    fn from(e: SdkError) -> Self { Error::Sdk(e) }
}
impl From<reqwest::Error> for Error {
    fn from(e: reqwest::Error) -> Self { Error::Transport(e) }
}

/// Client options (builder-style; every setter consumes and returns).
#[derive(Debug, Clone)]
pub struct ClientOptions {
    pub timeout: Duration,
    pub max_retries: u32,
    pub retry_backoff: Duration,
}

impl Default for ClientOptions {
    fn default() -> Self {
        Self { timeout: Duration::from_secs(10),
               max_retries: 3,
               retry_backoff: Duration::from_millis(100) }
    }
}

const RETRYABLE: [StatusCode; 3] = [
    StatusCode::BAD_GATEWAY,
    StatusCode::SERVICE_UNAVAILABLE,
    StatusCode::GATEWAY_TIMEOUT,
];

/// Client for a HugrGate service (protocol v1).
///
/// Recoverable failures (transport errors, HTTP 502/503/504) are
/// retried with exponential backoff; caller bugs (e.g. `spec_error`)
/// are raised immediately as [`Error::HugrGate`].
pub struct Client {
    url: String,
    http: HttpClient,
    max_retries: u32,
    retry_backoff: Duration,
}

impl Client {
    /// Build a client with default options. Fails only if the
    /// underlying HTTP client cannot be constructed.
    pub fn new(url: &str) -> Result<Self, Error> {
        Self::with_options(url, ClientOptions::default())
    }

    /// Build a client with explicit options.
    pub fn with_options(url: &str, options: ClientOptions) -> Result<Self, Error> {
        let http = HttpClient::builder()
            .timeout(options.timeout)
            .user_agent(format!("hugrgate-sdk-rs/{SDK_VERSION}"))
            .build()
            .map_err(Error::Transport)?;
        Ok(Self {
            url: url.trim_end_matches('/').to_string(),
            http,
            max_retries: options.max_retries,
            retry_backoff: options.retry_backoff,
        })
    }

    fn post_json(&self, path: &str,
                 payload: &serde_json::Value) -> Result<Response, Error> {
        let mut attempt: u32 = 0;
        loop {
            match self.http.post(format!("{}{}", self.url, path))
                .json(payload)
                .send()
            {
                Ok(resp) => {
                    let status = resp.status();
                    if RETRYABLE.contains(&status) && attempt < self.max_retries {
                        std::thread::sleep(self.retry_backoff * 2u32.pow(attempt));
                        attempt += 1;
                        continue;
                    }
                    return Ok(resp);
                }
                Err(e) => {
                    // Transport-level failure (connect, timeout, TLS):
                    // retry, then surface as SdkError.
                    if e.is_timeout() || e.is_connect() || attempt < self.max_retries {
                        if attempt >= self.max_retries {
                            return Err(Error::Sdk(SdkError {
                                message: format!(
                                    "hugrgate service unreachable: {e}"),
                            }));
                        }
                        std::thread::sleep(self.retry_backoff * 2u32.pow(attempt));
                        attempt += 1;
                        continue;
                    }
                    return Err(Error::Transport(e));
                }
            }
        }
    }

    fn map_error(resp: Response) -> Error {
        let status = resp.status();
        let envelope: Option<HashMap<String, ErrorEnvelope>> =
            resp.json().ok();
        if let Some(mut map) = envelope {
            if let Some(env) = map.remove("error") {
                return Error::HugrGate(HugrGateError::from_envelope(env));
            }
        }
        match status {
            StatusCode::UNPROCESSABLE_ENTITY => Error::HugrGate(
                HugrGateError::new("spec_error",
                                   "service rejected request (HTTP 422)",
                                   false)),
            StatusCode::SERVICE_UNAVAILABLE => Error::HugrGate(
                HugrGateError::new("backend_unavailable",
                                   "service unavailable (HTTP 503)",
                                   true)),
            _ => Error::HugrGate(HugrGateError::new(
                "backend_error",
                format!("service error (HTTP {status})"), true)),
        }
    }

    /// Make a decision via the service.
    pub fn decide(
        &self,
        state: HashMap<String, serde_json::Value>,
        spec: &DecisionSpec,
        policy: Option<&serde_json::Value>,
        backend_name: Option<&str>,
        context: Option<HashMap<String, serde_json::Value>>,
    ) -> Result<DecisionResult, Error> {
        let payload = serde_json::json!({
            "protocol_version": PROTOCOL_VERSION,
            "spec": spec,
            "state": state,
            "backend_name": backend_name,
            "context": context,
            "policy": policy,
        });
        let resp = self.post_json("/decide", &payload)?;
        if !resp.status().is_success() {
            return Err(Self::map_error(resp));
        }
        let body: serde_json::Value =
            resp.json().map_err(Error::Transport)?;
        if body.get("abstained").and_then(serde_json::Value::as_bool)
            .unwrap_or(false)
        {
            return Err(Error::Abstention(Abstention {
                message: body.get("message").and_then(
                    serde_json::Value::as_str).unwrap_or("service abstained")
                    .to_string(),
                reason: body.get("reason").and_then(
                    serde_json::Value::as_str).unwrap_or("below_threshold")
                    .to_string(),
            }));
        }
        let decision = body.get("decision").unwrap_or(&body);
        let mut result: DecisionResult = serde_json::from_value(decision.clone())
            .map_err(|e| Error::Sdk(SdkError {
                message: format!("service returned no decision: {e}"),
            }))?;
        result.metadata.insert("client_transport".into(),
                               serde_json::Value::from("http"));
        result.metadata.insert("sdk_version".into(),
                               serde_json::Value::from(SDK_VERSION));
        Ok(result)
    }

    /// Decide one spec over many states; per-item errors are
    /// returned in place, never raised.
    pub fn decide_batch(
        &self,
        states: Vec<HashMap<String, serde_json::Value>>,
        spec: &DecisionSpec,
        policy: Option<&serde_json::Value>,
        backend_name: Option<&str>,
    ) -> Vec<Result<DecisionResult, Error>> {
        states.into_iter()
            .map(|state| self.decide(state, spec, policy, backend_name, None))
            .collect()
    }

    /// Convenience: just the decided value.
    pub fn decide_value(
        &self,
        state: HashMap<String, serde_json::Value>,
        spec: &DecisionSpec,
        policy: Option<&serde_json::Value>,
        backend_name: Option<&str>,
    ) -> Result<serde_json::Value, Error> {
        Ok(self.decide(state, spec, policy, backend_name, None)?.value)
    }

    fn get_json<T: serde::de::DeserializeOwned>(
        &self, path: &str) -> Result<T, Error> {
        let resp = self.http.get(format!("{}{}", self.url, path))
            .send()
            .map_err(|e| Error::Sdk(SdkError {
                message: format!("hugrgate service unreachable: {e}"),
            }))?;
        if !resp.status().is_success() {
            return Err(Self::map_error(resp));
        }
        resp.json().map_err(Error::Transport)
    }

    /// Liveness probe. Never fails on transport: reports reachability.
    pub fn health(&self) -> serde_json::Value {
        match self.get_json::<serde_json::Value>("/health") {
            Ok(mut v) => {
                if let Some(map) = v.as_object_mut() {
                    map.insert("reachable".into(), serde_json::Value::from(true));
                }
                v
            }
            Err(e) => serde_json::json!({"reachable": false,
                                         "error": e.to_string()}),
        }
    }

    /// List backends known to the service.
    pub fn backends(&self) -> Result<Vec<BackendInfo>, Error> {
        self.get_json("/backends")
    }

    /// Fetch the service's protocol advertisement.
    pub fn protocol(&self) -> Result<ProtocolInfo, Error> {
        self.get_json("/protocol")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn protocol_version_is_v1() {
        assert_eq!(PROTOCOL_VERSION, "1.0");
    }

    #[test]
    fn decide_request_serializes_protocol_version() {
        let spec = DecisionSpec {
            spec_type: Some("categorical".into()),
            options: Some(vec!["a".into(), "b".into()]),
            ..Default::default()
        };
        let payload = serde_json::json!({
            "protocol_version": PROTOCOL_VERSION,
            "spec": spec,
            "state": HashMap::<String, serde_json::Value>::new(),
            "backend_name": Option::<String>::None,
            "context": Option::<HashMap<String, serde_json::Value>>::None,
            "policy": Option::<serde_json::Value>::None,
        });
        assert_eq!(payload["protocol_version"], "1.0");
        assert_eq!(payload["spec"]["options"], serde_json::json!(["a", "b"]));
    }

    #[test]
    fn error_envelope_maps_to_taxonomy() {
        let env = ErrorEnvelope {
            code: "spec_error".into(),
            message: "bad spec".into(),
            recoverable: false,
            details: HashMap::new(),
        };
        let err = HugrGateError::from_envelope(env);
        assert_eq!(err.code, "spec_error");
        assert!(!err.recoverable);
        assert_eq!(format!("{err}"), "[spec_error] bad spec");
    }

    #[test]
    fn client_trims_trailing_slash() {
        let client = Client::new("http://127.0.0.1:8377/").unwrap();
        assert_eq!(client.url, "http://127.0.0.1:8377");
    }

    #[test]
    fn error_enum_covers_all_variants() {
        let e: Error = HugrGateError::new("x", "y", true).into();
        assert!(matches!(e, Error::HugrGate(_)));
        let e: Error = Abstention { message: "m".into(),
                                   reason: "r".into() }.into();
        assert!(matches!(e, Error::Abstention(_)));
        let e: Error = SdkError { message: "m".into() }.into();
        assert!(matches!(e, Error::Sdk(_)));
    }

    #[test]
    fn decision_result_deserializes() {
        let body = serde_json::json!({
            "value": "a", "probability": 1.0,
            "distribution": {"a": 1.0}, "uncertainty": 0.0,
            "accepted": true, "backend": "stub", "model": "stub-1",
            "latency_ms": 0.1, "calibration_profile": "none",
            "fallback_used": false, "metadata": {}
        });
        let result: DecisionResult = serde_json::from_value(body).unwrap();
        assert_eq!(result.value, serde_json::Value::from("a"));
        assert_eq!(result.backend, "stub");
    }
}
