"""
ETL — Monitor Bancario México
Sakbé Consultores

Lee los 3 CSV del CNBV (sector 40, Banca Múltiple) y genera bancos_mx.json
con la misma estructura que bancos.json del monitor ecuatoriano.

Uso: python etl_mx.py
Salida: bancos_mx.json en el mismo directorio
"""

import csv
import json
from collections import defaultdict
from datetime import datetime
import os

# ── Rutas ──────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
FILE_INST  = os.path.join(os.path.dirname(BASE), 'data', 'cat_instituciones_40.csv')
FILE_CONC  = os.path.join(os.path.dirname(BASE), 'data', 'cat_conceptos_40.csv')
FILE_DATOS = os.path.join(os.path.dirname(BASE), 'data', 'sh_datos_40_2014_202603.csv')
FILE_OUT   = os.path.join(os.path.dirname(BASE), 'docs', 'data', 'bancos_mx.json')

# ── Conceptos a extraer ─────────────────────────────────────────────────────
# Indicadores directos CNBV (Tema 5)
IND_MAP = {
    '40200001': 'roa',
    '40200002': 'roe',
    '40200017': 'imor',
    '40200033': 'imora',
    '40200074': 'tda',
    '40200096': 'icor',
    '40200118': 'eprc_ratio',
    '40200162': 'tasa_activa',   # anualizada etapa 1+2
    '40200037': 'tasa_pasiva',
    '40200218': 'mif',
    '40200032': 'liquidez',
    # Desgloses IMOR por tipo
    '40200018': 'imor_comercial',
    '40200019': 'imor_consumo',
    '40200020': 'imor_vivienda',
    # Desgloses ICOR por tipo
    '40200097': 'icor_comercial',
    '40200101': 'icor_consumo',
    '40200112': 'icor_vivienda',
}

# Balance y resultados (Temas 1 y 2) — base para ratios derivados
BAL_MAP = {
    '40100001': 'activo',
    '40100002': 'capital',
    '40100551': 'cartera_neto',
    '40100042': 'captacion',
    '40100042': 'captacion',
    '40100096': 'pasivo',
    '40100008': 'margen_fin',
    '40100009': 'margen_aj',
    '40100013': 'resultado_neto',
    '40100011': 'gastos_adm',
    '40100006': 'ingresos_int',
    '40100007': 'gastos_int',
    '40100045': 'efectivo',
    '40100079': 'dep_inmediato',
    '40100085': 'captacion_trad',
    '40100031': 'estimacion_prev',
    '40100185': 'cartera_riesgo',  # cartera con riesgo de crédito (bruta)
    '40100341': 'cartera_etapa3',  # cartera etapa 3 (deteriorada)
}

ALL_CONCEPTS = set(IND_MAP.keys()) | set(BAL_MAP.keys())

# ── Nombres de display ──────────────────────────────────────────────────────
DISPLAY = {
    # Agregados CNBV
    '5':   'Total Sistema',
    '59':  'G-7',
    '60':  'Cambiarios',
    '61':  'Inv. y Servicios',
    '62':  'Comercial Mediano',
    '63':  'Comercial Pequeño',
    '64':  'Créditos a Hogares',
    # G-7
    '040002': 'Banamex',
    '040012': 'BBVA México',
    '040014': 'Santander',
    '040021': 'HSBC',
    '040036': 'Inbursa',
    '040044': 'Scotiabank',
    '040072': 'Banorte',
    # Cambiarios
    '040112': 'Monex',
    '040136': 'Intercam',
    '040143': 'CIBanco',
    '040145': 'Banco Base',
    # Inversión y Servicios
    '040059': 'Invex',
    '040062': 'Afirme',
    '040103': 'American Express',
    '040106': 'Bank of America',
    '040108': 'MUFG Bank',
    '040110': 'J.P. Morgan',
    '040124': 'Citi México',
    '040126': 'Credit Suisse',
    '040129': 'Barclays',
    '040139': 'BIAfirme',
    '040148': 'Pagatodo',
    '040160': 'Banco S3',
    '040164': 'BNP Paribas',
    # Comercial Mediano
    '040030': 'Banco del Bajío',
    '040037': 'Interacciones',
    '040042': 'Banca Mifel',
    '040058': 'Banregio',
    '040113': 'Ve por Más',
    '040132': 'Multiva',
    '040156': 'Sabadell',
    # Comercial Pequeño
    '040060': 'Bansí',
    '040102': 'Accendo',
    '040128': 'Kapital',
    '040133': 'Actinver',
    '040138': 'Ualá',
    '040147': 'Bankaool',
    '040150': 'Inmobiliario Mexicano',
    '040151': 'Dondé Banco',
    '040152': 'Bancrea',
    '040154': 'Covalto',
    '040155': 'ICBC',
    '040157': 'Shinhan',
    '040158': 'Mizuho Bank',
    '040159': 'Bank of China',
    '040162': 'KEB Hana',
    # Créditos a Hogares
    '040127': 'Banco Azteca',
    '040130': 'Compartamos',
    '040131': 'Ahorro Famsa',
    '040137': 'Bancoppel',
    '040140': 'Consubanco',
    '040141': 'Volkswagen Bank',
    '040149': 'Banfeliz',
    '040165': 'Banco Bineo',
    '040167': 'Hey Banco',
    '040169': 'Openbank',
    '040170': 'Revolut',
    '040171': 'Banco Plata',
    # Sin clasificar / históricos
    '040032': 'Ixe',
    '040116': 'ING',
    '040134': 'Banco Walmart',
    '040144': 'BNY Mellon',
    '040146': 'Banco Bicentenario',
}

