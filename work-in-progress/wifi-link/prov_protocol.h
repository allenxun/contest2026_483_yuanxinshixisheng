/* SPDX-License-Identifier: Apache-2.0 */
#ifndef VELA_PROV_PROTOCOL_H
#define VELA_PROV_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define PROV_MAX_CMD 512
enum prov_command { PROV_SCAN=1, PROV_STATUS, PROV_CONNECT };
struct prov_request { enum prov_command command; unsigned int id; };
struct prov_rx { char data[PROV_MAX_CMD+1]; size_t used; uint32_t started; int discard; };
void prov_zero(void *p,size_t n);
void prov_protocol_init(void);
void prov_rx_reset(struct prov_rx *r);
int prov_rx_feed(struct prov_rx *r,const void *data,size_t n,uint32_t now);
int prov_parse(const char *text,struct prov_request *out);
void prov_base64(const uint8_t *p,size_t n,char *out);
#endif
