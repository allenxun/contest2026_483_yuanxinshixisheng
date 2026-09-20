if(CONFIG_EXAMPLES_K7SOUND)
  nuttx_add_application(NAME k7sound SRCS k7sound_main.c live.c i2c3_timing.c codec_duplex.c pio.c platform.c
    STACKSIZE 8192 PRIORITY 100 MODULE ${CONFIG_EXAMPLES_K7SOUND})
endif()
