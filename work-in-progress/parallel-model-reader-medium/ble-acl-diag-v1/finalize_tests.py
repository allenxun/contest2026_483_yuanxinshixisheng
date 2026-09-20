from pathlib import Path
p=Path(__file__).parent
q=p/'build_candidate.py';s=q.read_text().replace('extern struct bt_meta g_bt_meta;','extern struct bt_meta g_bt_meta;\n_Static_assert(sizeof(int) == 4, "diagnostic error width");');q.write_text(s)
q=p/'create_tx_test.py';s=q.read_text();s=s.replace("(p/'test_tx.c').write_text(prefix+send+worker+tail)","status=s[s.index('static int fw_ble_status(void)'):s.index('int main(int argc, char **argv)')]\nextra='static bool g_bt_host_mode=true;\\nstatic struct { int lock; unsigned connected,handle,acl_rx,acl_tx,connections,disconnections,disconnect_reason,encryption_status,encryption_enabled; } g_native_bt;\\n'\ntail=tail.replace('puts(\"PASS extracted', 'lock_result=0;assert(!fw_ble_status());assert(!bm_get(BM_ACL_QUEUED));puts(\"PASS extracted')\n(p/'test_tx.c').write_text(prefix+extra+send+worker+status+tail)")
q.write_text(s)
q=p/'create_tests.py';s=q.read_text().replace('assert(bm_get(BM_HCI_DECODE_FAIL)==1);','assert(bm_get(BM_HCI_DECODE_FAIL)==1&&bm_get(BM_PORT5_HCI_DECODE_FAIL)==1);').replace('bm_get(BM_SLOT_DECODE_FAIL)==1);','bm_get(BM_SLOT_DECODE_FAIL)==1&&bm_get(BM_PORT5_SLOT_DECODE_FAIL)==1);');q.write_text(s)
