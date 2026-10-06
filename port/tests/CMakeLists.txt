cmake_minimum_required(VERSION 3.20)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(D2Regressions C)
    include(CTest)
    if(NOT DEFINED PS3RECOMP_DIR)
        get_filename_component(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../ps3recomp" ABSOLUTE)
    endif()
endif()
find_package(Python3 COMPONENTS Interpreter REQUIRED)
foreach(test IN ITEMS AN-summary AN-flags AN-metal AN-location-100 AN-location-140)
    if(APPLE OR test STREQUAL "AN-summary" OR test MATCHES "AN-location")
        add_test(NAME d2.${test} COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
        set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
        if(test STREQUAL "AN-metal")
            set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;gpu" SKIP_RETURN_CODE 77)
        endif()
    endif()
endforeach()
if(NOT WIN32)
    add_executable(d2_guest_poll_filter
        "${PS3RECOMP_DIR}/runtime/platform/tests/test_guest_poll_filter.c")
    target_compile_features(d2_guest_poll_filter PRIVATE c_std_17)
    target_compile_options(d2_guest_poll_filter PRIVATE -UNDEBUG)
    target_link_libraries(d2_guest_poll_filter PRIVATE pthread)
    add_test(NAME d2.guest-poll-filter COMMAND d2_guest_poll_filter)
    set_tests_properties(d2.guest-poll-filter PROPERTIES LABELS "asset-free;cpu" TIMEOUT 30)
endif()
# AT: Item Editor record/validation/icon/action-queue logic against a mock guest.
if(CMAKE_CXX_COMPILER_LOADED)
    add_executable(d2_at_items AT.items-test.cpp ../src/d2_items.cpp)
    target_compile_features(d2_at_items PRIVATE cxx_std_17)
    target_compile_definitions(d2_at_items PRIVATE D2_ITEMS_TEST)
    target_compile_options(d2_at_items PRIVATE -UNDEBUG)
    add_test(NAME d2.AT-items COMMAND d2_at_items)
    set_tests_properties(d2.AT-items PROPERTIES LABELS "asset-free;cpu" TIMEOUT 60)
endif()
set(D2_CPU_TESTS Q-sync T-sync Y-sync AA-sync AB-sync AG2-fifo
    draw AG2-engine hash vertex cache audio-clock AP-atrac-stream AP-audio-gain AP-audio-init filesystem edat save-import
    savedata-io savedata-fixed overlay system-overlay editor-100 editor-140
    guest-poll spu-vectors spu-shuffle spu-cache spu-lanes repro-guards)
foreach(test IN LISTS D2_CPU_TESTS)
    add_test(NAME d2.${test}
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
    set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;cpu" TIMEOUT 120)
endforeach()
if(APPLE)
    foreach(test IN ITEMS metal metal-overlay hotkey AS-ui)
        add_test(NAME d2.${test}
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
                "${test}" --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/${test}")
        set_tests_properties(d2.${test} PROPERTIES LABELS "asset-free;gpu" SKIP_RETURN_CODE 77 TIMEOUT 120)
    endforeach()
endif()

if(APPLE)
    set_tests_properties(d2.hotkey d2.AS-ui PROPERTIES LABELS "asset-free;host-ui")
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
if(APPLE AND TARGET ps3recomp_runtime AND D2_GAME_VERSION STREQUAL "140")
    add_test(NAME d2.AQ-fill
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            AQ-fill --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/AQ-fill"
            --runtime "$<TARGET_FILE:ps3recomp_runtime>" --lift "${RECOMP_DIR}")
    set_tests_properties(d2.AQ-fill PROPERTIES LABELS "asset-free;cpu" TIMEOUT 300)
    add_test(NAME d2.AR-shader
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
            AR-shader --sdk "${PS3RECOMP_DIR}" --work "${CMAKE_CURRENT_BINARY_DIR}/AR-shader"
            --runtime "$<TARGET_FILE:ps3recomp_runtime>" --lift "${RECOMP_DIR}")
    set_tests_properties(d2.AR-shader PROPERTIES LABELS "asset-free;cpu" TIMEOUT 300)
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

# Active SDK sysPrxForUser context-handler lwcond regression (no game assets).
if(NOT WIN32 AND CMAKE_CXX_COMPILER_LOADED)
    add_executable(d2_lwcond "${PS3RECOMP_DIR}/runtime/ppu/tests/test_lwcond.cpp"
        "${PS3RECOMP_DIR}/runtime/platform/win32_compat.c")
    target_include_directories(d2_lwcond PRIVATE "${RECOMP_DIR}" "${PS3RECOMP_DIR}/include")
    target_compile_features(d2_lwcond PRIVATE cxx_std_17)
    target_compile_definitions(d2_lwcond PRIVATE PS3_LWCOND_TEST)
    target_compile_options(d2_lwcond PRIVATE -UNDEBUG -ffunction-sections -fdata-sections)
    if(APPLE)
        target_link_options(d2_lwcond PRIVATE -Wl,-dead_strip)
    else()
        target_link_options(d2_lwcond PRIVATE -Wl,--gc-sections)
    endif()
    target_link_libraries(d2_lwcond PRIVATE pthread)
    add_test(NAME d2.lwcond COMMAND d2_lwcond)
    add_test(NAME d2.lwcond-poll COMMAND d2_lwcond poll)
    set_tests_properties(d2.lwcond d2.lwcond-poll PROPERTIES LABELS "asset-free;cpu" TIMEOUT 30)
    set_tests_properties(d2.lwcond PROPERTIES ENVIRONMENT "PS3_LWCOND_POLL=0")
    set_tests_properties(d2.lwcond-poll PROPERTIES ENVIRONMENT "PS3_LWCOND_POLL=1")
endif()

# AY: the SDK compatibility suite, including multi-wait routing diagnostics.
if(NOT WIN32)
    add_executable(d2_ay_compat
        "${PS3RECOMP_DIR}/runtime/platform/tests/test_win32_compat.c"
        "${PS3RECOMP_DIR}/runtime/platform/win32_compat.c")
    target_compile_features(d2_ay_compat PRIVATE c_std_17)
    target_compile_definitions(d2_ay_compat PRIVATE PS3_MULTIWAIT_TEST)
    target_compile_options(d2_ay_compat PRIVATE -UNDEBUG)
    target_link_libraries(d2_ay_compat PRIVATE pthread ${CMAKE_DL_LIBS})
    add_test(NAME d2.AY-compat COMMAND d2_ay_compat)
    add_test(NAME d2.AY-compat-broadcast COMMAND d2_ay_compat)
    set_tests_properties(d2.AY-compat-broadcast PROPERTIES LABELS "asset-free;cpu"
        TIMEOUT 30 ENVIRONMENT "PS3_MULTIWAIT_BROADCAST=1")
    set_tests_properties(d2.AY-compat PROPERTIES LABELS "asset-free;cpu" TIMEOUT 30)
endif()
if(CMAKE_CXX_COMPILER_LOADED)
    add_executable(d2_ay_qos AY.qos-test.cpp ../stubs.cpp)
    target_include_directories(d2_ay_qos PRIVATE "${PS3RECOMP_DIR}/include")
    target_compile_features(d2_ay_qos PRIVATE cxx_std_17)
    target_compile_options(d2_ay_qos PRIVATE -UNDEBUG)
    add_test(NAME d2.AY-qos COMMAND d2_ay_qos)
    set_tests_properties(d2.AY-qos PROPERTIES LABELS "asset-free;cpu" TIMEOUT 10)
endif()
