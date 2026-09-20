cmake_minimum_required(VERSION 3.14)
project(velavision_llama_b0 LANGUAGES C CXX)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
foreach(opt LLAMA_BUILD_COMMON LLAMA_BUILD_TESTS LLAMA_BUILD_EXAMPLES LLAMA_BUILD_SERVER LLAMA_CURL
    GGML_BACKEND_DL GGML_OPENMP GGML_BLAS GGML_LLAMAFILE GGML_CUDA GGML_METAL GGML_VULKAN GGML_RPC
    GGML_SYCL GGML_CANN GGML_MUSA GGML_KOMPUTE GGML_OPENCL GGML_ACCELERATE GGML_CPU_KLEIDIAI
    GGML_NATIVE GGML_AVX GGML_AVX2 GGML_BMI2 GGML_FMA GGML_F16C GGML_CCACHE)
  set(${opt} OFF CACHE BOOL "" FORCE)
endforeach()
set(GGML_CPU ON CACHE BOOL "" FORCE)
add_subdirectory(vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5 llama)
set_property(TARGET ggml PROPERTY SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/candidate/ggml-backend-reg.cpp")
target_include_directories(ggml PRIVATE vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/src)
# Upstream adds these on Linux even when GGML_BACKEND_DL is off.
foreach(prop LINK_LIBRARIES INTERFACE_LINK_LIBRARIES)
  get_target_property(items ggml ${prop})
  list(REMOVE_ITEM items dl stdc++fs "$<LINK_ONLY:dl>" "$<LINK_ONLY:stdc++fs>")
  set_property(TARGET ggml PROPERTY ${prop} "${items}")
endforeach()
add_executable(b0-probe probe/b0.c)
set_property(TARGET b0-probe PROPERTY C_STANDARD 11)
target_compile_options(b0-probe PRIVATE -Wall -Wextra -Werror -pedantic)
target_link_libraries(b0-probe PRIVATE llama ggml-cpu)
set_property(TARGET b0-probe PROPERTY LINKER_LANGUAGE CXX)
