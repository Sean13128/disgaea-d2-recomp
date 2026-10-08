if(D2_APPEARANCE_IMPORTER)
    target_sources(${PROJECT_NAME} PRIVATE src/d2_appearance_ui.m)
    set_source_files_properties(src/d2_appearance_ui.m PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
endif()
target_link_options(${PROJECT_NAME} PRIVATE "LINKER:-U,_d2_appearance_menu_install" "LINKER:-U,_d2_appearance_frame")
# Keep the CLI runner intact; Finder launches a small AppKit path resolver.
enable_language(OBJC)
target_sources(${PROJECT_NAME} PRIVATE src/d2_settings.m src/d2_cheats_ui.m src/d2_diagnostics.m)
set_source_files_properties(src/d2_diagnostics.m PROPERTIES COMPILE_OPTIONS "-fobjc-arc;-UNDEBUG")
# Mach-O needs an explicitly optional undefined symbol for an unlinked cheat UI.
target_link_options(${PROJECT_NAME} PRIVATE "LINKER:-U,_d2_cheats_menu_install" "LINKER:-U,_d2_item_editor_show")
set_source_files_properties(src/d2_cheats_ui.m PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
set_source_files_properties(src/d2_settings.m PROPERTIES
    COMPILE_OPTIONS "-fobjc-arc;-UNDEBUG"
    INCLUDE_DIRECTORIES "${CMAKE_CURRENT_BINARY_DIR};${PS3RECOMP_DIR}/libs/video;${PS3RECOMP_DIR}/libs/audio")
set(D2_GAME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../Disgaea D2 A Brighter Darkness - [BLUS31313]"
    CACHE PATH "Game dump used to generate the local app icon (never bundled)")
set(D2_ICON "${CMAKE_CURRENT_BINARY_DIR}/DisgaeaD2.icns")
add_custom_command(OUTPUT "${D2_ICON}"
    COMMAND /bin/bash "${CMAKE_CURRENT_SOURCE_DIR}/src/d2_icon.sh"
            "${D2_GAME_ROOT}/PS3_GAME/ICON0.PNG" "${D2_ICON}"
    DEPENDS "${D2_GAME_ROOT}/PS3_GAME/ICON0.PNG" src/d2_icon.sh
    COMMENT "Generating Disgaea D2 app icon from the local dump")
set_source_files_properties("${D2_ICON}" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
configure_file(src/d2_launcher_paths.h.in d2_launcher_paths.h @ONLY)
set_source_files_properties(src/d2_install_content.py PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
set(D2_SAVE_IMPORT "${CMAKE_CURRENT_SOURCE_DIR}/../tools/d2_save_import.py")
set_source_files_properties("${D2_SAVE_IMPORT}" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
add_executable(DisgaeaD2App MACOSX_BUNDLE src/d2_launcher.m "${D2_ICON}" "${D2_SAVE_IMPORT}" src/d2_install_content.py)
target_include_directories(DisgaeaD2App PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_options(DisgaeaD2App PRIVATE -fobjc-arc)
target_link_libraries(DisgaeaD2App PRIVATE "-framework AppKit")
set_target_properties(DisgaeaD2App PROPERTIES
    OUTPUT_NAME "Disgaea D2"
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/src/d2_Info.plist.in")
get_filename_component(D2_BUILD_NAME "${CMAKE_CURRENT_BINARY_DIR}" NAME)
if(CMAKE_CURRENT_BINARY_DIR STREQUAL "${CMAKE_CURRENT_SOURCE_DIR}/build"
   AND D2_GAME_VERSION STREQUAL "140" AND CMAKE_BUILD_TYPE STREQUAL "Release"
   AND NOT D2_HOST_SANITIZERS)
    set(D2_DIST_DEFAULT "${CMAKE_CURRENT_SOURCE_DIR}/dist")
else()
    string(SHA256 D2_BUILD_ID "${CMAKE_CURRENT_BINARY_DIR}|${CMAKE_BUILD_TYPE}|${D2_HOST_SANITIZERS}")
    string(SUBSTRING "${D2_BUILD_ID}" 0 8 D2_BUILD_ID)
    set(D2_DIST_DEFAULT "${CMAKE_CURRENT_SOURCE_DIR}/dist/${D2_BUILD_NAME}-v${D2_GAME_VERSION}-${D2_BUILD_ID}")
endif()
set(D2_DIST_DIR "" CACHE PATH "Optional explicit distribution destination")
if(NOT D2_DIST_DIR)
    set(D2_DIST_DIR "${D2_DIST_DEFAULT}")
endif()
add_executable(DisgaeaD2Publish EXCLUDE_FROM_ALL src/d2_publish.c)
configure_file(src/d2_package.cmake.in d2_package.cmake @ONLY)
# Packaging is explicit; ordinary builds never publish a distribution.
add_custom_target(DisgaeaD2Dist
    COMMAND "${CMAKE_COMMAND}"
        "-DAPP=$<TARGET_BUNDLE_DIR:DisgaeaD2App>"
        "-DRUNNER=$<TARGET_FILE:${PROJECT_NAME}>"
        "-DPUBLISH=$<TARGET_FILE:DisgaeaD2Publish>"
        -P "${CMAKE_CURRENT_BINARY_DIR}/d2_package.cmake"
    DEPENDS DisgaeaD2App ${PROJECT_NAME} DisgaeaD2Publish
    COMMENT "Packaging signed app into ${D2_DIST_DIR}")
