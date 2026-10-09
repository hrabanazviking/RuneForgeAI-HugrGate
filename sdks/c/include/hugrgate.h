/*
 * HugrGate stable C ABI — slice 432.
 *
 * This header is the binary-stability contract for the HugrGate C
 * client.  It is designed to be consumed from C, C++, Rust, Go, Mojo,
 * and any other language with a C FFI.
 *
 * ABI STABILITY RULES (the whole point of this file):
 *
 *   1. `hg_client_t` is opaque.  Its size and layout are private to
 *      the implementation; callers only ever touch pointers to it.
 *      New client state is added behind the pointer, never in this
 *      header.
 *   2. `hg_decision_t` is a *caller-owned snapshot*: the API
 *      allocates it and the caller frees it with hg_decision_free().
 *      Fields are only ever APPENDED at the end of the struct, and
 *      the struct is never passed by value across the boundary —
 *      only `hg_decision_t *`.
 *   3. `hg_status_t` codes are stable: existing enumerators never
 *      change value and are never removed; new failures get new
 *      enumerators appended at the end.
 *   4. All strings crossing the boundary are NUL-terminated UTF-8.
 *      Input strings are borrowed (caller keeps them alive for the
 *      call); output strings are owned by the returned object and
 *      freed with it.
 *   5. Every fallible function reports through `hg_error_t **`:
 *      on failure it returns a non-zero status and sets *err to an
 *      allocated error; on success *err is set to NULL.
 *      hg_error_free(NULL) is a no-op.
 *   6. The header is C99-clean and C++-compatible (extern "C").
 *      No C11/C23-only features, no <stdbool.h> in the ABI (plain
 *      int is used for flags), no bitfields.
 *
 * Threading: a client handle is NOT thread-safe for concurrent
 * decide() calls; create one handle per thread or serialize calls.
 * Distinct handles are fully independent.
 */

#ifndef HUGRGATE_H
#define HUGRGATE_H

#ifdef __cplusplus
extern "C" {
#endif

/* --- versions ------------------------------------------------------- */

/** ABI major version: bumped only on breaking ABI change. */
#define HUGRGATE_ABI_VERSION_MAJOR 1
/** ABI minor version: bumped on backward-compatible additions. */
#define HUGRGATE_ABI_VERSION_MINOR 0
/** Wire-protocol version this ABI speaks. */
#define HUGRGATE_PROTOCOL_VERSION "1.0"
/** SDK marketing version (matches the other SDKs). */
#define HUGRGATE_SDK_VERSION "2.0"

/* --- status codes ---------------------------------------------------- */

/**
 * Every enumerator value is frozen forever (rule 3).  New codes are
 * appended at the end, before HG_STATUS_COUNT.
 */
typedef enum hg_status {
    HG_OK = 0,               /**< success */
    HG_ERR_INVALID_ARG = 1,  /**< NULL/invalid argument (caller bug) */
    HG_ERR_NOMEM = 2,        /**< allocation failure */
    HG_ERR_TRANSPORT = 3,    /**< TCP/TLS/HTTP failure (retryable) */
    HG_ERR_TIMEOUT = 4,      /**< request exceeded deadline (retryable) */
    HG_ERR_PROTOCOL = 5,     /**< protocol version skew (not retryable) */
    HG_ERR_SPEC = 6,         /**< service rejected the spec (not retryable) */
    HG_ERR_POLICY = 7,       /**< service rejected the policy */
    HG_ERR_BACKEND = 8,      /**< backend failed server-side (retryable) */
    HG_ERR_UNAVAILABLE = 9,  /**< no backend available (retryable) */
    HG_ERR_ABSTAINED = 10,   /**< service abstained; see hg_error message */
    HG_ERR_BAD_RESPONSE = 11,/**< undecodable service response */
    HG_STATUS_COUNT          /**< number of status codes (not an error) */
} hg_status_t;

/* --- opaque client handle -------------------------------------------- */

/** Opaque client handle (rule 1). */
typedef struct hg_client hg_client_t;

/* --- error object ----------------------------------------------------- */

/** Allocated error descriptor; free with hg_error_free(). */
typedef struct hg_error {
    hg_status_t code;   /**< stable machine-readable status */
    char *message;      /**< human-readable detail (never NULL) */
    int recoverable;    /**< non-zero when retrying may succeed */
    char *service_code; /**< taxonomy code from the service, or NULL */
} hg_error_t;

/* --- decision snapshot ------------------------------------------------ */

/**
 * Caller-owned decision snapshot (rule 2).  Obtained from
 * hg_client_decide(); released with hg_decision_free().
 */
typedef struct hg_decision {
    char *value_json;      /**< decided value, JSON-encoded, never NULL */
    double probability;    /**< probability of the decided value */
    char *distribution_json; /**< full distribution, JSON object */
    double uncertainty;
    int accepted;
    char *backend;         /**< backend name, never NULL */
    char *model;           /**< model name, never NULL */
    double latency_ms;
    char *calibration_profile;
    int fallback_used;
    char *metadata_json;   /**< result metadata, JSON object */
    /* New fields are appended below this line (rule 2). */
} hg_decision_t;

/* --- client lifecycle -------------------------------------------------- */

/**
 * Create a client for the service at `url` (e.g.
 * "http://127.0.0.1:8377").  `timeout_ms` <= 0 selects the default
 * (10000).  Returns HG_OK and sets *client, or a non-zero status
 * with *err allocated.
 */
hg_status_t hg_client_new(const char *url, long timeout_ms,
                          hg_client_t **client, hg_error_t **err);

/** Destroy a client.  hg_client_free(NULL) is a no-op. */
void hg_client_free(hg_client_t *client);

/* --- decisions ---------------------------------------------------------- */

/**
 * Make one decision.  `spec_json` and `state_json` are JSON documents
 * (see the HugrGate wire protocol); `policy_json` and
 * `backend_name` may be NULL.  On HG_OK, *decision holds an
 * allocated snapshot (free with hg_decision_free) and *err is NULL.
 * On HG_ERR_ABSTAINED the service abstained; the reason is in the
 * error message.
 */
hg_status_t hg_client_decide(hg_client_t *client,
                             const char *spec_json,
                             const char *state_json,
                             const char *policy_json,
                             const char *backend_name,
                             hg_decision_t **decision,
                             hg_error_t **err);

/** Release a decision snapshot.  hg_decision_free(NULL) is a no-op. */
void hg_decision_free(hg_decision_t *decision);

/* --- introspection ------------------------------------------------------- */

/**
 * Fetch the service's protocol advertisement as a JSON document
 * (caller frees with hg_free_string).  Never fails on version skew:
 * the document itself carries the versions.
 */
hg_status_t hg_client_protocol(hg_client_t *client,
                               char **json_out, hg_error_t **err);

/* --- errors --------------------------------------------------------------- */

/** Human-readable message for a status code (never NULL). */
const char *hg_status_message(hg_status_t status);

/** Non-zero when the status is retryable (transport/timeout/backend). */
int hg_status_recoverable(hg_status_t status);

/** Release an error object.  hg_error_free(NULL) is a no-op. */
void hg_error_free(hg_error_t *err);

/* --- strings --------------------------------------------------------------- */

/**
 * Release a string allocated by the API (e.g. from
 * hg_client_protocol).  hg_free_string(NULL) is a no-op.
 */
void hg_free_string(char *str);

#ifdef __cplusplus
}
#endif

#endif /* HUGRGATE_H */
