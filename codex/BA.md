# Task BA — clean profiling build (yourname = BA, build dir port/build-ba)

Build only. Do NOT modify any source, patch, or SDK file.

1. Configure port/build-ba exactly like port/build in OPERATIONS.md (Release, version 140), e.g.:
   cmake -S port -B port/build-ba -G Ninja -DCMAKE_BUILD_TYPE=Release -DPS3RECOMP_DIR=../ps3recomp -DRECOMP_DIR=src/recomp-140 -DD2_GAME_VERSION=140 -DPython3_EXECUTABLE="$PWD/.venv/bin/python" -DCMAKE_{C,CXX,OBJC,OBJCXX}_FLAGS=-I/opt/homebrew/include
   (Use the OPERATIONS.md line if it differs.) Logs to port/runs/BA-configure.log, port/runs/BA-build.log.
2. cmake --build port/build-ba -j 4
3. ctest --test-dir port/build-ba --output-on-failure -j 2 > port/runs/BA-ctest.log
4. Record: git rev-parse HEAD for root and ps3recomp, `git -C ps3recomp diff --stat`, and shasum -a 256 of port/build-ba/DisgaeaD2Recomp into port/runs/BA-build-info.txt.

Report: build OK?, ctest pass count, binary sha256. Write codex/BA.report.md.
