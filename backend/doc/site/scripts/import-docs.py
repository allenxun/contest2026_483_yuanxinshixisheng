from pathlib import Path
import xml.etree.ElementTree as E,re,html,json,hashlib
site=Path(__file__).resolve().parents[1];source=site.parent
files={'components':'后端组件图-V5-部署式运行视图.drawio','modules':'后端模块图-V4-五模块.drawio','usecases':'后端用例图-V8-APP与云台控制.drawio','flows':'后端流程图-V4-APP与云台控制.drawio'}
def plain(v):
 v=re.sub(r'<br\s*/?>','\n',v,flags=re.I);v=re.sub(r'</(?:div|p)>','\n',v,flags=re.I);v=html.unescape(re.sub(r'<[^>]*>','',v));return re.sub(r'\n{3,}','\n\n',v).strip()
def parse(path):
 pages=[]
 for page in E.parse(path).getroot().findall('diagram'):
  cs={c.get('id'):c for c in page.iter('mxCell')};model=page.find('mxGraphModel');nodes=[];edges=[]
  def abspos(c):
   g=c.find('mxGeometry');x=float(g.get('x',0));y=float(g.get('y',0));p=c.get('parent')
   while p not in ('0','1',None):
    g=cs[p].find('mxGeometry');x+=float(g.get('x',0));y+=float(g.get('y',0));p=cs[p].get('parent')
   return x,y
  for c in cs.values():
   st={};sty=c.get('style','')
   for s in sty.split(';'):
    if '=' in s:k,v=s.split('=',1);st[k]=v
    elif s:st[s]='1'
   g=c.find('mxGeometry')
   if c.get('vertex')=='1':
    x,y=abspos(c);parent=c.get('parent','1');ptext=plain(cs[parent].get('value','')) if parent in cs else ''
    nodes.append({'id':c.get('id'),'text':plain(c.get('value','')),'x':x,'y':y,'w':float(g.get('width',0)),'h':float(g.get('height',0)),'style':st,'parent':parent,'lane':ptext if parent.startswith('lane') else '', 'apis':list(dict.fromkeys(re.findall(r'M[1-5]-A\d{2}',c.get('value',''))))})
   if c.get('edge')=='1':
    edges.append({'id':c.get('id'),'source':c.get('source'),'target':c.get('target'),'text':plain(c.get('value','')),'style':st,'points':[{'x':float(p.get('x',0)),'y':float(p.get('y',0))} for p in c.findall('mxGeometry/Array/mxPoint')]})
  pages.append({'id':page.get('name')[:2],'name':page.get('name'),'width':float(model.get('pageWidth')),'height':float(model.get('pageHeight')),'nodes':nodes,'edges':edges})
 return pages
md=(source/'后端API接口设计-V1-五模块与流程对应.md').read_text();refs={}
for line in md.splitlines():
 if re.match(r'^\| M[1-5]-A\d{2}',line):
  parts=[p.strip() for p in line.split('|')[1:-1]];refs[parts[0]]=parts[-1]
apis=[]
for m in re.finditer(r'^#### (M[1-5]-A\d{2}) · ([^\n]+)\n(.*?)(?=^### |^#### |^## |\Z)',md,re.M|re.S):
 i,title,body=m.groups();fields=dict(re.findall(r'^- \*\*(.+?)\*\*：(.+)$',body,re.M));route=re.search(r'`(GET|POST|PUT|DELETE|PATCH) (.*?)`',fields['接口']);assert route,i
 apis.append({'id':i,'module':i[:2],'title':title,'method':route.group(1),'path':route.group(2),'caller':fields.get('调用方',''),'input':fields.get('输入要素',''),'output':fields.get('输出要素',''),'rules':fields.get('关键规则',''),'flowNote':fields.get('流程对应',''),'refs':refs[i]})
assert len(apis)==27
sections=[]
for match in re.finditer(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)',md,re.M|re.S):
 title,body=match.groups()
 if title.startswith('3.'):continue
 sections.append({'title':title,'markdown':body.strip()})
data={k:parse(source/v) for k,v in files.items()};data['apis']=apis;data['sections']=sections
mods=[];ns=data['modules'][0]['nodes'];byid={n['id']:n for n in ns}
for i in range(1,6):
 id=f'M{i}';name=byid[id]['text'].split('\n')[0][3:];mods.append({'id':id,'name':name,'parts':[byid[f'{id}-part{k}']['text'] for k in range(3)],'apis':[a['id'] for a in apis if a['module']==id]})
data['moduleCards']=mods
extra_files={'detailedDesign':'后端详细设计-V1-MVP.md','faceResearch':'人脸服务调研与推荐方案-V1-MVP.md','checklist':'测试场景清单-V1-五模块与双控制.md','decisions':'测试需求决策记录.md','dataArchitecture':'数据架构设计-V1-五模块-MVP.md','technicalArchitecture':'技术架构设计-V1-MVP.md','runtimeNotes':'运行组件说明.md'}
for key,name in extra_files.items(): data[key]=(source/name).read_text()
data['tableCount']=len(re.findall(r'^### T\d+ `',data['dataArchitecture'],re.M))
assert data['tableCount']==14
downloads=site/'public/downloads';downloads.mkdir(parents=True,exist_ok=True)
(downloads/'detailed-design.md').write_text(data['detailedDesign'])
(downloads/'face-research.md').write_text(data['faceResearch'])
(downloads/'data-architecture.md').write_text(data['dataArchitecture'])
(downloads/'technical-architecture.md').write_text(data['technicalArchitecture'])
for name in extra_files.values(): (downloads/name).write_bytes((source/name).read_bytes())
(downloads/'后端API接口设计-V1-五模块与流程对应.md').write_text(md)
asset_files=['assets/runtime-components.svg','assets/runtime-components.mmd','references/face-insightface-code-review.md']
for name in asset_files:
 target=downloads/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/name).read_bytes())
for path in list(source.glob('*.md'))+list(source.glob('*.drawio')):
 (downloads/path.name).write_bytes(path.read_bytes())
data['scenarioCount']=len(re.findall(r'^\| SC-',data['checklist'],re.M))
out=site/'lib/docs-data.json';out.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
manifest={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in list(files.values())+['后端API接口设计-V1-五模块与流程对应.md']+list(extra_files.values())+asset_files}
(site/'lib/source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
apiids={a['id'] for a in apis}
for kind in ['usecases','flows']:
 found={a for p in data[kind] for n in p['nodes'] for a in n['apis']};assert found==apiids,(kind,apiids-found)
print(f'Imported {len(mods)} modules, {len(data["usecases"])} use-case pages, {len(data["flows"])} flows, and {len(apis)} APIs. Every source vertex and edge retained.')
