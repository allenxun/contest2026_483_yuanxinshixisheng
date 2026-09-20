# BLE ACL metadata diagnostic candidate

Status: HOST_TESTED_CANDIDATE; no target build or hardware test. This candidate is independent of the shared Wi-Fi backend and changes no pairing/security policy, packet decoder policy, scheduler, thread creation, flow-control decisions, or ownership.

## Integrate

1. Verify inputs.json against the current five formal inputs before applying candidate.patch. The patch changes only app/k7radio/k7radio_main.c and skw_bt.c, and adds bt_meta.h. The other candidate files are unchanged frozen build inputs. Formal inputs use CRLF and the patch uses LF: plain `git apply --check` rejected context; `git apply --ignore-space-change --check` passed against unchanged formal sources at delivery. Use that option for integration, or copy the two reviewed candidate files plus the new header after verifying input hashes.
2. Rebuild both main and skw_bt objects together. No new .c source/build-system entry or struct skw_bt ABI change is needed. Do not mix this patch with the shared backend patch without a separate review.
3. Target compiler must support GNU lock-free 32-bit atomics; static assertions reject unsupported atomic/int width. Root owns SDK compile/link and hardware approval.
4. Explicit `k7radio ble-status` appends six `RADIO BTM` metadata lines after existing status. No new per-packet printf. Existing historical per-packet logs are unchanged. No ACL payload, keys, passwords, addresses, SMP fields or buffers are added to diagnostics.
5. Record baseline and post-attempt status deltas plus existing host fault/TX/ACK/RX status. Counters live for the application process lifetime, include traffic before advertising, and are not reset on reconnect or skw_bt_init.

## Counter interpretation

- ACL_QUEUED: successful software queue insertion of port 5 transfer, before the existing semaphore post. It does not prove semaphore delivery or hardware transfer.
- ACL_SEND_OK/FAIL: fw_packet return 0/nonzero for dequeued port 5 transfer. This is synchronous transport return, not HCI completion or peer consumption.
- ACL_ACK_MATCH: existing link ACK channel/pending predicate matched on port 5. ACL_ACK_OTHER: port 5 ACK passed bridge readiness but did not match that predicate. This preserves the current implementation's ignored sequence number; it does NOT prove transaction identity against late ACKs. ACK may arrive while synchronous send is still returning, so snapshots need not show queue/send/ACK in numerical order.
- ACL_ACK_WAIT_FAIL and last_wait record actual existing wait failure; no extra wait or retry.
- PORT5_SLOT counts raw header channel byte 5 at the sole fw_receive slot decoder, including malformed headers. It is a header claim, not proof of a valid ACL; an EOF header with that byte is also counted. SLOT_DECODE_FAIL is all channels; PORT5_SLOT_DECODE_FAIL narrows by header claim. No masking of channel bits.
- HCI_DECODE_FAIL/PORT5_HCI_DECODE_FAIL count the real HCI parser failure, preserving its return. H4_ACL/EVENT/SCO/VENDOR/OTHER classify the bounded H4 byte BEFORE HCI validation, and thus count claimed categories, including malformed packets. LINK_ACK means logical length 12 before readiness; it is not an accepted ACK. Normal current dispatcher sends ports 2/5 only, so H4_SCO is normally unreachable.
- READY_REJECT is opened=false or lower.ready failure after decode. RX_LOCK_FAIL is distinct. Existing ACL_RX remains after decode/ready, before upper delivery; this patch does not add upper-layer success claims.
- FLOW_COMPLETE counts validated HCI Command Complete for opcode 0x0c31 that passed bridge readiness. flow_status is its last controller status byte; status 0 is meaningful only when FLOW_COMPLETE > 0. Initial zero alone is not success. This does not record the requested flow mode; that is existing initialization code/config evidence.
- last_decode_error is the latest SDIO or HCI error, last_ready_error covers lock/ready errors; successes do not erase prior errors.

## Atomicity and size

20 uint32 counters + 4 int last errors + uint32 status = 100 bytes, statically zero initialized. Every diagnostic access in production uses relaxed atomic fetch-add/load/store. No lock, heap allocation, reset command, payload copy or new worker. Four host pthreads incremented a shared counter 100000 times each with exact result at O0/O2. uint32 wrap is defined modulo 2^32 and tested; compare deltas modulo 2^32 only across short observation intervals. Individual fields are atomic, but status is not a coherent multi-field snapshot and error/status may race their respective counts. Never use these fields as synchronization or acceptance gates. Existing scheduler timing can still be affected slightly by atomic instructions and explicit status output.

## Host evidence / reproduction

Run `C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe run_tests.py` from this directory. Each compile is bounded 30 s and each executable 15 s. Exact GCC commands and raw stdout are in test-output.txt. O0/O2 use -std=c11 -Wall -Wextra -Werror -pthread.

RX test compiles actual candidate skw_bt.c plus unchanged real skw_packet.c, with explicit NuttX mutex/driver/upper callback stubs. It checks closed and ready failure, lock failure, valid ACL, invalid H4, actual 0c31 failure status, atomic increments/wrap, and decoder/send helper counters. TX test extracts exact candidate bt_lower_send, bt_lower_ack, bt_tx_worker and fw_ble_status, using mock fw_packet/semaphore/mutex only; checks transport failure, matched/duplicate ACK, wait timeout, full queue and lock failure with no queue count, and status prints. Extraction script and full test sources retained. These are real C paths with injected hardware/OS events, not proof of SDIO/firmware behavior. Whole k7radio_main.c and target SDK headers are not host compiled.

Initial host harness compile used EHOSTDOWN, absent in this MinGW errno set; changed only injected host test error to EIO. No target source or errno handling was changed for that harness issue.

Build_candidate.py regenerates only from existing frozen input snapshots after initial capture. Other generation/refinement scripts are authoring history; use run_tests.py for verification, not repeated refinement scripts. Input/output manifests freeze all delivery files. No SDK, device or formal source writes were made.

