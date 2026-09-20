include $(APPDIR)/Make.defs
PROGNAME = k7radio
PRIORITY = 100
STACKSIZE = 4096
MODULE = $(CONFIG_EXAMPLES_K7RADIO)
MAINSRC = k7radio_main.c
CSRCS = skw_bus.c skw_dw.c skw_rk3576.c skw_packet.c skw_bt.c skw_wpa_transport.c
include $(APPDIR)/Application.mk

# Flat-build native Bluetooth API adapter and bounded JSON parser
CSRCS += prov_protocol.c cJSON.c
CFLAGS += -DCJSON_NESTING_LIMIT=4 -I$(TOPDIR)/wireless/bluetooth
