"""Apply SDK inode union correction, retaining exact failed-stage provenance."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
stage=json.loads((R/'private/emmc-block-20260910/staging.json').read_text())
paths=['app/k7emmc/block_readonly.inc','app/k7emmc/test_block_readonly.c']
e={p:[stage[p]['new']] for p in paths}
(R/'evidence/sync/emmc-block-attempt1.json').write_text(json.dumps(e,indent=2)+'\n',encoding='utf-8')
old={p:v['new'] for p,v in stage.items()}
(R/'private/emmc-block-original-hashes.json').write_text(json.dumps(old,indent=2)+'\n',encoding='utf-8')
p=R/paths[0];text=p.read_text().replace('->i_bops','->u.i_bops');p.write_text(text,encoding='utf-8',newline='\n')
p=R/paths[1];text=p.read_text().replace('->i_bops','->u.i_bops')
text=text.replace('const struct block_operations *i_bops; };','union { const struct block_operations *i_bops; } u; };')
text=text.replace('(struct inode){priv,ops}','(struct inode){.i_private=priv,.u={.i_bops=ops}}')
p.write_text(text,encoding='utf-8',newline='\n')
print('Corrected inode union; failed source hashes recorded (not build success)')
