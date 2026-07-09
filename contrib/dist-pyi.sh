#!/bin/bash

# error while loading shared libraries: libz.so.1: failed to map segment from shared object
# https://stackoverflow.com/questions/57796839/docker-compose-error-while-loading-shared-libraries-libz-so-1-failed-to-map-s
# Got it solved by re-mounting the /tmp to give the volume permission to execute (it was accessible with read-only)
# Configuring a user specific TMPDIR directory solves the problem
# --runtime-tmpdir="./tmp"

main_file=contrib/pyi.py
exe_name=bookmarks-curses

log="$(realpath "$0")".tmp
[[ -f $log ]] && rm -f "$log"

main2() {
    if [[ ! $(command -v pyinstaller) ]]; then
        echo "pyinstaller not found" | tee -a "$log"
        return 1
    fi

    local i
    for i in dist build; do
        [[ -d $i ]] && rm -rf "$i"
    done

    lib=$(find .venv/lib -type d -name 'site-packages' -print -quit)
    if [[ ! -d $lib ]]; then
        echo "dir not found: .venv/lib/...site-packages/" | tee -a "$log"
        return 1
    fi
    export PYTHONPATH="$lib"

    echo "---------------------" >>"$log"
    echo "pyinstaller $main_file ..." | tee -a "$log"
    echo >>"$log"
    local opts=(
        --specpath=tmp
        --workpath=tmp
        --noupx
        --runtime-tmpdir="./tmp"
        --name="$exe_name"
        -F
        "$main_file"
    )
    pyinstaller "${opts[@]}" &>>"$log"
}

main() {
    (
        # out of contrib/
        cd "$(dirname "$0")"/.. || exit 1
        main2
    )
}

main
