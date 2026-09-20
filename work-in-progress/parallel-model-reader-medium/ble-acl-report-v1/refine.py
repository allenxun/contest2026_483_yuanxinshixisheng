from pathlib import Path
p=Path(__file__).parent/'report.py'
s=p.read_text().replace("    lines = text.splitlines()", "    lines = text.splitlines(keepends=True)")
s=s.replace("    for line in lines:", "    positions = []\n    for index, line in enumerate(lines):")
s=s.replace("            if not line.startswith(PREFIX):", "            if not line.endswith('\\n'):\n                raise ValueError('unterminated BTM line')\n            positions.append(index)\n            if not line.startswith(PREFIX):")
s=s.replace("    values = {}", "    if positions != list(range(positions[0], positions[0]+6)):\n        raise ValueError('interleaved BTM block')\n    values = {}")
p.write_text(s)
