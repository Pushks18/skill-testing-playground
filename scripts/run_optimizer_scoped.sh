#!/bin/bash
# Run the optimizer per classification file against a domain-scoped task dir.
# The full bank (178+ tasks) makes every run cost ~835 rollout calls; scoping
# to the clusters' own domains keeps runs affordable and the splits relevant.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
export LANGCHAIN_TRACING_V2=false

run_scoped() {
  local clsfile="$1"; shift
  local scoped="/tmp/opt_tasks_$(basename "$clsfile" .json)"
  rm -rf "$scoped" && mkdir -p "$scoped"
  for prefix in "$@"; do
    for d in tasks/${prefix}*; do
      [ -d "$d" ] && cp -R "$d" "$scoped/"
    done
  done
  echo "=== OPTIMIZER: $clsfile  (tasks: $(ls "$scoped" | wc -l | tr -d ' ') scoped to: $*)  $(date +%H:%M:%S) ==="
  $PY -m eval.optimizer.optimize \
    --classification "$clsfile" \
    --tasks-dir "$scoped" \
    --cluster-timeout 3600 --heartbeat 120 --max-rollout-calls 400
  echo "=== exit $? for $clsfile ==="
}

# cluster domains verified per file; prefixes from eval/taskgen.py DOMAIN_TARGETS
run_scoped failure_classification_modify-booking.json edge-
run_scoped failure_classification_planning.json itinerary- planning-
run_scoped failure_classification_booking-skill.json booking-flow-
echo "OPTIMIZER BATCH DONE $(date +%H:%M:%S)"
