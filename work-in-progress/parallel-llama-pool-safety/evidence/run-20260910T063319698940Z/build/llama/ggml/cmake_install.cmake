# Install script for directory: E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "C:/Program Files (x86)/velavision_pool_safety")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "D:/software/mingw64/mingw64/bin/objdump.exe")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/src/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE STATIC_LIBRARY FILES "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/src/ggml.a")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE FILES
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-cpu.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-alloc.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-backend.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-blas.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-cann.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-cpp.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-cuda.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-kompute.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-opt.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-metal.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-rpc.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-sycl.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/ggml-vulkan.h"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/include/gguf.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE STATIC_LIBRARY FILES "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/src/ggml-base.a")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/ggml" TYPE FILE FILES
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/ggml-config.cmake"
    "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/ggml-version.cmake"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "E:/openvela/VelaVision/work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063319698940Z/build/llama/ggml/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
