"""Compile the hash-pinned fixed FSA-Net graph to freestanding scalar C."""
from pathlib import Path
import hashlib,json
import numpy as np
import onnx

r=Path(__file__).resolve().parent
path=r/'model-inspection/head_pose_fsanet_1x1.onnx'
digest=hashlib.sha256(path.read_bytes()).hexdigest()
assert digest=='120fa107a2dd3be78c21c3a73a0db980590643a5372893e8878094898262f213'
m=onnx.shape_inference.infer_shapes(onnx.load(path));onnx.checker.check_model(m)
dims={v.name:tuple(d.dim_value for d in v.type.tensor_type.shape.dim) for v in [*m.graph.input,*m.graph.value_info,*m.graph.output]}
arrays={t.name:onnx.numpy_helper.to_array(t) for t in m.graph.initializer}
dims.update({k:v.shape for k,v in arrays.items()})
assert dims['input']==(1,3,64,64) and dims['output']==(1,3)
out=['/* Generated fixed FSA-Net. Model SHA256: '+digest+' */']
calls=[];ptrs={'input':'a'};offsets={'input':0};used=12288;macs=0
def num(s): return int(np.prod(s,dtype=np.int64))
def ptr(n):
    if n in ptrs:return ptrs[n]
    ar=arrays[n];assert np.isfinite(ar).all()
    sym='pw'+str(len(ptrs));ptrs[n]=sym
    vals=[float(v).hex()+'f' for v in ar.flatten()]
    out.append('static const float '+sym+'[] = {\n'+ '\n'.join(','.join(vals[i:i+8])+',' for i in range(0,len(vals),8))+'\n};')
    return sym
def index_expr(source,target):
    source=(1,)*(len(target)-len(source))+source
    assert all(a==1 or a==b for a,b in zip(source,target)),(source,target)
    terms=[]
    for j,d in enumerate(source):
        if d!=1:terms.append('((i/%d)%%%d)*%d'%(num(target[j+1:]),target[j],num(source[j+1:])))
    return '+'.join(terms) or '0'
def mapped(a,b,ids,i):
    ids=np.asarray(ids).flatten();name='pm'+str(i)
    out.append('static const unsigned int '+name+'[] = {'+','.join(map(str,ids))+'};')
    calls.append('for(int i=0;i<%d;i++) %s[i]=%s[%s[i]];'%(len(ids),b,a,name))