# Grupos CNBV — para peer scoring de liquidez
GROUPS = {
    'sistémico':  {'040002','040012','040014','040021','040036','040044','040072'},
    'mediano':    {'040030','040037','040042','040058','040113','040132','040156',
                   '040112','040136','040143','040145'},
    'inv_svc':    {'040059','040062','040103','040106','040108','040110','040124',
                   '040126','040129','040139','040148','040160','040164'},
    'pequeño':    {'040060','040102','040128','040133','040138','040147','040150',
                   '040151','040152','040154','040155','040157','040158','040159','040162'},
    'hogares':    {'040127','040130','040131','040137','040140','040141','040149',
                   '040165','040167','040169','040170','040171'},
    'sin_clasif': {'040032','040116','040134','040144','040146'},
}

# ── Paso 1: leer catálogo de instituciones ──────────────────────────────────
print("Leyendo catálogo de instituciones...")
inst_catalog = {}  # entidad_id -> {nombre, grupo}
with open(FILE_INST, encoding='latin-1') as f:
    for row in csv.DictReader(f):
        inst_catalog[row['entidad']] = {
            'nombre': row['nombre_entidad'],
            'grupo':  row['nombre_grupo'],
            'grupo_id': row['grupo'],
        }

# ── Paso 2: leer datos (single pass, filtrado por concepto) ─────────────────
print("Leyendo datos (8M+ filas)...")
raw = defaultdict(dict)  # (entidad, periodo) -> {concepto: valor}

with open(FILE_DATOS, encoding='latin-1') as f:
    reader = csv.DictReader(f)
    n = 0
    for row in reader:
        n += 1
        if n % 1_000_000 == 0:
            print(f"  {n:,} filas procesadas...")
        if row['saldo'] != '130':   # solo saldo puntual
            continue
        if row['idconcepto'] not in ALL_CONCEPTS:
            continue
        try:
            v = float(row['valor'])
        except (ValueError, TypeError):
            continue
        raw[(row['entidad'], row['periodo'])][row['idconcepto']] = v

print(f"  Total filas leídas: {n:,}")
print(f"  Combinaciones entidad×período con datos: {len(raw):,}")

# ── Paso 3: construir índices de bancos y períodos ──────────────────────────
all_entities  = sorted({ent for (ent, _) in raw})
all_periods_r = sorted({per for (_, per) in raw})

# Convertir YYYYMM → YYYY-MM
def fmt_period(p):
    return f"{p[:4]}-{p[4:]}"

all_periods = [fmt_period(p) for p in all_periods_r]
period_idx  = {p: i for i, p in enumerate(all_periods_r)}
entity_idx  = {e: i for i, e in enumerate(all_entities)}

NB = len(all_entities)
NM = len(all_periods)

print(f"  Entidades: {NB} | Períodos: {NM} ({all_periods[0]} → {all_periods[-1]})")

# ── Paso 4: armar arrays ────────────────────────────────────────────────────
def empty_grid():
    return [[None]*NM for _ in range(NB)]

# Indicadores directos
ind = {k: empty_grid() for k in IND_MAP.values()}
# Balance
bal = {k: empty_grid() for k in BAL_MAP.values()}
# Derivados (calculados aquí)
derived_keys = ['capital_activo', 'efic_margen', 'efic_activo', 'cov_int', 'ictl_ilon', 'ictl_icint', 'ictl_itl']
der = {k: empty_grid() for k in derived_keys}

