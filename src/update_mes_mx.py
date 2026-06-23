#!/usr/bin/env python3
# Update incremental Monitor Bancos MX: agrega UN mes al bancos_mx.json existente
# sin reprocesar las 13.7M filas del CSV completo. Usa un subset prefiltrado del
# mes (grep '"YYYYMM"' del csv grande). Replica EXACTAMENTE las formulas de etl_mx.py.
# Uso: python update_mes_mx.py 2026-04 /tmp/mx_202604.csv [--write]
import sys, os, csv, json, datetime
from collections import defaultdict

REPO = os.environ.get("REPO_BANCOS_MX", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSON = os.path.join(REPO, "docs", "data", "bancos_mx.json")

MONTH  = sys.argv[1]               # '2026-04'
SUBSET = sys.argv[2]               # csv prefiltrado del mes
WRITE  = "--write" in sys.argv
PER    = MONTH.replace("-", "")    # '202604'

# ── Mapas copiados textualmente de etl_mx.py ────────────────────────────────
IND_MAP = {
    '40200001':'roa','40200002':'roe','40200017':'imor','40200033':'imora',
    '40200074':'tda','40200096':'icor','40200118':'eprc_ratio','40200162':'tasa_activa',
    '40200037':'tasa_pasiva','40200218':'mif','40200032':'liquidez',
    '40200018':'imor_comercial','40200019':'imor_consumo','40200020':'imor_vivienda',
    '40200097':'icor_comercial','40200101':'icor_consumo','40200112':'icor_vivienda',
}
BAL_MAP = {
    '40100001':'activo','40100002':'capital','40100551':'cartera_neto','40100042':'captacion',
    '40100096':'pasivo','40100008':'margen_fin','40100009':'margen_aj','40100013':'resultado_neto',
    '40100011':'gastos_adm','40100006':'ingresos_int','40100007':'gastos_int','40100045':'efectivo',
    '40100079':'dep_inmediato','40100085':'captacion_trad','40100031':'estimacion_prev',
    '40100185':'cartera_riesgo','40100341':'cartera_etapa3',
}
ALL_CONCEPTS = set(IND_MAP) | set(BAL_MAP)
GROUPS = {
    'sistémico': {'040002','040012','040014','040021','040036','040044','040072'},
    'mediano':   {'040030','040037','040042','040058','040113','040132','040156','040112','040136','040143','040145'},
    'inv_svc':   {'040059','040062','040103','040106','040108','040110','040124','040126','040129','040139','040148','040160','040164'},
    'pequeño':   {'040060','040102','040128','040133','040138','040147','040150','040151','040152','040154','040155','040157','040158','040159','040162'},
    'hogares':   {'040127','040130','040131','040137','040140','040141','040149','040165','040167','040169','040170','040171'},
    'sin_clasif':{'040032','040116','040134','040144','040146'},
}

# ── Leer subset del mes (single pass, mismo filtro saldo=='130') ─────────────
raw = defaultdict(dict)  # entidad -> {concepto: valor}
cols = ["sector","idconcepto","entidad","periodo","saldo","valor"]
with open(SUBSET, encoding='latin-1') as f:
    for row in csv.DictReader(f, fieldnames=cols):
        if row['periodo'] != PER:      # por si el grep trajo coincidencias parciales
            continue
        if row['saldo'] != '130':
            continue
        if row['idconcepto'] not in ALL_CONCEPTS:
            continue
        try:
            raw[row['entidad']][row['idconcepto']] = float(row['valor'])
        except (ValueError, TypeError):
            continue

print(f"Mes {MONTH}: {len(raw)} entidades con datos en el subset")

data = json.load(open(JSON, encoding='utf-8'))
banks  = data['meta']['banks']
months = data['meta']['months']
if MONTH in months:
    sys.exit(f"ERROR: {MONTH} ya existe en el JSON")
if MONTH <= months[-1]:
    sys.exit(f"ERROR: {MONTH} no es posterior al ultimo ({months[-1]})")

new_ents = sorted(set(raw) - set(banks))
faltan   = [b for b in banks if b not in raw]
print(f"Bancos JSON: {len(banks)} | con dato este mes: {len(raw)}")
if new_ents: print("  NUEVAS entidades en el mes:", new_ents)
if faltan:   print(f"  Sin dato este mes (quedaran None): {len(faltan)} ->", faltan[:8], "..." if len(faltan)>8 else "")

def cell_values(ent):
    """Devuelve dict {grp:{key:val}} para una entidad en este mes (None si falta)."""
    c = raw.get(ent, {})
    out_ind = {key: c.get(cid) for cid, key in IND_MAP.items()}
    out_bal = {key: c.get(cid) for cid, key in BAL_MAP.items()}
    activo=c.get('40100001'); capital=c.get('40100002'); margen=c.get('40100008')
    gastos=c.get('40100011'); ing=c.get('40100006'); gto=c.get('40100007')
    efe=c.get('40100045'); dep=c.get('40100079')
    out_der = {k: None for k in data['der']}
    if activo and capital and activo>0:        out_der['capital_activo']=capital/activo
    if margen and gastos and margen>0 and gastos>=0: out_der['efic_margen']=gastos/margen
    if activo and gastos and activo>0 and gastos>=0: out_der['efic_activo']=gastos/activo
    if ing and gto and gto>0:                  out_der['cov_int']=ing/gto
    if efe and dep and dep>0:
        out_der['ictl_ilon']=efe/dep
        out_der['ictl_itl']=dep/efe
    if ing and gto and gto>0:                  out_der['ictl_icint']=ing/gto
    return out_ind, out_bal, out_der

# Muestra de validacion (Total Sistema '5' y BBVA '040012')
for ent in ['5','040012']:
    if ent in banks or ent in raw:
        oi,ob,od = cell_values(ent)
        print(f"  {ent} {data['meta']['display'].get(ent,ent)}: roa={oi['roa']} activo={ob['activo']} cap/act={od['capital_activo']}")

if not WRITE:
    print("\n[DRY-RUN] No se escribio nada. Re-correr con --write.")
    sys.exit(0)

# ── Insertar entidades nuevas en posicion ordenada (igual que sorted() del ETL) ──
for ne in new_ents:
    pos = 0
    while pos < len(banks) and banks[pos] < ne:
        pos += 1
    banks.insert(pos, ne)
    # display
    data['meta']['display'][ne] = ne  # sin nombre conocido; queda el id
    # grupo
    grp = next((g for g,mem in GROUPS.items() if ne in mem), None) or \
          ('agregado' if ne in {'5','59','60','61','62','63','64'} else 'sin_clasif')
    data['meta'].setdefault('groups', {})[ne] = grp
    filler = [None]*len(months)
    for g in ['ind','der','bal']:
        for k in data[g]:
            data[g][k].insert(pos, list(filler))

# ── Append de la columna del mes en cada serie ──────────────────────────────
for bi, ent in enumerate(banks):
    oi, ob, od = cell_values(ent)
    for k in data['ind']: data['ind'][k][bi].append(oi.get(k))
    for k in data['bal']: data['bal'][k][bi].append(ob.get(k))
    for k in data['der']: data['der'][k][bi].append(od.get(k))

months.append(MONTH)
data['meta']['generated'] = datetime.date.today().isoformat()

# Validacion de longitudes
L = len(months); bad = 0
for g in ['ind','der','bal']:
    for k in data[g]:
        for row in data[g][k]:
            if len(row) != L: bad += 1
if bad:
    sys.exit(f"ERROR: {bad} series con longitud != {L}")

with open(JSON, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
print(f"\n✓ Escrito. Meses: {L} | ultimo: {months[-1]} | bancos: {len(banks)} | {os.path.getsize(JSON)/1048576:.1f} MB")
