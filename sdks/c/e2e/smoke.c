/*
 * C client prototype end-to-end driver — slice 433.
 *
 * Usage: smoke <url> <mode> [spec_json] [state_json]
 *   mode = decide | protocol | nullargs
 *
 * Prints `STATUS=<n>` and mode-specific lines; exits 0 always
 * (the pytest harness asserts on the printed lines).
 */
#include <hugrgate.h>

#include <stdio.h>
#include <string.h>

static void print_decide(const char *url, const char *spec,
                         const char *state) {
    hg_client_t *client = NULL;
    hg_error_t *err = NULL;
    hg_decision_t *decision = NULL;
    hg_status_t st;

    st = hg_client_new(url, 5000, &client, &err);
    printf("STATUS=%d\n", (int)st);
    if (st != HG_OK) {
        printf("MSG=%s\n", err ? err->message : "?");
        printf("RECOVERABLE=%d\n", err ? err->recoverable : -1);
        hg_error_free(err);
        return;
    }
    st = hg_client_decide(client, spec, state, NULL, NULL,
                          &decision, &err);
    printf("STATUS=%d\n", (int)st);
    if (st == HG_OK) {
        printf("VALUE=%s\n", decision->value_json);
        printf("BACKEND=%s\n", decision->backend);
        hg_decision_free(decision);
    } else {
        printf("MSG=%s\n", err ? err->message : "?");
        printf("RECOVERABLE=%d\n", err ? err->recoverable : -1);
        printf("SVC_CODE=%s\n",
               err && err->service_code ? err->service_code : "-");
        hg_error_free(err);
    }
    hg_client_free(client);
}

static void print_protocol(const char *url) {
    hg_client_t *client = NULL;
    hg_error_t *err = NULL;
    char *json = NULL;
    hg_status_t st = hg_client_new(url, 5000, &client, &err);
    printf("STATUS=%d\n", (int)st);
    if (st != HG_OK) {
        hg_error_free(err);
        return;
    }
    st = hg_client_protocol(client, &json, &err);
    printf("STATUS=%d\n", (int)st);
    if (st == HG_OK) {
        printf("JSON=%s\n", json);
        hg_free_string(json);
    } else {
        printf("MSG=%s\n", err ? err->message : "?");
        hg_error_free(err);
    }
    hg_client_free(client);
}

static void print_nullargs(void) {
    hg_error_t *err = NULL;
    hg_decision_t *decision = NULL;
    hg_status_t st = hg_client_decide(NULL, "{}", "{}", NULL, NULL,
                                      &decision, &err);
    printf("STATUS=%d\n", (int)st);
    printf("MSG=%s\n", err ? err->message : "?");
    hg_error_free(err);
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: smoke <url> <mode> [spec] [state]\n");
        return 2;
    }
    if (strcmp(argv[2], "decide") == 0 && argc >= 5)
        print_decide(argv[1], argv[3], argv[4]);
    else if (strcmp(argv[2], "protocol") == 0)
        print_protocol(argv[1]);
    else if (strcmp(argv[2], "nullargs") == 0)
        print_nullargs();
    else {
        fprintf(stderr, "unknown mode\n");
        return 2;
    }
    return 0;
}
