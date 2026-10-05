cmake_minimum_required(VERSION 3.20)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(D2Regressions NONE)
    include(CTest)
    if(NOT DEFINED PS3RECOMP_DIR)
        get_filename_component(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../ps3recomp" ABSOLUTE)
    endif()
endif()
find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(D2_CPU_TESTS Q-sync T-sync Y-sync AA-sync AB-sync AG2-fifo
    draw AG2-engine hash vertex cache audio-clock filesystem edat save-import
    savedata-io savedata-fixed overlay system-overlay editor-100 editor-140
    guest-poll spu-vectors spu-shuffle repro-guards)
foreach(test IN LISTS D2_CPU_TESTS)
    add_test(NAME d2.${test}
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
    set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
endforeach()
if(APPLE)
    foreach(test IN ITEMS metal metal-overlay hotkey)
        add_test(NAME d2.${test}
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
                "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
        set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;gpu" SKIP_RETURN_CODE 77 TIMEOUT 120)
    endforeach()
endif()

if(APPLE)
    set_tests_properties(d2.hotkey PROPERTIES LABELS "asset-free;host-ui")
endif()

# Failure fixtures supplied by newer SDK exports; the pinned baseline predates them.
foreach(spec IN ITEMS "savedata-transaction|libs/system/tests/test_savedata_transaction.c"
                      "edat-cache|libs/filesystem/tests/test_edat_cache.py")
    string(REPLACE "|" ";" parts "${spec}")
    list(GET parts 0 test)
    list(GET parts 1 fixture)
    if(EXISTS "${PS3RECOMP_DIR}/${fixture}")
        add_test(NAME d2.${test}
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
                "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
        set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
    endif()
endforeach()
if(APPLE AND TARGET ps3recomp_runtime AND EXISTS "${PS3RECOMP_DIR}/runtime/ppu/tests/test_loader_validation.cpp")
    add_test(NAME d2.loader-validation
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            loader-validation --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/loader-validation"
            --runtime "$<TARGET_FILE:ps3recomp_runtime>")
    set_tests_properties(d2.loader-validation PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
endif()
if(APPLE AND TARGET DisgaeaD2Recomp AND D2_GAME_VERSION STREQUAL "140" AND EXISTS "${PS3RECOMP_DIR}/runtime/ppu/tests/test_runner_failures.py")
    add_test(NAME d2.runner-failures
        COMMAND "${Python3_EXECUTABLE}" "${PS3RECOMP_DIR}/runtime/ppu/tests/test_runner_failures.py"
            "$<TARGET_FILE:DisgaeaD2Recomp>" "${CMAKE_CURRENT_BINARY_DIR}/runner-failures")
    set_tests_properties(d2.runner-failures PROPERTIES LABELS "asset-free;cpu" TIMEOUT 60
        ENVIRONMENT "D2_TEST_TMPDIR=${CMAKE_CURRENT_BINARY_DIR}")
endif()

file(READ "${PS3RECOMP_DIR}/runtime/platform/guest_poll.c" D2_TEST_POLL_SOURCE)
if(D2_TEST_POLL_SOURCE MATCHES "ps3_guest_workers_request_stop")
    foreach(test IN ITEMS lifecycle save-stop scripts metal)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/AL.${test}-test.c" OR
           EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/AL.${test}-test.py" OR
           (APPLE AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/AL.${test}-test.m"))
            add_test(NAME d2.AL-${test}
                COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
                    AL-${test} --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/AL-${test}")
            set_tests_properties(d2.AL-${test} PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
            if(test STREQUAL "metal")
                set_tests_properties(d2.AL-${test} PROPERTIES LABELS "asset-free;gpu" SKIP_RETURN_CODE 77)
            endif()
        endif()
    endforeach()
endif()
