CC ?= gcc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -O2
INCLUDE = -Iinclude

all: smoke

smoke: src/hugrgate.c e2e/smoke.c include/hugrgate.h
	$(CC) $(CFLAGS) $(INCLUDE) src/hugrgate.c e2e/smoke.c -o smoke

check: smoke
	@echo "C unit checks live in the pytest suite:"
	@echo "  pytest tests/test_deveco_432_c_abi.py tests/test_deveco_433_c_client.py"

clean:
	rm -f smoke

.PHONY: all check clean
