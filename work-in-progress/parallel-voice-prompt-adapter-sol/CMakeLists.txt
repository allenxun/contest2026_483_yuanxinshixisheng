cmake_minimum_required(VERSION 3.16)
project(voice_prompt_adapter_host LANGUAGES CXX)
add_executable(voice_prompt_adapter_test
  voice_prompt_adapter.cpp
  test_voice_prompt_adapter.cpp)
target_compile_features(voice_prompt_adapter_test PRIVATE cxx_std_17)
if(MSVC)
  target_compile_options(voice_prompt_adapter_test PRIVATE /W4 /WX)
else()
  target_compile_options(voice_prompt_adapter_test PRIVATE -Wall -Wextra -Werror -pedantic)
endif()
