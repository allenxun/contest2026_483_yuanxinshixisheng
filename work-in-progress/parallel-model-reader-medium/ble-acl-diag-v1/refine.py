from pathlib import Path
p=Path(__file__).parent/'build_candidate.py'
s=p.read_text().replace("b=(root/'app/k7radio'/n).read_bytes();", "b=(d/'input'/n).read_bytes() if (d/'input'/n).exists() else (root/'app/k7radio'/n).read_bytes();")
s=s.replace("'SLOT_DECODE_FAIL','HCI_DECODE_FAIL'", "'SLOT_DECODE_FAIL','PORT5_SLOT_DECODE_FAIL','HCI_DECODE_FAIL','PORT5_HCI_DECODE_FAIL'")
s=s.replace('if (ret) { bm_inc(BM_SLOT_DECODE_FAIL);', 'if (ret) { if (channel == 5) bm_inc(BM_PORT5_SLOT_DECODE_FAIL); bm_inc(BM_SLOT_DECODE_FAIL);')
s=s.replace('if (ret) { bm_inc(BM_HCI_DECODE_FAIL);', 'if (ret) { if (packet.channel == SKW_BT_DATA_PORT) bm_inc(BM_PORT5_HCI_DECODE_FAIL); bm_inc(BM_HCI_DECODE_FAIL);')
p.write_text(s)
