if(COMMAND nuttx_add_application)
  if(CONFIG_APP_VOICELINK)
    nuttx_add_application(
      NAME ${CONFIG_APP_VOICELINK_PROGNAME}
      PRIORITY ${CONFIG_APP_VOICELINK_PRIORITY}
      STACKSIZE ${CONFIG_APP_VOICELINK_STACKSIZE}
      MODULE ${CONFIG_APP_VOICELINK}
      SRCS
        src/main.cpp
        src/core.cpp
        src/parsers.cpp
        src/platform_openvela.cpp
        src/board_hooks_k7.c
        src/speech_engine_k7.cpp
      INCLUDE_DIRECTORIES ${CMAKE_CURRENT_LIST_DIR}/include)
  endif()
  return()
endif()

cmake_minimum_required(VERSION 3.16)
project(openvela_voicelink VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(VOICELINK_BUILD_TESTS "Build host unit tests" ON)

add_library(voicelink_core
    src/core.cpp
    src/parsers.cpp
)
target_include_directories(voicelink_core PUBLIC include)
target_compile_options(voicelink_core PRIVATE -Wall -Wextra -Wpedantic)

include(CTest)
if(BUILD_TESTING AND VOICELINK_BUILD_TESTS)
  enable_testing()
  set(VOICELINK_TESTS
      tests/test_parsers.cpp
      tests/test_wake_word.cpp
      tests/test_network_selection.cpp
      tests/test_password.cpp
      tests/test_io_status.cpp
  )
  foreach(src ${VOICELINK_TESTS})
    get_filename_component(name ${src} NAME_WE)
    add_executable(${name} ${src})
    target_link_libraries(${name} PRIVATE voicelink_core)
    target_compile_options(${name} PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME ${name} COMMAND ${name})
  endforeach()
endif()
