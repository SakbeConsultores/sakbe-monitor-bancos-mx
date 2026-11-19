"""
ETL v2 - Monitor Bancario Mexico (Sakbe Consultores), 18-nov-2026.

Genera docs/data/bancos_mx_v2.json con la MISMA estructura que bancos.json del
monitor de Ecuador (meta, ind, pt, bal; matrices [banco][mes]) para portar el
scoring IALT / IFB v2.3 con el menor numero de cambios. No toca bancos_mx.json
(prototipo de junio, que sigue alimentando docs/index.html).

Uso:
  python3 src/icap_mx.py                       # antes, si cambio el ICAP
  python3 src/etl_mx_v2.py <sh_datos_40.csv>   # ruta al CSV grande de la CNBV

Decisiones de diseno (ver README_v2 al final de este docstring):
  - Perimetro: tipo de saldo 130 = la institucion sin consolidar. El 133 es
    consolidado con sus SOFOM ER (guia CUB R12-A de la CNBV). La diferencia en
    capital contable es <= 1.1% y en activo <= 3% (Banregio, Bajio, Inbursa,
    Afirme, Bancrea, Ve por Mas). Los comunicados de prensa de la CNBV usan el
    133, asi que el total del sistema aqui queda ~0.2% por debajo del publicado.
  - Panel: 2014-01 a ultimo mes. Se leen 12 meses previos para los flujos.
  - Flujos: el estado de resultados de la CNBV es ACUMULADO DEL ANO (se
    reinicia en enero). Se pasan a 12 meses: F12(t) = YTD(t) + YTD(dic t-1)
    - YTD(t-12); en diciembre F12 = YTD.
  - depositos = deposito de exigibilidad inmediata + plazo del publico en
    general + cuenta global sin movimientos. Excluye mercado de dinero y
    titulos emitidos (fondeo mayorista), equivalente a "obligaciones con el
    publico" de la SB de Ecuador.
  - pasivo_liquido = definicion CNBV de pasivo circulante (dep. exigibilidad
    inmediata + prestamos interbancarios inmediatos y de corto plazo). La CNBV
    no separa el plazo por vencimiento, asi que NO es el "dep_corto_plazo" de
    Ecuador (vista + plazo <= 90 dias).
  - liquidez (ind) = indicador oficial CNBV = activos liquidos / pasivos
    liquidos. Coincide con la liquidez ampliada SIN descuentos: la CNBV no
    separa inversiones por emisor, asi que los factores 85% / 70% del IFB
    de Ecuador no se pueden aplicar.
  - act_impr = 1 - activos productivos / activo, con la definicion de activos
    productivos de las notas CNBV (efectivo + inversiones + operaciones con
    instrumentos financieros y derivados + cartera etapas 1 y 2).
  - efic_margen = gastos de administracion / ingresos totales de la operacion
    (despues de estimaciones, antes de gastos), el analogo del "margen
    financiero" de la SB. PENDIENTE de confirmar con Gustavo.
  - pt.coef_basilea = ICAP (fraccion) de data/icap_mx.csv. El ICAP se publica
    con un mes mas de rezago que el balance: el ultimo mes queda sin dato.
  - Grupo de pares: grupo de la CNBV (catalogo), decidido por Gustavo el
    18-nov-2026. ind.capt_pasivo (captacion tradicional / pasivo) queda
    disponible para excluir del IALT a los bancos que casi no captan.
"""
import csv, json, os, sys, datetime
from collections import defaultdict
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_INST = os.path.join(BASE, "data", "cat_instituciones_40.csv")
F_ICAP = os.path.join(BASE, "data", "icap_mx.csv")
F_OUT  = os.path.join(BASE, "docs", "data", "bancos_mx_v2.json")
INICIO = "201401"
LECTURA_DESDE = "201301"
SALDO = 130
SISTEMA = "SISTEMA"

C = {  # concepto CNBV -> clave interna
    # balance (saldos)
    40100001: "activo", 40100096: "pasivos", 40100002: "patrimonio_bal",
    40100045: "efectivo", 40100051: "inversiones", 40100052: "inv_neg_sr",
    40100053: "inv_cyv_sr", 40100059: "op_derivados_act",
    40100185: "cartera_bruta", 40100224: "cart_etapa12", 40100341: "cart_etapa3",
    40100031: "cart_prov", 40100553: "adjudicados",
    40100085: "captacion_trad", 40100079: "dep_vista", 40100081: "dep_plazo",
    40100082: "dep_mdo_dinero", 40100083: "titulos_emitidos", 40100084: "cta_global",
    40100087: "pi_inmediato", 40100088: "pi_corto",
    40100263: "cart_etapa1", 40100302: "cart_etapa2", 40100551: "cart_neta",
    # resultados (acumulados del ano)
    40100006: "ing_int", 40100007: "gto_int", 40100008: "margen_fin",
    40100131: "eprc_res", 40100170: "ing_tot_op", 40100011: "gastos_adm",
    40100013: "resultado", 40100010: "com_cobradas", 40100167: "com_pagadas",
    40100012: "resultado_op",
    # indicadores CNBV
    40200017: "imor", 40200033: "imora", 40200096: "icor", 40200001: "roa",
    40200002: "roe", 40200032: "liquidez", 40200037: "tasa_pasiva",
    40200218: "mif", 40200018: "imor_comercial", 40200019: "imor_consumo",
    40200020: "imor_vivienda",
}
FLUJOS = ["ing_int", "gto_int", "margen_fin", "eprc_res", "ing_tot_op", "gastos_adm", "resultado",
          "resultado_op"]

