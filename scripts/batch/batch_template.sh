#!/bin/bash
# v23 (strip_repeat verify guard): convert every file to scratch, promote nothing.
cd ~/Documents/FMPT-Legends || exit 1
S="$1"; LOG="$S/batch23/log.txt"; : > "$LOG"
for f in "FM 24 XML Files"/*.xml; do
  c=$(basename "$f" | sed 's/^FMPT Legends - //; s/ - Squads - FM24\.xml$//; s/ - FM24\.xml$//')
  echo "=== $c $(date +%H:%M:%S)" >> "$LOG"
  /usr/bin/python3 scripts/convert_edition.py "$f" "$S/batch23/$c.xml" --target-season 2025 \
    --flag-year-only --rebuild-careers --drop-retired-adaptations --rebuild-real-history \
    --names --report "$S/batch23/$c.md" >> "$LOG" 2>&1 \
    && echo "  ok $c" >> "$LOG" || echo "  FAILED $c" >> "$LOG"
done
echo "=== Portugal FM18 $(date +%H:%M:%S)" >> "$LOG"
/usr/bin/python3 scripts/convert_edition.py "FM 18 XML Files/FMPT Legends - Portugal.xml" \
  "$S/batch23/Portugal FM18.xml" --target-season 2025 --flag-year-only --rebuild-careers \
  --drop-retired-adaptations --rebuild-real-history --names \
  --report "$S/batch23/Portugal FM18.md" >> "$LOG" 2>&1 \
  && echo "  ok Portugal FM18" >> "$LOG" || echo "  FAILED Portugal FM18" >> "$LOG"
echo "BATCH DONE" >> "$LOG"
