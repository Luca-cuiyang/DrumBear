cmake_minimum_required(VERSION 3.24)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(midi_converter LANGUAGES CXX)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(midi-converter
    midi_converter.cpp
)

if(MSVC)
    target_compile_options(midi-converter PRIVATE /W4 /permissive-)
else()
    target_compile_options(midi-converter PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(DEFINED MUSE_APP_INSTALL_RESOURCES_LOCATION)
    install(TARGETS midi-converter
        RUNTIME DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}/plugins/midi_converter
    )
else()
    install(TARGETS midi-converter RUNTIME DESTINATION tools)
endif()

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        add_test(
            NAME midi_converter_tests
            COMMAND ${Python3_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_midi_converter.py
                    $<TARGET_FILE:midi-converter>
        )
    endif()
endif()