def leer(path):
    keep = set(map(str, C))
    rows = []
    with open(path, encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        for sec, con, ent, per, sal, val in r:
            if sal != str(SALDO) or per < LECTURA_DESDE or con not in keep:
                continue
            if ent != "5" and not ent.startswith("04"):
                continue
            try:
                rows.append((ent, per, C[int(con)], float(val)))
            except ValueError:
                pass
    return pd.DataFrame(rows, columns=["ent", "per", "k", "v"])

def a12(ytd):
    """ytd: DataFrame [ent x per YYYYMM] acumulado del ano -> flujo 12 meses."""
    cols = list(ytd.columns)
    out = pd.DataFrame(np.nan, index=ytd.index, columns=cols)
    for c in cols:
        y, m = int(c[:4]), int(c[4:])
        if m == 12:
            out[c] = ytd[c]; continue
        dic, prev = f"{y-1}12", f"{y-1}{m:02d}"
        if dic in ytd.columns and prev in ytd.columns:
            out[c] = ytd[c] + ytd[dic] - ytd[prev]
    return out

def prom12(s):
    return s.T.rolling(12, min_periods=12).mean().T

def main(path):
    raw = leer(path)
    per_all = sorted(raw.per.unique())
    ents = sorted(e for e in raw[(raw.k == "activo") & (raw.per >= INICIO)].ent.unique())
    S = {k: g.pivot_table(index="ent", columns="per", values="v").reindex(index=ents, columns=per_all)
         for k, g in raw.groupby("k")}
    for k in C.values():
        S.setdefault(k, pd.DataFrame(np.nan, index=ents, columns=per_all))

    F = {f"{k}_12m": a12(S[k]) for k in FLUJOS}
    prov = -S["cart_prov"]                       # en balance viene con signo negativo
    act_prom = prom12(S["activo"])
    dep = S["dep_vista"].fillna(0) + S["dep_plazo"].fillna(0) + S["cta_global"].fillna(0)
    dep = dep.where(S["dep_vista"].notna() | S["dep_plazo"].notna())
    act_prod = (S["efectivo"].fillna(0) + S["inversiones"].fillna(0)
                + S["op_derivados_act"].fillna(0) + S["cart_etapa12"].fillna(0))
    act_prod = act_prod.where(S["activo"].notna())
    pas_liq = S["dep_vista"].fillna(0) + S["pi_inmediato"].fillna(0) + S["pi_corto"].fillna(0)
    pas_liq = pas_liq.where(S["dep_vista"].notna())

    def div(a, b):
        b = b.where(b > 0)
        return a / b

    IND = {
        "mor_total": S["imor"], "imora": S["imora"], "cob_prob": S["icor"],
        "roa": S["roa"], "roe": S["roe"], "liquidez": S["liquidez"],
        "liq_ampliada": S["liquidez"],
        "dep_cartera": div(dep, S["cartera_bruta"]),
        "efic_margen": div(F["gastos_adm_12m"], F["ing_tot_op_12m"]),
        "efic_activo": div(F["gastos_adm_12m"], act_prom),
        "act_impr": 1 - div(act_prod, S["activo"]),
        "vulner_pat": div(S["cart_etapa3"] - prov, S["patrimonio_bal"]),
        "capt_pasivo": div(S["captacion_trad"], S["pasivos"]),
        "cobertura_caja": div(S["efectivo"], dep),
        "mif": S["mif"], "tasa_pasiva": S["tasa_pasiva"],
        "mor_comercial": S["imor_comercial"], "mor_consumo": S["imor_consumo"],
        "mor_vivienda": S["imor_vivienda"],
        # Claves con el nombre que usa el dashboard de Ecuador (se rotulan para Mexico en el tablero)
        "mor_prod": S["imor_comercial"],      # rotulo MX: mora comercial
        "mor_micro": S["imor_vivienda"],      # rotulo MX: mora vivienda
        "act_prod_tot": div(act_prod, S["activo"]),
        "intermediacion": div(S["cartera_bruta"], dep),
        "margen_act": div(F["resultado_op_12m"], act_prom),
        "margen_pat": div(F["resultado_op_12m"], prom12(S["patrimonio_bal"])),
    }
    BAL = {k: S[k] for k in ["activo", "pasivos", "patrimonio_bal", "efectivo", "inversiones",
                             "inv_neg_sr", "inv_cyv_sr", "cartera_bruta", "cart_etapa12",
                             "cart_etapa3", "adjudicados", "captacion_trad", "dep_vista",
                             "dep_plazo", "dep_mdo_dinero", "titulos_emitidos"]}
    BAL.update({"cart_prov": S["cart_prov"], "depositos": dep, "ictl_fondos": S["efectivo"],
                "pasivo_liquido": pas_liq, "activos_productivos": act_prod,
                "cart_neta": S["cart_neta"], "cart_pv": S["cart_etapa1"], "cart_cndi": S["cart_etapa2"],
                "cart_vencida": S["cart_etapa3"],
                # estado de resultados acumulado del ano, como en Ecuador (cascada de resultados)
                "resultado": S["resultado"], "pyg_ingresos": S["ing_int"], "pyg_int_causados": S["gto_int"],
                "pyg_provisiones": S["eprc_res"], "pyg_gastos_op": S["gastos_adm"],
                "pyg_com_netas": S["com_cobradas"] - S["com_pagadas"]})
    BAL.update(F)
    # Montos en MILES de pesos, la misma unidad que el JSON de Ecuador (miles de USD)
    BAL = {k: v / 1000.0 for k, v in BAL.items()}

    # ICAP
    ic = pd.read_csv(F_ICAP, dtype={"periodo": str, "clave": str})
    PT = {}
    for col, key in [("ICAP", "coef_basilea"), ("CCB", "ccb"), ("CCF", "ccf")]:
        PT[key] = ic.pivot_table(index="clave", columns="periodo", values=col).reindex(index=ents, columns=per_all)
    PT["bajo_minimo_cat1"] = (ic.assign(b=ic.bajo_minimo_cat1.astype(float))
                              .pivot_table(index="clave", columns="periodo", values="b")
                              .reindex(index=ents, columns=per_all))
    NOTAS = {}
    for col, key in [("nota_revision", "nota_revision"), ("categoria_pdf", "categoria_pdf")]:
        NOTAS[key] = (ic.pivot(index="clave", columns="periodo", values=col)
                        .reindex(index=ents, columns=per_all))

    # recorte al panel y armado del JSON
    meses = [p for p in per_all if p >= INICIO]
    ids = [SISTEMA if e == "5" else e for e in ents]
    cat = pd.read_csv(F_INST, dtype=str).set_index("entidad")
    display = {i: ("Total Banca Múltiple" if e == "5" else cat.nombre_entidad.get(e, e))
               for i, e in zip(ids, ents)}
    grupo = {i: (None if e == "5" else cat.nombre_grupo.get(e, "Sin Clasificar"))
             for i, e in zip(ids, ents)}

    def mat(df, nd):
        df = df[meses]
        out = []
        for e in ents:
            row = []
            for v in df.loc[e].tolist():
                if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
                    row.append(None)
                else:
                    row.append(round(float(v), nd) if nd is not None else v)
            out.append(row)
        return out

    def matstr(df):
        df = df[meses]
        return [[(None if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v))
                 for v in df.loc[e].tolist()] for e in ents]

    data = {
        "meta": {
            "months": [f"{p[:4]}-{p[4:]}" for p in meses],
            "banks": ids, "display": display, "grupo_cnbv": grupo,
            "generated": datetime.date.today().isoformat(),
            "pais": "MX", "moneda": "MXN (pesos corrientes)", "unidad_bal": "miles de pesos",
            "fuente": "CNBV Portafolio de Informacion, sector 40 Banca Multiple, saldo 130 "
                      "(institucion sin consolidar); ICAP de los PDF ICAP_BM_AAAAMM",
            "cierres": {"040131": "2020-06", "040102": "2021-09", "040143": "2025-10"},
            "version_etl": "v2 (18-nov-2026)",
        },
        "ind": {k: mat(v, 6) for k, v in IND.items()},
        "pt": {k: mat(v, 6) for k, v in PT.items()},
        "pt_notas": {k: matstr(v) for k, v in NOTAS.items()},
        "bal": {k: mat(v, 1) for k, v in BAL.items()},
    }
    with open(F_OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{F_OUT}: {os.path.getsize(F_OUT)/1e6:.1f} MB | {len(ids)} entidades | "
          f"{data['meta']['months'][0]} a {data['meta']['months'][-1]}")

if __name__ == "__main__":
    main(sys.argv[1])
