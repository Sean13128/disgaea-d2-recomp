# Keep the CLI runner intact; Finder launches a small AppKit path resolver.
enable_language(OBJC)
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
add_executable(DisgaeaD2App MACOSX_BUNDLE src/d2_launcher.m "${D2_ICON}")
target_include_directories(DisgaeaD2App PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_options(DisgaeaD2App PRIVATE -fobjc-arc)
target_link_libraries(DisgaeaD2App PRIVATE "-framework AppKit")
set_target_properties(DisgaeaD2App PROPERTIES
    OUTPUT_NAME "Disgaea D2"
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/src/d2_Info.plist.in")
configure_file(src/d2_package.cmake.in d2_package.cmake @ONLY)
# An ALL target also refreshes the bundle when only the runtime was rebuilt.
add_custom_target(DisgaeaD2Dist ALL
    COMMAND "${CMAKE_COMMAND}"
        "-DAPP=$<TARGET_BUNDLE_DIR:DisgaeaD2App>"
        "-DRUNNER=$<TARGET_FILE:${PROJECT_NAME}>"
        -P "${CMAKE_CURRENT_BINARY_DIR}/d2_package.cmake"
    DEPENDS DisgaeaD2App ${PROJECT_NAME}
    COMMENT "Bundling runtime and dylibs into port/dist/Disgaea D2.app")
