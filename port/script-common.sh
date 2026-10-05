# Shared build/version selection. Call from the project root.
d2_prepare() {
    build=${D2_BUILD_DIR:-port/build}
    runs=${D2_RUNS_DIR:-port/runs}
    mkdir -p "$runs" || return
    cmake --build "$build" -j6 > "$runs/build.log" 2>&1 || {
        tail -30 "$runs/build.log"; return 1;
    }
    version=$(sed -n 's/^D2_GAME_VERSION:STRING=//p' "$build/CMakeCache.txt")
    case "$version" in
        100) elf=work/EBOOT.elf ;;
        140) elf=work/v140/EBOOT.elf ;;
        *) echo "Invalid/missing D2_GAME_VERSION in $build" >&2; return 1 ;;
    esac
    elf=${D2_EBOOT:-$elf}
    test -f "$elf" || { echo "Missing executable: $elf" >&2; return 1; }
}
# SIGALRM is an intentional diagnostic timeout; retain its status (128 + 14).
d2_result() {
    case "$1" in
        0) echo "Completed: $2" ;;
        142) echo "Diagnostic timeout (SIGALRM): $2" ;;
        *) echo "Runner failed (exit $1): $2" >&2 ;;
    esac
    return "$1"
}
