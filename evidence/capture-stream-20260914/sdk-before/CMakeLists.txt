if(CONFIG_EXAMPLES_K7SOUND)
  nuttx_add_application(NAME k7sound SRCS k7sound_main.c playback_filter.c duplex.c mmu_command.c command_core.c mmu_probe.c snapshot_arm64.c live.c i2c3_timing.c codec_duplex.c pio.c platform.c observe.c reset_probe.c start_clear.c rx2_ready.c
    STACKSIZE 8192 PRIORITY 100 MODULE ${CONFIG_EXAMPLES_K7SOUND})
endif()
