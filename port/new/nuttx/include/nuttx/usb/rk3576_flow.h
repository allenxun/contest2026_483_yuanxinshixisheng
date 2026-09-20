/* SPDX-License-Identifier: Apache-2.0 */
#ifndef NUTTX_USB_RK3576_FLOW_H
#define NUTTX_USB_RK3576_FLOW_H
/* Keep 2048 queued HS microframes; deliver completed groups every32ms
 * instead of128ms. Camera parser and HCD must use the same geometry. */
#define K7_FLOW_BANKS 8u
#define K7_FLOW_SLOTS 256u
#define K7_FLOW_TOTAL (K7_FLOW_BANKS * K7_FLOW_SLOTS)
#if K7_FLOW_TOTAL != 2048
#error Flow geometry must match the 2049-entry ring including its link TRB
#endif
#endif
