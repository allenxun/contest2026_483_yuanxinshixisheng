from pathlib import Path
import pypdfium2 as pdfium
R=Path(__file__).resolve().parents[1]
for version in ['K7_V2.0_20250716_SCH','K7_V1.1_20241211_SCH']:
 doc=pdfium.PdfDocument(str(Path(r'E:\rk3576_data\4-HardwareData\K7')/(version+'.pdf')))
 for page in [5,16,17,20,32,33]:
  bitmap=doc[page-1].render(scale=2)
  bitmap.to_pil().save(R/'evidence'/f'{version}-p{page}.png')
