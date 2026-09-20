# Candidate integration helper. The eventual owning app calls:
#   vv_add_https_client(apps_<name>)
# after this file is included. Keeping the target explicit avoids creating a
# second NuttX application or a competing network worker.
set(VV_HTTPS_CLIENT_CANDIDATE_DIR ${CMAKE_CURRENT_LIST_DIR})

function(vv_add_https_client owner_target)
  if(NOT CONFIG_VELAVISION_HTTPS_CLIENT_CANDIDATE)
    return()
  endif()
  target_sources(${owner_target} PRIVATE
    ${VV_HTTPS_CLIENT_CANDIDATE_DIR}/src/vv_https_client.c
    ${VV_HTTPS_CLIENT_CANDIDATE_DIR}/src/vv_https_mbedtls.c)
  target_include_directories(${owner_target} PRIVATE
    ${VV_HTTPS_CLIENT_CANDIDATE_DIR}/include)
endfunction()
