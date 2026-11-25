#!/bin/sh
# Which libraries does the unpacked ALMP folder still need from the system?  sh ldd_check.sh <ALMP folder>
# Prints each missing soname once, with how many files need it and one example file.
cd "$1" || exit 1
for f in ALMP $(find . -name "*.so*" -type f); do
  ldd "$f" 2>/dev/null | grep "not found" | while read -r lib rest; do echo "$lib $f"; done
done | sort | awk '{n[$1]++; if (!($1 in ex)) ex[$1]=$2} END {for (l in n) printf "%3d  %-28s e.g. %s\n", n[l], l, ex[l]}' | sort -k2
echo "ldd check done"
