import json,pandas as pd,numpy as np,sys
d=json.load(open('docs/data/bancos_mx_v2.json'));B=d['meta']['banks'];M=d['meta']['months']
def df(s,k): return pd.DataFrame(d[s][k],index=B,columns=M,dtype=float).drop('SISTEMA')
act=df('bal','activo')
IND=[('pt','coef_basilea','ICAP'),('pt','ccf','CCF'),('ind','act_impr','Act. improductivos'),('ind','mor_total','IMOR'),
     ('ind','cob_prob','ICOR'),('ind','efic_margen','Gastos/ingresos op.'),('ind','efic_activo','Gastos/activo'),
     ('ind','roa','ROA'),('ind','roe','ROE'),('ind','liq_ampliada','Liquidez CNBV'),('ind','dep_cartera','Depositos/cartera'),('ind','vulner_pat','Vulnerab. patrimonial')]
P=[10,25,50,75,90]
def wq(v,w,q):
    o=np.argsort(v); v=v[o]; w=w[o]; c=np.cumsum(w)/w.sum(); return np.interp(np.array(q)/100,c,v)
out={}
for desde,tag in [('2014-01','full'),('2025-10','12m')]:
  cols=[m for m in M if m>=desde]
  for s,k,l in IND:
    x=df(s,k)[cols].stack(); w=act[cols].stack().reindex(x.index)
    ok=x.notna()&w.notna()&np.isfinite(x)
    x=x[ok].values; w=w[ok].values
    out.setdefault(l,{})[tag]={'n':int(len(x)),'simple':[float(np.percentile(x,p)) for p in P],'pond':[float(v) for v in wq(x,w,P)]}
json.dump(out,open('estudio_calibracion_mx/percentiles.json','w'),indent=1)
for l,v in out.items():
  f=lambda a:' '.join(f'{z:8.4f}' for z in a)
  print(f'{l:22s} n={v["full"]["n"]:5d} S {f(v["full"]["simple"])} | W {f(v["full"]["pond"])} | W12 {f(v["12m"]["pond"])}')
