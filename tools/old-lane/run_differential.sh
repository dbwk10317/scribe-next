#!/bin/sh
# usage: run_differential.sh CHECKOUT_DIR NEW_OUTPUT_DIR [case ...]
# Runs each daemon_differential case in its own isolated container of IMAGE.
# CHECKOUT_DIR: exported tree with tools/ (git archive main | tar -x). NEW_OUTPUT_DIR must not exist.
set -eu
CHECKOUT=$(realpath "$1"); OUT=$2; shift 2
IMAGE=${IMAGE:-scribe-next-differential:latest}
[ $# -gt 0 ] || set -- file stores rotation restart spool mixed-spool file-stores fb303 mapping game-profile rotation-time backpressure bucket-hash relay-stream mixed-relay-stream receiver-restart mixed-receiver-restart receiver-crash mixed-receiver-crash receiver-stall mixed-receiver-stall sender-restart-spool mixed-sender-restart-spool throttle-retry mixed-throttle-retry
mkdir -m 0777 "$OUT"; OUT=$(realpath "$OUT")
cat > "$OUT/targets.json" <<'EOF'
{
  "old": {"command": ["/old-lane/bin/scribed"], "environment": {"LD_LIBRARY_PATH": "/old-lane/lib"}},
  "modern": {"command": ["/usr/local/bin/scribed"], "environment": {}}
}
EOF
failed=0
for case in "$@"; do
  rc=0
  docker run --rm --network none --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
    --cpus 2 --memory 2g --pids-limit 512 \
    -v "$CHECKOUT:/validation-input:ro" -v "$OUT:/out" "$IMAGE" \
    python3 /validation-input/tools/daemon_differential.py --run-isolated-daemons \
    --targets /out/targets.json --output "/out/$case" --case "$case" > "$OUT/$case.log" 2>&1 || rc=$?
  [ "$rc" -eq 0 ] || failed=1
  echo "$case exit=$rc" | tee -a "$OUT/summary.txt"
done
# every case still runs; exit non-zero if any failed so callers need not parse summary.txt
exit "$failed"
