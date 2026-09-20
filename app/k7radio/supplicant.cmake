include(${CMAKE_CURRENT_LIST_DIR}/hostap/sources.cmake)
set(SKW_SUPPLICANT_SOURCES skw_supplicant.c skw_supplicant_os.c ${SKW_HOSTAP_SOURCES})
set_source_files_properties(${SKW_SUPPLICANT_SOURCES} PROPERTIES COMPILE_DEFINITIONS
 "CONFIG_NO_STDOUT_DEBUG;CONFIG_NO_WPA_MSG;CONFIG_NO_RANDOM_POOL;CONFIG_NO_RC4;CONFIG_NO_TKIP;CONFIG_SHA256;CONFIG_IEEE80211W;CONFIG_CRYPTO_INTERNAL;CONFIG_INTERNAL_AES;CONFIG_INTERNAL_SHA1;CONFIG_INTERNAL_SHA256;CONFIG_INTERNAL_MD5;bswap_16=__builtin_bswap16;bswap_32=__builtin_bswap32;bswap_64=__builtin_bswap64")
# Upstream debug-only locals remain when its no-stdout configuration is used.
set_source_files_properties(${SKW_HOSTAP_SOURCES} PROPERTIES COMPILE_OPTIONS "-Wno-unused-but-set-variable")
include_directories(${CMAKE_CURRENT_LIST_DIR}/hostap ${CMAKE_CURRENT_LIST_DIR}/hostap/utils)
