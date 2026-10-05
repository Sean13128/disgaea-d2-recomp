#!/bin/bash
# Distinct completed guest frames, never drawable/presentation counts.
# X_HEADLESS=1 X_FIFO_ONLY=1 isolates guest timing; real Metal is the default.
set -euo pipefail
cd "$(dirname "$0")/.."
seconds=${X_SECONDS:-40}
if [[ ! "$seconds" =~ ^[0-9]+$ ]] || (( seconds < 40 )); then
  echo 'X_SECONDS must be >=40'; exit 1
fi
stage=${D2_WARP_STAGE:-1}
if [[ ! "$stage" =~ ^[0-9]{1,5}$ ]] || (( 10#$stage < 1 || 10#$stage > 65535 )); then
  echo 'D2_WARP_STAGE must be 1..65535'; exit 1
fi
stage=$((10#$stage)); if (( stage < 100 )); then stage=$((stage + 100)); fi
out=$(mktemp -d "$PWD/port/runs/X-host.XXXXXX")
scratch=$(mktemp -d /Volumes/Data/ai-tmp/codex/d2-X.XXXXXX)
printf '%s\n' "$scratch" > "$out/scratch.txt"
mkdir -p "$scratch/hdd0" "$scratch/hdd1"
cp -R port/hdd0/. "$scratch/hdd0/"
if [[ ${X_SKIP_BUILD:-0} != 1 ]]; then
  (cd port; cmake -B build-x -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp \
    -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include) > "$out/configure.log" 2>&1
  cmake --build port/build-x --target DisgaeaD2Recomp -j 4 > "$out/build.log" 2>&1
fi
unset PS3RECOMP_METAL_HEADLESS PS3RECOMP_RSX_FIFO_ONLY PAD_FILE PAD_SCRIPT D2_DRAW_TRACE
unset PS3RECOMP_METAL_FRAME_DUMP PS3RECOMP_METAL_OVERLAY_CAPTURE
if [[ ${X_HEADLESS:-0} == 1 ]]; then export PS3RECOMP_METAL_HEADLESS=1; fi
if [[ ${X_FIFO_ONLY:-0} == 1 ]]; then export PS3RECOMP_RSX_FIFO_ONLY=1; fi
pad='10:0x4000,14:0x4000'
for ((t=22; t<seconds; t+=4)); do pad="$pad,$t:0x4000"; done
logfile="$out/run.log"
status=0
PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" \
PS3_HDD0_ROOT="$scratch/hdd0" PS3_HDD1_ROOT="$scratch/hdd1" \
D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 \
D2_WARP_STAGE="$stage" D2_BOOT_TRACE=1 GCM_FLIP_TRACE=1 GCM_FLIPCOUNT=1 \
PS3_HOST_CPU=1 PAD_SCRIPT="${X_PAD_SCRIPT:-$pad}" \
  perl -e 'alarm shift; exec @ARGV' "$seconds" \
  "${X_BINARY:-./port/build-x/DisgaeaD2Recomp}" work/EBOOT.elf > "$logfile" 2>&1 || status=$?
printf 'Log: %s\nExit: %s (142 is the expected alarm)\n' "$logfile" "$status" | tee "$out/summary.txt"
grep -nE '\[D2-warp\]|\[gcm-rate\]|\[HOSTCPU\]|LOAD complete|backend init|FIFO timing' \
  "$logfile" > "$out/metrics.txt" || true
if [[ "$status" != 142 ]]; then
  echo 'FAIL: game exited before the alarm; inspect run.log' | tee -a "$out/summary.txt"; exit 1
fi
if [[ ${X_HEADLESS:-0} != 1 ]] && ! grep -q '\[rsx\] Metal backend init OK' "$logfile"; then
  echo 'FAIL: real Metal unavailable; X_HEADLESS=1 X_FIFO_ONLY=1 only measures guest timing' | tee -a "$out/summary.txt"; exit 1
fi
if ! grep -q 'LOAD complete for.*NPUB31321_NORMAL_00' "$logfile" \
  || ! grep -q '\[D2-warp\] confirm stage=' "$logfile"; then
  echo 'FAIL: Continue/warp did not complete; inspect run.log' | tee -a "$out/summary.txt"; exit 1
fi
awk -v stage="$stage" '
function value(key,   i,a) {for(i=1;i<=NF;i++) {split($i,a,"="); if(a[1]==key) return a[2]} return ""}
function latency(name, a, b,   dt) {dt=(b-a)/1e6; total[name]+=dt; counts[name]++; if(dt>maximum[name])maximum[name]=dt}
/\[D2-warp\] stage=/ && value("map_id")+0==stage && value("stage")+0>0 {
  if(!battle) {battle=1; settle=last_time+5e9}
}
/\[gcm-fifo-flip\]/ {
  ea=value("ea"); event=value("event");
  if(event=="submit") {fifo_time[ea]=value("time_ns")+0; fifo_tick[ea]=value("vblank")+0}
  if(event=="reach") {
    seq=value("seq")+0;
    if(battle && fifo_time[ea]>=settle) {submit[seq]=fifo_time[ea]; submit_tick[seq]=fifo_tick[ea]}
    delete fifo_time[ea]; delete fifo_tick[ea];
  }
}
/\[gcm-submit\]/ {if(battle && last_time>=settle) {submits++; if(value("put")!=value("get"))undrained++}}
/\[gcm-flip\]/ {
  seq=value("seq")+0; t=value("time_ns")+0; v=value("vblank")+0; event=value("event"); last_time=t;
  if(!battle || t<settle) next;
  if(event=="submit") {
    submit[seq]=t; submit_tick[seq]=v;
    if(previous_wake_seq==seq-1) latency("wake_next_submit",previous_wake,t);
  }
  if(event=="reach") reach[seq]=t;
  if(event=="select") selected[seq]=t;
  if(event=="retire") {
    if(seen[seq]++) {duplicate++; next}
    if(n && v==previous_tick) overcap++;
    if(!n) {first=t; first_tick=v}
    n++; last=t; last_tick=v; previous_tick=v; retired[seq]=t;
    if(submit[seq]) {
      latency("submit_reach",submit[seq],reach[seq]);
      latency("reach_select",reach[seq],selected[seq]);
      latency("select_retire",selected[seq],t);
      latency("submit_retire",submit[seq],t);
      ticks=v-submit_tick[seq]; hist[ticks]++; matched++;
    }
  }
  if(event=="wake" && retired[seq]) {
    previous_wake_seq=seq; previous_wake=t;
    latency("retire_wake",retired[seq],t);
    delete submit[seq]; delete submit_tick[seq]; delete reach[seq];
    delete selected[seq]; delete retired[seq];
  }
}
END {
  if(n<300 || last<=first) {print "FAIL: insufficient steady battle frames (need >=300 after settling)"; exit 1}
  duration=(last-first)/1e9; fps=(n-1)/duration; vb=last_tick-first_tick;
  printf "Battle %d: %.3f distinct guest flips/s vs %.3f vblanks/s; %d flips / %d vblanks over %.3fs\n",stage,fps,vb/duration,n-1,vb,duration;
  printf "RESC/direct submissions with undrained FIFO: %d / %d\n",undrained,submits;
  for(name in counts) printf "%s: mean %.3f ms, max %.3f ms (%d frames)\n",name,total[name]/counts[name],maximum[name],counts[name];
  printf "Retirement tick minus submission tick: 1=%d 2=%d later=%d\n",hist[1],hist[2],matched-hist[1]-hist[2];
  if(overcap || duplicate) {printf "FAIL: duplicate sequences=%d, multiple distinct flips in one vblank=%d\n",duplicate,overcap; exit 1}
  if(fps<58.5 || fps>60.2) {print "FAIL: battle below the native 60-flip target; use latency breakdown to locate misses"; exit 1}
  print "PASS: native 60-flip battle cadence, one distinct guest flip per vblank at most"
}' "$logfile" | tee -a "$out/summary.txt"
if [[ ${X_HEADLESS:-0} == 1 ]]; then
  echo 'Headless results do not verify visible Metal speed.' | tee -a "$out/summary.txt"
fi
printf 'Copied save retained: %s\n' "$scratch"
