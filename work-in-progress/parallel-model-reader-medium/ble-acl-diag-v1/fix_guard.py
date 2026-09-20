from pathlib import Path
p=Path(__file__).parent
q=p/'build_candidate.py'; s=q.read_text().replace('if (((const uint8_t *)packet)[3] == SKW_BT_DATA_PORT)', 'if (length >= 4 && ((const uint8_t *)packet)[3] == SKW_BT_DATA_PORT)'); q.write_text(s)