print("Construyendo arrays...")
for (ent, per), concepts in raw.items():
    bi = entity_idx.get(ent)
    mi = period_idx.get(per)
    if bi is None or mi is None:
        continue

    # Indicadores directos
    for cid, key in IND_MAP.items():
        v = concepts.get(cid)
        if v is not None:
            ind[key][bi][mi] = v

    # Balance
    for cid, key in BAL_MAP.items():
        v = concepts.get(cid)
        if v is not None:
            bal[key][bi][mi] = v

    # Derivados
    activo   = concepts.get('40100001')
    capital  = concepts.get('40100002')
    margen   = concepts.get('40100008')
    gastos   = concepts.get('40100011')
    ing_int  = concepts.get('40100006')
    gto_int  = concepts.get('40100007')
    efectivo = concepts.get('40100045')
    dep_inm  = concepts.get('40100079')

    if activo and capital and activo > 0:
        der['capital_activo'][bi][mi] = capital / activo

    if margen and gastos and margen > 0 and gastos >= 0:
        der['efic_margen'][bi][mi] = gastos / margen

    if activo and gastos and activo > 0 and gastos >= 0:
        der['efic_activo'][bi][mi] = gastos / activo

    if ing_int and gto_int and gto_int > 0:
        der['cov_int'][bi][mi] = ing_int / gto_int

    # ICTL aproximado (sin cartera ≤30d — no disponible en datos agregados CNBV)
    if efectivo and dep_inm and dep_inm > 0:
        der['ictl_ilon'][bi][mi] = efectivo / dep_inm
        der['ictl_itl'][bi][mi]  = dep_inm / efectivo

    if ing_int and gto_int and gto_int > 0:
        der['ictl_icint'][bi][mi] = ing_int / gto_int

# ── Paso 5: construir display names y grupos ────────────────────────────────
display = {}
bank_group = {}  # entidad -> grupo peer

for ent in all_entities:
    display[ent] = DISPLAY.get(ent, inst_catalog.get(ent, {}).get('nombre', ent))
    for grp, members in GROUPS.items():
        if ent in members:
            bank_group[ent] = grp
            break
    else:
        # Agregados CNBV
        if ent in {'5','59','60','61','62','63','64'}:
            bank_group[ent] = 'agregado'
        else:
            bank_group[ent] = 'sin_clasif'

# ── Paso 6: ensamblar JSON ──────────────────────────────────────────────────
out = {
    "meta": {
        "months":    all_periods,
        "banks":     all_entities,
        "display":   display,
        "groups":    bank_group,
        "generated": datetime.today().strftime('%Y-%m-%d'),
        "source":    "CNBV — Portafolio de Información, Sector 40 Banca Múltiple",
        "saldo_type": "130 (saldo puntual del mes)",
        "thresholds": {
            # CAMELS — calculados de distribución histórica 2014-2026
            # Dirección: 'high' = mayor es mejor, 'low' = menor es mejor
            "C": {
                "capital_activo": {"tLow": 0.084, "tHigh": 0.166, "dir": "high", "weight": 1.0}
            },
            "A": {
                "imor":  {"tLow": 0.0085, "tHigh": 0.0347, "dir": "low",  "weight": 0.40},
                "icor":  {"tLow": 0.953,  "tHigh": 1.791,  "dir": "high", "weight": 0.40},
                "tda":   {"tLow": 0.013,  "tHigh": 0.057,  "dir": "low",  "weight": 0.20}
            },
            "M": {
                "efic_margen": {"tLow": 0.595, "tHigh": 1.383, "dir": "low", "weight": 0.50},
                "efic_activo": {"tLow": 0.008, "tHigh": 0.032, "dir": "low", "weight": 0.50}
            },
            "E": {
                "roa": {"tLow": 0.004, "tHigh": 0.018, "dir": "high", "weight": 0.50},
                "roe": {"tLow": 0.028, "tHigh": 0.156, "dir": "high", "weight": 0.50}
            },
            "L": {
                # Para Sistema: umbral directo sobre liquidez (FD/Depósitos CP)
                # Para bancos individuales: percentil dentro del peer group
                "liquidez": {"tLow": 0.359, "tHigh": 1.255, "dir": "high", "weight": 1.0}
            },
            "S": {
                # MIF como proxy de sensibilidad (margen de intermediación)
                "mif": {"tLow": 0.022, "tHigh": 0.061, "dir": "high", "weight": 1.0}
            }
        },
        "ictl_thresholds": {
            # ICTL México — componentes disponibles (sin cartera ≤30d)
            # Pesos redistribuidos: ILON 40%, ICInt 30%, ITL 30%
            "ilon":  {"verde": 2.50, "amarillo": 1.50, "dir": "high", "peso": 0.40},
            "icint": {"verde": 2.52, "amarillo": 1.44, "dir": "high", "peso": 0.30},
            "itl":   {"verde": 0.40, "amarillo": 0.67, "dir": "low",  "peso": 0.30}
        },
        "camels_weights": {"C": 0.25, "A": 0.20, "M": 0.15, "E": 0.20, "L": 0.15, "S": 0.05},
        "peer_groups": {k: list(v) for k, v in GROUPS.items()}
    },
    "ind": ind,
    "der": der,
    "bal": bal
}

# ── Paso 7: escribir JSON ───────────────────────────────────────────────────
print(f"Escribiendo {FILE_OUT}...")
with open(FILE_OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

size_mb = os.path.getsize(FILE_OUT) / 1_048_576
print(f"✓ bancos_mx.json generado — {size_mb:.1f} MB")
print(f"  Bancos: {NB} | Períodos: {NM} | {all_periods[0]} → {all_periods[-1]}")
