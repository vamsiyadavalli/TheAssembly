#!/usr/bin/env bash
# memory_profile_streamlit.sh — Sample RSS for one or two Streamlit processes.
#
# Usage:
#   ./tools/memory_profile_streamlit.sh <scenario> <duration_sec> <interval_sec> <pid1> [pid2]
#
# Positional args:
#   scenario      — Label for the report (e.g. "athlete-idle", "both-worst-case")
#   duration_sec  — How many seconds to sample
#   interval_sec  — Sampling interval in seconds
#   pid1          — PID of first process (athlete or admin)
#   pid2          — (optional) PID of second process for simultaneous runs
#
# Output:
#   Prints live samples to stdout.
#   Writes a timestamped report to tools/reports/<timestamp>_<scenario>.txt

set -euo pipefail

SCENARIO="${1:-unnamed}"
DURATION="${2:-30}"
INTERVAL="${3:-2}"
PID1="${4:-}"
PID2="${5:-}"

if [[ -z "$PID1" ]]; then
  echo "ERROR: pid1 is required." >&2
  echo "Usage: $0 <scenario> <duration_sec> <interval_sec> <pid1> [pid2]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="$SCRIPT_DIR/reports"
mkdir -p "$REPORTS_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="$REPORTS_DIR/${TIMESTAMP}_${SCENARIO}.txt"

STREAMLIT_OVERHEAD_MB=180   # conservative Cloud container + runtime baseline
CAPACITY_MB=1024            # Streamlit Community Cloud 1 GB limit
CAUTION_THRESHOLD_MB=700    # combined peak above this triggers caution
UNSAFE_THRESHOLD_MB=900     # combined peak above this is unsafe

{
  echo "====================================================="
  echo " Memory Profile: $SCENARIO"
  echo " Date     : $(date)"
  echo " Duration : ${DURATION}s   Interval: ${INTERVAL}s"
  echo " PID1     : $PID1"
  [[ -n "$PID2" ]] && echo " PID2     : $PID2"
  echo "====================================================="
  echo ""
  echo "Time(s)  RSS_1(MB)$([ -n "$PID2" ] && echo "  RSS_2(MB)  Combined(MB)")"
  echo "-------  ---------$([ -n "$PID2" ] && echo "  ---------  ------------")"
} | tee -a "$REPORT_FILE"

PEAK1=0
PEAK2=0
PEAK_COMBINED=0
TOTAL1=0
TOTAL2=0
TOTAL_COMBINED=0
SAMPLES=0
START=$(date +%s)

rss_mb() {
  local pid="$1"
  # macOS: ps -o rss returns kibibytes
  local rss_kb
  rss_kb=$(ps -o rss= -p "$pid" 2>/dev/null || echo 0)
  echo $(( rss_kb / 1024 ))
}

while true; do
  ELAPSED=$(( $(date +%s) - START ))
  [[ $ELAPSED -ge $DURATION ]] && break

  RSS1=$(rss_mb "$PID1")
  LINE="${ELAPSED}s      ${RSS1}MB"

  if [[ -n "$PID2" ]]; then
    RSS2=$(rss_mb "$PID2")
    COMBINED=$(( RSS1 + RSS2 ))
    LINE="${ELAPSED}s      ${RSS1}MB       ${RSS2}MB       ${COMBINED}MB"
    [[ $RSS2 -gt $PEAK2 ]] && PEAK2=$RSS2
    [[ $COMBINED -gt $PEAK_COMBINED ]] && PEAK_COMBINED=$COMBINED
    TOTAL2=$(( TOTAL2 + RSS2 ))
    TOTAL_COMBINED=$(( TOTAL_COMBINED + COMBINED ))
  fi

  [[ $RSS1 -gt $PEAK1 ]] && PEAK1=$RSS1
  TOTAL1=$(( TOTAL1 + RSS1 ))
  SAMPLES=$(( SAMPLES + 1 ))

  echo "$LINE" | tee -a "$REPORT_FILE"
  sleep "$INTERVAL"
done

# Compute averages (integer division)
AVG1=$(( SAMPLES > 0 ? TOTAL1 / SAMPLES : 0 ))

{
  echo ""
  echo "====================================================="
  echo " SUMMARY"
  echo "====================================================="
  echo " Scenarios        : $SCENARIO"
  echo " Samples          : $SAMPLES"
  echo ""
  echo " Process 1 (PID $PID1)"
  echo "   Peak RSS       : ${PEAK1} MB"
  echo "   Avg RSS        : ${AVG1} MB"

  if [[ -n "$PID2" ]]; then
    AVG2=$(( SAMPLES > 0 ? TOTAL2 / SAMPLES : 0 ))
    AVG_COMBINED=$(( SAMPLES > 0 ? TOTAL_COMBINED / SAMPLES : 0 ))
    echo ""
    echo " Process 2 (PID $PID2)"
    echo "   Peak RSS       : ${PEAK2} MB"
    echo "   Avg RSS        : ${AVG2} MB"
    echo ""
    echo " Combined"
    echo "   Peak RSS       : ${PEAK_COMBINED} MB"
    echo "   Avg RSS        : ${AVG_COMBINED} MB"
    EFFECTIVE_PEAK=$PEAK_COMBINED
  else
    EFFECTIVE_PEAK=$PEAK1
  fi

  ESTIMATED_CLOUD=$(( EFFECTIVE_PEAK + STREAMLIT_OVERHEAD_MB ))
  echo ""
  echo "====================================================="
  echo " CAPACITY VERDICT vs Streamlit 1 GB"
  echo "====================================================="
  echo " Local peak       : ${EFFECTIVE_PEAK} MB"
  echo " + Cloud overhead : ${STREAMLIT_OVERHEAD_MB} MB (estimated)"
  echo " Estimated Cloud  : ${ESTIMATED_CLOUD} MB / ${CAPACITY_MB} MB"
  HEADROOM=$(( CAPACITY_MB - ESTIMATED_CLOUD ))
  echo " Headroom         : ${HEADROOM} MB"
  echo ""

  if [[ $ESTIMATED_CLOUD -le $CAUTION_THRESHOLD_MB ]]; then
    echo " VERDICT          : ✅ SAFE — well within 1 GB limit"
  elif [[ $ESTIMATED_CLOUD -le $UNSAFE_THRESHOLD_MB ]]; then
    echo " VERDICT          : ⚠️  CAUTION — approaching limit, monitor closely"
  else
    echo " VERDICT          : 🔴 UNSAFE — likely to exceed 1 GB under Cloud conditions"
  fi

  echo "====================================================="
  echo " Report saved to: $REPORT_FILE"
  echo "====================================================="
} | tee -a "$REPORT_FILE"
