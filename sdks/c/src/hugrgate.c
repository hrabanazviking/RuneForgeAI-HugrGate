/*
 * HugrGate C client prototype — slice 433.
 *
 * Implements sdks/c/include/hugrgate.h with POSIX sockets and a
 * hand-rolled HTTP/1.1 client plus a minimal JSON parser/serializer.
 * No libcurl, no third-party dependencies — C99 + POSIX only.
 *
 * Prototype limits (honest, documented):
 *   - http:// only (no TLS); https:// URLs are rejected with
 *     HG_ERR_INVALID_ARG.
 *   - One request per TCP connection (Connection: close).
 *   - The client handle is not thread-safe for concurrent decide()
 *     calls (per the ABI contract); distinct handles are independent.
 */

#include <hugrgate.h>

#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <netdb.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>

/* ------------------------------------------------------------------ */
/* small utilities                                                     */
/* ------------------------------------------------------------------ */

static char *xstrndup(const char *s, size_t n) {
    char *d = (char *)malloc(n + 1);
    if (!d) return NULL;
    memcpy(d, s, n);
    d[n] = '\0';
    return d;
}

static char *xstrdup(const char *s) {
    return xstrndup(s, strlen(s));
}

/* JSON-escape a string; caller frees. */
static char *json_escape(const char *s) {
    size_t n = 0;
    const unsigned char *p = (const unsigned char *)s;
    for (; *p; p++) {
        switch (*p) {
        case '"': case '\\': case '\n': case '\r': case '\t':
        case '\b': case '\f':
            n += 2; break;
        default:
            n += (*p < 0x20) ? 6 : 1; break;
        }
    }
    char *out = (char *)malloc(n + 1), *q = out;
    if (!out) return NULL;
    for (p = (const unsigned char *)s; *p; p++) {
        switch (*p) {
        case '"': *q++ = '\\'; *q++ = '"'; break;
        case '\\': *q++ = '\\'; *q++ = '\\'; break;
        case '\n': *q++ = '\\'; *q++ = 'n'; break;
        case '\r': *q++ = '\\'; *q++ = 'r'; break;
        case '\t': *q++ = '\\'; *q++ = 't'; break;
        case '\b': *q++ = '\\'; *q++ = 'b'; break;
        case '\f': *q++ = '\\'; *q++ = 'f'; break;
        default:
            if (*p < 0x20) {
                sprintf(q, "\\u%04x", *p);
                q += 6;
            } else {
                *q++ = (char)*p;
            }
            break;
        }
    }
    *q = '\0';
    return out;
}

/* ------------------------------------------------------------------ */
/* minimal JSON DOM (parse + serialize)                                */
/* ------------------------------------------------------------------ */

typedef enum { HGJ_NULL, HGJ_BOOL, HGJ_NUM, HGJ_STR, HGJ_ARR, HGJ_OBJ } hgj_type_t;

typedef struct hgj hgj_t;
typedef struct hgj_kv { char *key; hgj_t *val; struct hgj_kv *next; } hgj_kv_t;

struct hgj {
    hgj_type_t type;
    union {
        int b;
        double n;
        char *s;
        struct { hgj_t **items; size_t len, cap; } a;
        hgj_kv_t *o;
    } u;
};

static void hgj_free(hgj_t *v) {
    size_t i;
    hgj_kv_t *kv, *nxt;
    if (!v) return;
    switch (v->type) {
    case HGJ_STR: free(v->u.s); break;
    case HGJ_ARR:
        for (i = 0; i < v->u.a.len; i++) hgj_free(v->u.a.items[i]);
        free(v->u.a.items);
        break;
    case HGJ_OBJ:
        for (kv = v->u.o; kv; kv = nxt) {
            nxt = kv->next;
            free(kv->key);
            hgj_free(kv->val);
            free(kv);
        }
        break;
    default: break;
    }
    free(v);
}

static hgj_t *hgj_new(hgj_type_t t) {
    hgj_t *v = (hgj_t *)calloc(1, sizeof(*v));
    if (v) v->type = t;
    return v;
}

typedef struct { const char *p; const char *err; } hgj_ctx_t;

static void hgj_skip_ws(hgj_ctx_t *c) {
    while (*c->p == ' ' || *c->p == '\t' || *c->p == '\n' || *c->p == '\r')
        c->p++;
}

static hgj_t *hgj_parse_value(hgj_ctx_t *c);

