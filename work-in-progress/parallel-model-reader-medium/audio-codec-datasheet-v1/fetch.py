import pathlib,urllib.request,json,hashlib,time
R=pathlib.Path(__file__).resolve().parent
targets=[('everest-original.pdf','https://www.everest-semi.com/pdf/ES8388%20DS.pdf'),('es8388-rev10-pcbartists.pdf','https://cdn.pcbartists.com/wp-content/uploads/2022/12/es8388-datasheet-english.pdf'),('es8388-rev5-lcsc.pdf','https://datasheet.lcsc.com/lcsc/1912111437_Everest-semi-Everest-Semiconductor-ES8388_C365736.pdf')]
records=[]
for name,url in targets:
 row=dict(url=url,file=name,started=time.time())
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=12) as response:
   data=response.read(5*1024*1024+1)
   assert len(data)<=5*1024*1024,'5 MiB download cap'
   assert data.startswith(b'%PDF-'),'not PDF'
   (R/name).write_bytes(data)
   row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),final_url=response.url)
 except Exception as e:row['error']=str(e)
 records.append(row)
 (R/'fetch-results.json').write_text(json.dumps(records,indent=2)+'\n')
 print(row,flush=True)