layers=[]
for i,n in enumerate(m.graph.node):
    op=n.op_type;ins=list(n.input);dest=n.output[0]
    assert len(n.output)==1 and dest in dims and all(v>0 for v in dims[dest]),(i,op,dims.get(dest))
    shape=dims[dest];at={x.name:onnx.helper.get_attribute_value(x) for x in n.attribute}
    if op in ('Reshape','Unsqueeze','Squeeze'):
        assert num(dims[ins[0]])==num(shape)
        ptrs[dest]=ptr(ins[0]);offsets[dest]=offsets[ins[0]]
        layers.append(dict(name=dest,offset=offsets[dest],shape=shape));continue
    ptrs[dest]='(a+%d)'%used;offsets[dest]=used;used+=num(shape)
    layers.append(dict(name=dest,offset=offsets[dest],shape=shape))
    b=ptr(dest);a=ptr(ins[0]);s=dims[ins[0]]
    calls.append('/* %d %s */'%(i,op))
    if op=='Conv':
        _,ci,ih,iw=s;_,co,oh,ow=shape;k=at['kernel_shape'][0];st=at['strides'][0];pad=at['pads'][0];g=at.get('group',1)
        assert at['kernel_shape']==[k,k] and at['strides']==[st,st] and at['pads']==[pad]*4
        assert at.get('dilations',[1,1])==[1,1] and k in (1,3) and (g==1 or g==ci==co)
        if len(ins)==2:
            zero='bias_zero_'+str(i);arrays[zero]=np.zeros(co,dtype=np.float32);ins.append(zero)
        calls.append('yn_conv(%s,%s,%s,%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d);'%(a,b,ptr(ins[1]),ptr(ins[2]),ci,ih,iw,co,oh,ow,k,st,pad,g))
        macs+=co*oh*ow*(ci//g)*k*k
    elif op in ('MaxPool','AveragePool'):
        assert at['kernel_shape']==[2,2] and at['pads']==[0]*4 and at['strides']==[2,2]
        _,c,h,w=s;assert h%2==w%2==0
        calls.append('pose_pool(%s,%s,%d,%d,%d,%d);'%(a,b,c,h,w,int(op=='AveragePool')))
    elif op in ('Relu','Tanh','Sigmoid','Sqrt','Exp'):
        expr={'Relu':'fmaxf(x,0)','Tanh':'tanhf(x)','Sigmoid':'1.0f/(1.0f+expf(-x))','Sqrt':'sqrtf(x)','Exp':'expf(x)'}[op]
        calls.append('for(int i=0;i<%d;i++){float x=%s[i];%s[i]=%s;}'%(num(shape),a,b,expr))
    elif op in ('Add','Mul','Div','Pow'):
        x='%s[%s]'%(a,index_expr(s,shape));y='%s[%s]'%(ptr(ins[1]),index_expr(dims[ins[1]],shape))
        expr='powf(%s,%s)'%(x,y) if op=='Pow' else x+{'Add':'+','Mul':'*','Div':'/'}[op]+y
        calls.append('for(int i=0;i<%d;i++) %s[i]=%s;'%(num(shape),b,expr))
    elif op=='Gemm':
        assert at==dict(alpha=1.,beta=1.,transB=1,transA=0)
        rows,k=s;cols=dims[ins[1]][0];macs+=rows*k*cols
        calls.append('pose_gemm(%s,%s,%s,%s,%d,%d,%d);'%(a,ptr(ins[1]),ptr(ins[2]),b,rows,k,cols))
    elif op=='MatMul':
        s2=dims[ins[1]];rows,k=s[-2:];assert s2[-2]==k;cols=s2[-1]
        batch=shape[:-2];sa=s[:-2];sb=s2[:-2]
        ai=np.broadcast_to(np.arange(num(sa)).reshape(sa),batch).flatten()
        bi=np.broadcast_to(np.arange(num(sb)).reshape(sb),batch).flatten()
        for j,(ia,ib) in enumerate(zip(ai,bi)):
            calls.append('pose_mm(%s+%d,%s+%d,%s+%d,%d,%d,%d);'%(a,ia*rows*k,ptr(ins[1]),ib*k*cols,b,j*rows*cols,rows,k,cols))
        macs+=len(ai)*rows*k*cols
    elif op=='ReduceSum':
        assert len(at['axes'])==1 and at['keepdims']==1
        ax=at['axes'][0]%len(s);outer=num(s[:ax]);inner=num(s[ax+1:]);dim=s[ax]
        calls.append('pose_sum(%s,%s,%d,%d,%d);'%(a,b,outer,dim,inner))
    elif op=='Concat':
        ax=at['axis']%len(shape);outer=num(shape[:ax]);inner=num(shape[ax+1:]);offset=0
        for name in ins:
            chunk=dims[name][ax]*inner
            calls.append('for(int i=0;i<%d;i++)memcpy(%s+i*%d+%d,%s+i*%d,%d*sizeof(float));'%(outer,b,shape[ax]*inner,offset,ptr(name),chunk,chunk))
            offset+=chunk
    elif op=='Transpose': mapped(a,b,np.arange(num(s)).reshape(s).transpose(at['perm']),i)
    elif op=='Slice':
        sl=[slice(None)]*len(s)
        for ax,st,en in zip(at['axes'],at['starts'],at['ends']):sl[ax]=slice(st,en)
        ids=np.arange(num(s)).reshape(s)[tuple(sl)];assert ids.shape==shape
        mapped(a,b,ids,i)
    elif op=='Gather':
        ids=np.take(np.arange(num(s)).reshape(s),arrays[ins[1]],axis=at['axis'])
        assert ids.shape==shape;mapped(a,b,ids,i)
    else:raise ValueError((i,op))

out+=['#define POSE_FLOATS %d'%used,'static void pose_graph(float *a) {']+calls+['}']
out+=['#define POSE_OUTPUT %d'%offsets['output']]
(r/'k7_pose_model.inc').write_text('\n'.join(out)+'\n')
(r/'pose-graph.json').write_text(json.dumps(dict(sha256=digest,arena_bytes=used*4,macs=macs,layers=layers),indent=2))
print(json.dumps(dict(arena_bytes=used*4,macs=macs,layers=len(layers))))