static int hexval(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

/* Parse a JSON string; c->p points at the opening quote. */
static char *hgj_parse_string(hgj_ctx_t *c) {
    /* first pass: measure */
    const char *p = c->p + 1;
    size_t n = 0;
    for (;;) {
        char ch = *p++;
        if (ch == '\0') { c->err = "unterminated string"; return NULL; }
        if (ch == '"') break;
        if (ch == '\\') {
            char e = *p++;
            if (e == 'u') {
                int cp = 0, i;
                for (i = 0; i < 4; i++) {
                    int h = hexval(*p++);
                    if (h < 0) { c->err = "bad \\u escape"; return NULL; }
                    cp = cp * 16 + h;
                }
                n += (cp < 0x80) ? 1 : (cp < 0x800) ? 2 : 3;
            } else if (e == '"' || e == '\\' || e == '/' || e == 'b' ||
                       e == 'f' || e == 'n' || e == 'r' || e == 't') {
                n += 1;
            } else {
                c->err = "bad escape";
                return NULL;
            }
        } else {
            n += 1;
        }
    }
    char *out = (char *)malloc(n + 1), *q = out;
    if (!out) { c->err = "out of memory"; return NULL; }
    p = c->p + 1;
    for (;;) {
        char ch = *p++;
        if (ch == '"') break;
        if (ch == '\\') {
            char e = *p++;
            if (e == 'u') {
                int cp = 0, i;
                for (i = 0; i < 4; i++) cp = cp * 16 + hexval(*p++);
                if (cp < 0x80) {
                    *q++ = (char)cp;
                } else if (cp < 0x800) {
                    *q++ = (char)(0xC0 | (cp >> 6));
                    *q++ = (char)(0x80 | (cp & 0x3F));
                } else {
                    *q++ = (char)(0xE0 | (cp >> 12));
                    *q++ = (char)(0x80 | ((cp >> 6) & 0x3F));
                    *q++ = (char)(0x80 | (cp & 0x3F));
                }
            } else {
                switch (e) {
                case '"': *q++ = '"'; break;
                case '\\': *q++ = '\\'; break;
                case '/': *q++ = '/'; break;
                case 'b': *q++ = '\b'; break;
                case 'f': *q++ = '\f'; break;
                case 'n': *q++ = '\n'; break;
                case 'r': *q++ = '\r'; break;
                case 't': *q++ = '\t'; break;
                default: break;
                }
            }
        } else {
            *q++ = ch;
        }
    }
    *q = '\0';
    c->p = p;
    return out;
}

static hgj_t *hgj_parse_value(hgj_ctx_t *c) {
    hgj_skip_ws(c);
    char ch = *c->p;
    hgj_t *v;
    if (ch == '{') {
        c->p++;
        v = hgj_new(HGJ_OBJ);
        if (!v) { c->err = "out of memory"; return NULL; }
        hgj_skip_ws(c);
        if (*c->p == '}') { c->p++; return v; }
        for (;;) {
            char *key;
            hgj_t *val;
            hgj_kv_t *kv;
            hgj_skip_ws(c);
            if (*c->p != '"') { c->err = "expected object key"; goto fail; }
            key = hgj_parse_string(c);
            if (!key) goto fail;
            hgj_skip_ws(c);
            if (*c->p != ':') {
                free(key);
                c->err = "expected ':'";
                goto fail;
            }
            c->p++;
            val = hgj_parse_value(c);
            if (!val) { free(key); goto fail; }
            kv = (hgj_kv_t *)malloc(sizeof(*kv));
            if (!kv) {
                free(key);
                hgj_free(val);
                c->err = "out of memory";
                goto fail;
            }
            kv->key = key;
            kv->val = val;
            kv->next = v->u.o;
            v->u.o = kv;
            hgj_skip_ws(c);
            if (*c->p == ',') { c->p++; continue; }
            if (*c->p == '}') { c->p++; return v; }
            c->err = "expected ',' or '}'";
            goto fail;
        }
    fail:
        hgj_free(v);
        return NULL;
    }
    if (ch == '[') {
        c->p++;
        v = hgj_new(HGJ_ARR);
        if (!v) { c->err = "out of memory"; return NULL; }
        hgj_skip_ws(c);
        if (*c->p == ']') { c->p++; return v; }
        for (;;) {
            hgj_t *item = hgj_parse_value(c);
            if (!item) { hgj_free(v); return NULL; }
            if (v->u.a.len == v->u.a.cap) {
                size_t ncap = v->u.a.cap ? v->u.a.cap * 2 : 8;
                hgj_t **ni = (hgj_t **)realloc(
                    v->u.a.items, ncap * sizeof(*ni));
                if (!ni) {
                    hgj_free(item);
                    hgj_free(v);
                    c->err = "out of memory";
                    return NULL;
                }
                v->u.a.items = ni;
                v->u.a.cap = ncap;
            }
            v->u.a.items[v->u.a.len++] = item;
            hgj_skip_ws(c);
            if (*c->p == ',') { c->p++; continue; }
            if (*c->p == ']') { c->p++; return v; }
            c->err = "expected ',' or ']'";
            hgj_free(v);
            return NULL;
        }
    }
    if (ch == '"') {
        char *s = hgj_parse_string(c);
        if (!s) return NULL;
        v = hgj_new(HGJ_STR);
        if (!v) { free(s); c->err = "out of memory"; return NULL; }
        v->u.s = s;
        return v;
    }
    if (ch == 't' && strncmp(c->p, "true", 4) == 0) {
        c->p += 4;
        v = hgj_new(HGJ_BOOL);
        if (v) v->u.b = 1;
        return v;
    }
    if (ch == 'f' && strncmp(c->p, "false", 5) == 0) {
        c->p += 5;
        v = hgj_new(HGJ_BOOL);
        if (v) v->u.b = 0;
        return v;
    }
    if (ch == 'n' && strncmp(c->p, "null", 4) == 0) {
        c->p += 4;
        return hgj_new(HGJ_NULL);
    }
    if (ch == '-' || (ch >= '0' && ch <= '9')) {
        char *end;
        double n = strtod(c->p, &end);
        if (end == c->p) { c->err = "bad number"; return NULL; }
        c->p = end;
        v = hgj_new(HGJ_NUM);
        if (v) v->u.n = n;
        return v;
    }
    c->err = "unexpected character";
    return NULL;
}

static hgj_t *hgj_parse(const char *text, const char **err) {
    hgj_ctx_t c = { text, NULL };
    hgj_t *v = hgj_parse_value(&c);
    if (!v) {
        if (err) *err = c.err ? c.err : "parse error";
        return NULL;
    }
    hgj_skip_ws(&c);
    if (*c.p != '\0') {
        hgj_free(v);
        if (err) *err = "trailing characters";
        return NULL;
    }
    return v;
}

static const hgj_t *hgj_obj_get(const hgj_t *obj, const char *key) {
    hgj_kv_t *kv;
    if (!obj || obj->type != HGJ_OBJ) return NULL;
    for (kv = obj->u.o; kv; kv = kv->next)
        if (strcmp(kv->key, key) == 0) return kv->val;
    return NULL;
}

/* Serialize a node to compact JSON; caller frees. */
static int hgj_write(const hgj_t *v, char **buf, size_t *len, size_t *cap);

static int hgj_grow(char **buf, size_t *len, size_t *cap, size_t need) {
    if (*len + need + 1 > *cap) {
        size_t ncap = (*cap ? *cap * 2 : 64);
        while (ncap < *len + need + 1) ncap *= 2;
        char *nb = (char *)realloc(*buf, ncap);
        if (!nb) return -1;
        *buf = nb;
        *cap = ncap;
    }
    return 0;
}

static int hgj_puts(const char *s, char **buf, size_t *len, size_t *cap) {
    size_t n = strlen(s);
    if (hgj_grow(buf, len, cap, n)) return -1;
    memcpy(*buf + *len, s, n);
    *len += n;
    (*buf)[*len] = '\0';
    return 0;
}

static int hgj_write(const hgj_t *v, char **buf, size_t *len, size_t *cap) {
    size_t i;
    hgj_kv_t *kv;
    char num[64];
    char *esc;
    switch (v->type) {
    case HGJ_NULL: return hgj_puts("null", buf, len, cap);
    case HGJ_BOOL: return hgj_puts(v->u.b ? "true" : "false", buf, len, cap);
    case HGJ_NUM:
        snprintf(num, sizeof(num), "%.17g", v->u.n);
        return hgj_puts(num, buf, len, cap);
    case HGJ_STR:
        esc = json_escape(v->u.s);
        if (!esc) return -1;
        if (hgj_puts("\"", buf, len, cap) || hgj_puts(esc, buf, len, cap) ||
            hgj_puts("\"", buf, len, cap)) {
            free(esc);
            return -1;
        }
        free(esc);
        return 0;
    case HGJ_ARR:
        if (hgj_puts("[", buf, len, cap)) return -1;
        for (i = 0; i < v->u.a.len; i++) {
            if (i && hgj_puts(",", buf, len, cap)) return -1;
            if (hgj_write(v->u.a.items[i], buf, len, cap)) return -1;
        }
        return hgj_puts("]", buf, len, cap);
    case HGJ_OBJ:
        if (hgj_puts("{", buf, len, cap)) return -1;
        for (kv = v->u.o, i = 0; kv; kv = kv->next, i++) {
            hgj_t ks;
            if (i && hgj_puts(",", buf, len, cap)) return -1;
            ks.type = HGJ_STR;
            ks.u.s = kv->key;
            if (hgj_write(&ks, buf, len, cap)) return -1;
            if (hgj_puts(":", buf, len, cap)) return -1;
            if (hgj_write(kv->val, buf, len, cap)) return -1;
        }
        return hgj_puts("}", buf, len, cap);
    }
    return -1;
}

static char *hgj_serialize(const hgj_t *v) {
    char *buf = NULL;
    size_t len = 0, cap = 0;
    if (hgj_write(v, &buf, &len, &cap)) {
        free(buf);
        return NULL;
    }
    return buf ? buf : xstrdup("");
}

/* ------------------------------------------------------------------ */
/* error helpers                                                       */
/* ------------------------------------------------------------------ */

struct hg_client {
    char *host;
    char *port;
    long timeout_ms;
};

static hg_error_t *mkerr(hg_status_t code, const char *service_code,
                         const char *fmt, ...) {
    hg_error_t *e = (hg_error_t *)calloc(1, sizeof(*e));
    char buf[1024];
    va_list ap;
    if (!e) return NULL;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    e->code = code;
    e->message = xstrdup(buf);
    e->recoverable = hg_status_recoverable(code);
    e->service_code = service_code ? xstrdup(service_code) : NULL;
    if (!e->message) {
        hg_error_free(e);
        return NULL;
    }
    return e;
}

/* ------------------------------------------------------------------ */
/* public API                                                          */
/* ------------------------------------------------------------------ */

const char *hg_status_message(hg_status_t status) {
    switch (status) {
    case HG_OK: return "success";
    case HG_ERR_INVALID_ARG: return "invalid argument";
    case HG_ERR_NOMEM: return "out of memory";
    case HG_ERR_TRANSPORT: return "transport failure";
    case HG_ERR_TIMEOUT: return "request timed out";
    case HG_ERR_PROTOCOL: return "protocol version skew";
    case HG_ERR_SPEC: return "service rejected the spec";
    case HG_ERR_POLICY: return "service rejected the policy";
    case HG_ERR_BACKEND: return "backend failure";
    case HG_ERR_UNAVAILABLE: return "no backend available";
    case HG_ERR_ABSTAINED: return "service abstained";
    case HG_ERR_BAD_RESPONSE: return "undecodable service response";
    default: return "unknown status";
    }
}

int hg_status_recoverable(hg_status_t status) {
    switch (status) {
    case HG_ERR_TRANSPORT:
    case HG_ERR_TIMEOUT:
    case HG_ERR_BACKEND:
    case HG_ERR_UNAVAILABLE:
        return 1;
    default:
        return 0;
    }
}

void hg_error_free(hg_error_t *err) {
    if (!err) return;
    free(err->message);
    free(err->service_code);
    free(err);
}

void hg_free_string(char *str) {
    free(str);
}

void hg_decision_free(hg_decision_t *decision) {
    if (!decision) return;
    free(decision->value_json);
    free(decision->distribution_json);
    free(decision->backend);
    free(decision->model);
    free(decision->calibration_profile);
    free(decision->metadata_json);
    free(decision);
}

void hg_client_free(hg_client_t *client) {
    if (!client) return;
    free(client->host);
    free(client->port);
    free(client);
}

/* Parse "http://host[:port][/...]".  Only http:// is supported. */
static hg_status_t parse_url(const char *url, char **host, char **port,
                             hg_error_t **err) {
    const char *p, *slash, *colon;
    if (!url || strncmp(url, "http://", 7) != 0) {
        *err = mkerr(HG_ERR_INVALID_ARG, NULL,
                     "only http:// URLs are supported (prototype has no TLS)");
        return HG_ERR_INVALID_ARG;
    }
    p = url + 7;
    slash = strchr(p, '/');
    colon = strchr(p, ':');
    if (colon && (!slash || colon < slash)) {
        *host = xstrndup(p, (size_t)(colon - p));
        *port = xstrndup(colon + 1,
                         slash ? (size_t)(slash - colon - 1)
                               : strlen(colon + 1));
    } else {
        *host = xstrndup(p, slash ? (size_t)(slash - p) : strlen(p));
        *port = xstrdup("80");
    }
    if (!*host || !*port || **host == '\0') {
        free(*host);
        free(*port);
        *err = mkerr(HG_ERR_INVALID_ARG, NULL,
                     "malformed service URL: %s", url);
        return HG_ERR_INVALID_ARG;
    }
    return HG_OK;
}

hg_status_t hg_client_new(const char *url, long timeout_ms,
                          hg_client_t **client, hg_error_t **err) {
    hg_client_t *c;
    hg_status_t st;
    if (err) *err = NULL;
    if (!url || !client) {
        if (err)
            *err = mkerr(HG_ERR_INVALID_ARG, NULL,
                         "url and client out-param are required");
        return HG_ERR_INVALID_ARG;
    }
    c = (hg_client_t *)calloc(1, sizeof(*c));
    if (!c) {
        if (err)
            *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return HG_ERR_NOMEM;
    }
    st = parse_url(url, &c->host, &c->port, err);
    if (st != HG_OK) {
        free(c);
        return st;
    }
    c->timeout_ms = timeout_ms > 0 ? timeout_ms : 10000;
    *client = c;
    return HG_OK;
}

/* --- HTTP ------------------------------------------------------------ */

typedef struct {
    int status;
    char *body;      /* NUL-terminated body (may be binary-clean JSON) */
    size_t body_len;
} http_resp_t;

static void http_resp_free(http_resp_t *r) {
    if (!r) return;
    free(r->body);
    free(r);
}

static void set_timeouts(int fd, long timeout_ms) {
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

static int tcp_connect(const char *host, const char *port, long timeout_ms) {
    struct addrinfo hints, *res, *rp;
    int fd = -1, rc;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    rc = getaddrinfo(host, port, &hints, &res);
    if (rc != 0) return -1;
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0) continue;
        set_timeouts(fd, timeout_ms);
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

static int send_all(int fd, const char *buf, size_t n) {
    while (n > 0) {
        ssize_t w = send(fd, buf, n, 0);
        if (w < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (w == 0) return -1;
        buf += w;
        n -= (size_t)w;
    }
    return 0;
}

/* Read until EOF or timeout; caller frees *out. */
static int recv_all(int fd, char **out, size_t *out_len) {
    size_t cap = 8192, len = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) return -1;
    for (;;) {
        ssize_t r;
        if (len == cap) {
            cap *= 2;
            char *nb = (char *)realloc(buf, cap);
            if (!nb) {
                free(buf);
                return -1;
            }
            buf = nb;
        }
        r = recv(fd, buf + len, cap - len, 0);
        if (r < 0) {
            if (errno == EINTR) continue;
            if ((errno == EAGAIN || errno == EWOULDBLOCK) && len > 0)
                break; /* timeout after partial body: take what we got */
            free(buf);
            return -1;
        }
        if (r == 0) break; /* EOF */
        len += (size_t)r;
    }
    *out = buf;
    *out_len = len;
    return 0;
}

/* Split headers/body; parse the status code. */
static int parse_response(const char *raw, size_t raw_len,
                          http_resp_t *resp) {
    const char *hdr_end = NULL;
    size_t i;
    for (i = 0; i + 3 < raw_len; i++) {
        if (raw[i] == '\r' && raw[i + 1] == '\n' &&
            raw[i + 2] == '\r' && raw[i + 3] == '\n') {
            hdr_end = raw + i + 4;
            break;
        }
    }
    if (!hdr_end) return -1;
    /* status line: HTTP/1.1 200 OK */
    {
        const char *sp = strchr(raw, ' ');
        if (!sp || sp >= hdr_end) return -1;
        resp->status = atoi(sp + 1);
    }
    resp->body_len = raw_len - (size_t)(hdr_end - raw);
    resp->body = xstrndup(hdr_end, resp->body_len);
    return resp->body ? 0 : -1;
}

static http_resp_t *http_roundtrip(hg_client_t *c, const char *request,
                                   size_t req_len, hg_error_t **err) {
    int fd = tcp_connect(c->host, c->port, c->timeout_ms);
    char *raw = NULL;
    size_t raw_len = 0;
    http_resp_t *resp;
    if (fd < 0) {
        *err = mkerr(HG_ERR_TRANSPORT, NULL,
                     "cannot connect to %s:%s", c->host, c->port);
        return NULL;
    }
    if (send_all(fd, request, req_len) != 0) {
        close(fd);
        *err = mkerr(HG_ERR_TRANSPORT, NULL, "send failed: %s",
                     strerror(errno));
        return NULL;
    }
    if (recv_all(fd, &raw, &raw_len) != 0) {
        close(fd);
        *err = mkerr(HG_ERR_TIMEOUT, NULL, "receive failed: %s",
                     strerror(errno));
        return NULL;
    }
    close(fd);
    resp = (http_resp_t *)calloc(1, sizeof(*resp));
    if (!resp) {
        free(raw);
        *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return NULL;
    }
    if (parse_response(raw, raw_len, resp) != 0) {
        free(raw);
        http_resp_free(resp);
        *err = mkerr(HG_ERR_BAD_RESPONSE, NULL,
                     "could not parse HTTP response");
        return NULL;
    }
    free(raw);
    return resp;
}

/* --- error code mapping ------------------------------------------------- */

static hg_status_t map_service_code(const char *code) {
    if (!code) return HG_ERR_BACKEND;
    if (strcmp(code, "spec_error") == 0) return HG_ERR_SPEC;
    if (strcmp(code, "policy_error") == 0) return HG_ERR_POLICY;
    if (strcmp(code, "protocol_error") == 0) return HG_ERR_PROTOCOL;
    if (strcmp(code, "backend_unavailable") == 0) return HG_ERR_UNAVAILABLE;
    if (strcmp(code, "timeout") == 0) return HG_ERR_TIMEOUT;
    return HG_ERR_BACKEND;
}

/* Build an hg_error_t from a parsed error envelope body. */
static hg_error_t *error_from_body(const hgj_t *root, int http_status) {
    const hgj_t *envelope = hgj_obj_get(root, "error");
    const hgj_t *code, *message, *recoverable;
    hg_error_t *e;
    char *msg;
    if (!envelope || envelope->type != HGJ_OBJ) {
        return mkerr(HG_ERR_BAD_RESPONSE, NULL,
                     "HTTP %d with undecodable error body", http_status);
    }
    code = hgj_obj_get(envelope, "code");
    message = hgj_obj_get(envelope, "message");
    recoverable = hgj_obj_get(envelope, "recoverable");
    e = (hg_error_t *)calloc(1, sizeof(*e));
    if (!e) return NULL;
    e->code = map_service_code(
        code && code->type == HGJ_STR ? code->u.s : NULL);
    msg = (message && message->type == HGJ_STR)
        ? xstrdup(message->u.s) : xstrdup(hg_status_message(e->code));
    if (!msg) {
        free(e);
        return NULL;
    }
    e->message = msg;
    e->recoverable = (recoverable && recoverable->type == HGJ_BOOL)
        ? recoverable->u.b : hg_status_recoverable(e->code);
    e->service_code = (code && code->type == HGJ_STR)
        ? xstrdup(code->u.s) : NULL;
    return e;
}

/* --- decisions ------------------------------------------------------------ */

hg_status_t hg_client_decide(hg_client_t *client,
                             const char *spec_json,
                             const char *state_json,
                             const char *policy_json,
                             const char *backend_name,
                             hg_decision_t **decision,
                             hg_error_t **err) {
    char *payload = NULL, *request = NULL;
    char *esc_backend = NULL;
    size_t payload_len, req_len;
    http_resp_t *resp = NULL;
    hgj_t *root = NULL;
    const char *jerr = NULL;
    const hgj_t *node;
    hg_decision_t *d = NULL;
    hg_status_t st;

    if (err) *err = NULL;
    if (!client || !spec_json || !state_json || !decision) {
        if (err)
            *err = mkerr(HG_ERR_INVALID_ARG, NULL,
                         "client, spec_json, state_json and decision "
                         "out-param are required");
        return HG_ERR_INVALID_ARG;
    }
    *decision = NULL;

    if (backend_name) {
        esc_backend = json_escape(backend_name);
        if (!esc_backend) {
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
    }

    /* Build the protocol-v1 payload.  spec/state/policy arrive as raw
       JSON documents; only backend_name needs escaping. */
    {
        /* two-pass: measure then fill */
        size_t need = strlen("{\"protocol_version\":\"\",\"spec\":,"
                            "\"state\":,\"backend_name\":,"
                            "\"context\":null,\"policy\":}") +
            strlen(HUGRGATE_PROTOCOL_VERSION) + strlen(spec_json) +
            strlen(state_json) +
            (esc_backend ? strlen(esc_backend) + 2 : 4) +
            (policy_json ? strlen(policy_json) : 4) + 1;
        payload = (char *)malloc(need);
        if (!payload) {
            free(esc_backend);
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
        if (esc_backend) {
            snprintf(payload, need,
                     "{\"protocol_version\":\"%s\",\"spec\":%s,"
                     "\"state\":%s,\"backend_name\":\"%s\","
                     "\"context\":null,\"policy\":%s}",
                     HUGRGATE_PROTOCOL_VERSION, spec_json, state_json,
                     esc_backend, policy_json ? policy_json : "null");
        } else {
            snprintf(payload, need,
                     "{\"protocol_version\":\"%s\",\"spec\":%s,"
                     "\"state\":%s,\"backend_name\":null,"
                     "\"context\":null,\"policy\":%s}",
                     HUGRGATE_PROTOCOL_VERSION, spec_json, state_json,
                     policy_json ? policy_json : "null");
        }
        payload_len = strlen(payload);
    }
    free(esc_backend);

    {
        const char *fmt =
            "POST /decide HTTP/1.1\r\n"
            "Host: %s:%s\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %zu\r\n"
            "Connection: close\r\n"
            "User-Agent: hugrgate-sdk-c/%s\r\n"
            "\r\n";
        size_t hlen = (size_t)snprintf(NULL, 0, fmt, client->host,
                                      client->port, payload_len,
                                      HUGRGATE_SDK_VERSION);
        request = (char *)malloc(hlen + payload_len + 1);
        if (!request) {
            free(payload);
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
        snprintf(request, hlen + 1, fmt, client->host, client->port,
                 payload_len, HUGRGATE_SDK_VERSION);
        memcpy(request + hlen, payload, payload_len + 1);
        req_len = hlen + payload_len;
    }
    free(payload);

    resp = http_roundtrip(client, request, req_len, err);
    free(request);
    if (!resp) {
        /* err already set by http_roundtrip */
        return (*err)->code;
    }

    root = hgj_parse(resp->body, &jerr);
    if (!root) {
        st = HG_ERR_BAD_RESPONSE;
        if (err)
            *err = mkerr(st, NULL, "invalid JSON in response: %s",
                         jerr ? jerr : "?");
        http_resp_free(resp);
        return st;
    }

    if (resp->status < 200 || resp->status >= 300) {
        hg_error_t *e = error_from_body(root, resp->status);
        hgj_free(root);
        http_resp_free(resp);
        if (!e) {
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
        if (err) *err = e;
        else hg_error_free(e);
        return e->code;
    }

    node = hgj_obj_get(root, "abstained");
    if (node && node->type == HGJ_BOOL && node->u.b) {
        const hgj_t *msg = hgj_obj_get(root, "message");
        const hgj_t *reason = hgj_obj_get(root, "reason");
        hg_error_t *e = mkerr(
            HG_ERR_ABSTAINED, "abstention", "%s (reason: %s)",
            msg && msg->type == HGJ_STR ? msg->u.s : "service abstained",
            reason && reason->type == HGJ_STR ? reason->u.s
                                             : "below_threshold");
        hgj_free(root);
        http_resp_free(resp);
        if (!e) {
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
        if (err) *err = e;
        else hg_error_free(e);
        return HG_ERR_ABSTAINED;
    }

    node = hgj_obj_get(root, "decision");
    if (!node || node->type != HGJ_OBJ) node = root;
    if (node->type != HGJ_OBJ || !hgj_obj_get(node, "value")) {
        hgj_free(root);
        http_resp_free(resp);
        if (err)
            *err = mkerr(HG_ERR_BAD_RESPONSE, NULL,
                         "service returned no decision");
        return HG_ERR_BAD_RESPONSE;
    }

    d = (hg_decision_t *)calloc(1, sizeof(*d));
    if (!d) {
        hgj_free(root);
        http_resp_free(resp);
        if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return HG_ERR_NOMEM;
    }
    {
        const hgj_t *v;
#define FILL_STR(field, key, fallback)                                     \
    do {                                                                   \
        const hgj_t *_n = hgj_obj_get(node, key);                           \
        d->field = (_n && _n->type == HGJ_STR) ? xstrdup(_n->u.s)           \
                                              : xstrdup(fallback);         \
    } while (0)
#define FILL_JSON(field, key, fallback)                                    \
    do {                                                                   \
        const hgj_t *_n = hgj_obj_get(node, key);                           \
        d->field = _n ? hgj_serialize(_n) : xstrdup(fallback);              \
    } while (0)
#define FILL_NUM(field, key)                                               \
    do {                                                                   \
        const hgj_t *_n = hgj_obj_get(node, key);                           \
        d->field = (_n && _n->type == HGJ_NUM) ? _n->u.n : 0.0;             \
    } while (0)
#define FILL_BOOL(field, key)                                              \
    do {                                                                   \
        const hgj_t *_n = hgj_obj_get(node, key);                           \
        d->field = (_n && _n->type == HGJ_BOOL) ? _n->u.b : 0;              \
    } while (0)
        FILL_JSON(value_json, "value", "null");
        FILL_NUM(probability, "probability");
        FILL_JSON(distribution_json, "distribution", "{}");
        FILL_NUM(uncertainty, "uncertainty");
        FILL_BOOL(accepted, "accepted");
        FILL_STR(backend, "backend", "unknown");
        FILL_STR(model, "model", "unknown");
        FILL_NUM(latency_ms, "latency_ms");
        FILL_STR(calibration_profile, "calibration_profile", "none");
        FILL_BOOL(fallback_used, "fallback_used");
        FILL_JSON(metadata_json, "metadata", "{}");
#undef FILL_STR
#undef FILL_JSON
#undef FILL_NUM
#undef FILL_BOOL
        v = NULL;
        (void)v;
    }
    if (!d->value_json || !d->distribution_json || !d->backend ||
        !d->model || !d->calibration_profile || !d->metadata_json) {
        hg_decision_free(d);
        hgj_free(root);
        http_resp_free(resp);
        if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return HG_ERR_NOMEM;
    }
    hgj_free(root);
    http_resp_free(resp);
    *decision = d;
    return HG_OK;
}

/* --- introspection ------------------------------------------------------ */

hg_status_t hg_client_protocol(hg_client_t *client,
                               char **json_out, hg_error_t **err) {
    char *request = NULL;
    http_resp_t *resp;
    size_t hlen;
    const char *fmt =
        "GET /protocol HTTP/1.1\r\n"
        "Host: %s:%s\r\n"
        "Connection: close\r\n"
        "User-Agent: hugrgate-sdk-c/%s\r\n"
        "\r\n";
    if (err) *err = NULL;
    if (!client || !json_out) {
        if (err)
            *err = mkerr(HG_ERR_INVALID_ARG, NULL,
                         "client and json_out are required");
        return HG_ERR_INVALID_ARG;
    }
    *json_out = NULL;
    hlen = (size_t)snprintf(NULL, 0, fmt, client->host, client->port,
                            HUGRGATE_SDK_VERSION);
    request = (char *)malloc(hlen + 1);
    if (!request) {
        if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return HG_ERR_NOMEM;
    }
    snprintf(request, hlen + 1, fmt, client->host, client->port,
             HUGRGATE_SDK_VERSION);
    resp = http_roundtrip(client, request, hlen, err);
    free(request);
    if (!resp) return (*err)->code;
    if (resp->status < 200 || resp->status >= 300) {
        hgj_t *root = hgj_parse(resp->body, NULL);
        hg_error_t *e = root ? error_from_body(root, resp->status)
                             : mkerr(HG_ERR_BAD_RESPONSE, NULL,
                                     "HTTP %d on /protocol", resp->status);
        if (root) hgj_free(root);
        http_resp_free(resp);
        if (!e) {
            if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
            return HG_ERR_NOMEM;
        }
        if (err) *err = e;
        else hg_error_free(e);
        return e->code;
    }
    *json_out = xstrndup(resp->body, resp->body_len);
    http_resp_free(resp);
    if (!*json_out) {
        if (err) *err = mkerr(HG_ERR_NOMEM, NULL, "out of memory");
        return HG_ERR_NOMEM;
    }
    return HG_OK;
}
