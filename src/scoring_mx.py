"""
Motor de scoring IALT + IFB para la banca multiple de Mexico (Sakbe Consultores).

Port del motor de Ecuador (sakbe-monitor-bancos-ec/src/scoring.py, IALT v1.0 e
IFB v2.3) sobre docs/data/bancos_mx_v2.json. La maquinaria es la misma: escala,
bandas, CDF historica del grupo, historia propia, persistencia, scoring
continuo, renormalizacion en dos niveles, guardarrail de 70%, override de
capital y cortes 2,30 / 2,00 / 1,70 (sakbe_scoring_common.py, copia identica).

Lo que cambia para Mexico, y por que:

  IALT
  1. Grupos de pares = grupos de la CNBV por modelo de negocio (decision de
     Gustavo, 18-nov-2026), fijos, no por tamano. "Sin Clasificar" queda fuera.
  2. Se excluye del IALT el banco-mes cuya captacion tradicional es menor al
     20% del pasivo (mediana movil de 12 meses). Para esos bancos la fuga de
     depositos y la cobertura de caja no miden nada (decision 18-nov-2026).
  3. Solvencia = ICAP (CNBV). El piso de solvencia se activa cuando el banco
     queda bajo los minimos de la categoria I sin suplementos (ICAP 10,5%,
     CCB 8,5%, CCF 7%), no con el 9% de Ecuador: Famsa y Accendo cayeron con
     ICAP de 11,3% y 10,2%.
  4. Sin piso de liquidez: la CNBV no fija un minimo sobre su indicador de
     liquidez y el CCL regulatorio solo se publica trimestral.
  5. El ICAP sale un mes despues que el balance. En el ULTIMO mes se arrastra
     el ICAP del mes anterior (marca icap_arrastrado) para no perder el mes.
  6. Quiebre IFRS 9 de ene-2022: la morosidad salta (sistema 1,97% -> 2,55%)
     por cambio de criterio. La ventana de historia propia de las dos senales
     de morosidad no cruza el quiebre, y la variacion a 6 meses de ene a jun
     2022 se mide contra ene-2022.
  7. Eventos corporativos (EVENTOS): en los 6 meses desde el evento la senal
     de fuga de depositos vale 50 (neutra) en sus dos componentes, porque el
     salto viene de una transferencia de negocio y no de los depositantes.
     Citi Mexico se trata como banco nuevo desde dic-2024.

  IFB
  8. C = ICAP + CCF (capital fundamental), en lugar de PT/APR + FK/FI.
  9. L1 = indicador de liquidez de la CNBV (activos liquidos / pasivos
     liquidos). Equivale a la liquidez ampliada SIN descuentos: la CNBV no
     separa las inversiones por emisor.
 10. Override: el banco-mes bajo los minimos de categoria I topa en 2,29.
     Regla del silencio igual que Ecuador.
 11. Umbrales calibrados con la serie mexicana 2014-2026 (UMBRALES_MX), con
     regla explicita: saludable = percentil 25 ponderado por activo del lado
     bueno, alerta = percentil 90 ponderado del lado malo; ICAP y CCF usan el
     minimo regulatorio como alerta. PROPUESTA pendiente de aprobacion.

Uso: python3 src/scoring_mx.py docs/data/bancos_mx_v2.json docs/data/bancos_mx_v2.json
"""
import datetime as _dt
import json, math, sys

import numpy as np
import pandas as pd

from sakbe_scoring_common import CATEGORIAS, COBERTURA_MINIMA, TOPE_OVERRIDE, score_interp

BANCO_SISTEMA = "SISTEMA"

# ── IALT ───────────────────────────────────────────────────────────────────
IALT_SENALES = {"fuga_dep_6m": "bajo", "cobertura_caja": "bajo", "morosidad": "alto",
                "moro_delta_6m": "alto", "solvencia": "bajo"}
IALT_PESOS = {"fuga_dep_6m": 0.30, "cobertura_caja": 0.25, "morosidad": 0.20,
              "moro_delta_6m": 0.15, "solvencia": 0.10}
IALT_ALPHA_TRANSVERSAL = 0.6
IALT_VENTANA_HIST = 12
IALT_MIN_HIST = 6
IALT_BANDAS = [(75, "Rojo"), (60, "Naranja"), (45, "Amarillo"), (0, "Verde")]
PISO_IALT_MIN = 45.0

GRUPOS_IALT = ["G-7", "Bancos Cambiarios", "Inversión y Servicios Financieros",
               "Comercial Mediano", "Comercial Pequeño", "Créditos a los Hogares"]
CAPT_MINIMA = 0.20
CAPT_VENTANA = 12
QUIEBRE_IFRS9 = "2022-01"
QUIEBRE_FIN_DELTA = "2022-06"

# (clave CNBV, mes del evento, descripcion). Solo eventos verificados.
EVENTOS = [
    ("040002", "2024-12", "Banamex: separacion del negocio institucional hacia Citi Mexico"),
    ("040132", "2025-08", "Multiva: recibe el negocio fiduciario de CIBanco"),
    ("040128", "2025-09", "Kapital: compra de activos de Intercam"),
    ("040128", "2026-06", "Kapital: segunda incorporacion de activos de Intercam"),
]
REINICIO_SERIE = {"040124": "2024-12"}   # Citi Mexico: antes era Deutsche Bank / CBM Banco
EVENTO_MESES = 6

# ── IFB ────────────────────────────────────────────────────────────────────
IFB_PESOS = {"C": 0.25, "A": 0.20, "M": 0.15, "E": 0.20, "L": 0.15, "S": 0.05}
UMBRALES_MX = {   # (fuente, clave, t_bajo, t_alto, direccion, etiqueta, origen)
    "C": [("pt", "coef_basilea", 0.105, 0.195, "alto", "ICAP (capital neto / APSRT)", "R: 10,5% min. cat. I | C: P75 pond."),
          ("pt", "ccf", 0.070, 0.165, "alto", "Coef. capital fundamental", "R: 7% min. cat. I | C: P75 pond.")],
    "A": [("ind", "act_impr", 0.07, 0.14, "bajo", "Activos improductivos / activo", "C: P25 / P90 pond."),
          ("ind", "mor_total", 0.015, 0.035, "bajo", "IMOR", "C: P25 / P90 pond."),
          ("ind", "cob_prob", 0.95, 1.85, "alto", "ICOR", "C: P10 / P75 pond.")],
    "M": [("ind", "efic_margen", 0.48, 0.88, "bajo", "Gastos adm. / ingresos totales op.", "C: P25 / P90 pond."),
          ("ind", "efic_activo", 0.025, 0.050, "bajo", "Gastos adm. / activo promedio", "C: P25 / P90 pond.")],
    "E": [("ind", "roa", 0.006, 0.023, "alto", "ROA (CNBV)", "C: P10 / P75 pond."),
          ("ind", "roe", 0.07, 0.22, "alto", "ROE (CNBV)", "C: P10 / P75 pond.")],
    "L": [("ind", "liq_ampliada", 0.25, 0.52, "alto", "Liquidez CNBV (activos liq. / pasivos liq.)", "C: P10 / P75 pond."),
          ("ind", "dep_cartera", 0.82, 1.09, "alto", "Depositos / cartera bruta", "C: P10 / P75 pond.")],
    "S": [("ind", "vulner_pat", -0.06, 0.007, "bajo", "Vulnerabilidad patrimonial", "C: P25 / P90 pond.")],
}
IFB_PESOS_INTERNOS = {"L": [0.60, 0.40]}
IFB_TITULARES = {"C": ("pt", "coef_basilea"), "A": ("ind", "mor_total"), "M": ("ind", "efic_margen"),
                 "E": ("ind", "roa"), "L": ("ind", "liq_ampliada"), "S": ("ind", "vulner_pat")}


# ── utilidades ─────────────────────────────────────────────────────────────
def _df(data, sec, key):
    b, m = data["meta"]["banks"], data["meta"]["months"]
    mat = data.get(sec, {}).get(key)
    if mat is None:
        return pd.DataFrame(np.nan, index=b, columns=m)
    return pd.DataFrame(mat, index=b, columns=m, dtype=float)

def _jm(df, nd=None):
    if nd is not None:
        df = df.round(nd)
    return [[None if pd.isna(v) else float(v) for v in row] for row in df.to_numpy()]

def _jl(df):
    return [[None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v) for v in row]
            for row in df.to_numpy()]


def preparar(data):
    """Reinicio de series (Citi Mexico) y arrastre del ICAP en el ultimo mes."""
    b, m = data["meta"]["banks"], data["meta"]["months"]
    for ent, desde in REINICIO_SERIE.items():
        if ent not in b or desde not in m:
            continue
        i, j0 = b.index(ent), m.index(desde)
        for sec in ("ind", "pt", "bal", "pt_notas"):
            for mat in data.get(sec, {}).values():
                for j in range(j0):
                    mat[i][j] = None
    arr = [[False] * len(m) for _ in b]
    pt = data["pt"]
    for i in range(len(b)):
        if pt["coef_basilea"][i][-1] is None and pt["coef_basilea"][i][-2] is not None \
                and data["bal"]["activo"][i][-1] is not None:
            for k in ("coef_basilea", "ccb", "ccf", "bajo_minimo_cat1"):
                pt[k][i][-1] = pt[k][i][-2]
            arr[i][-1] = True
    data["pt"]["icap_arrastrado"] = arr


def grupos_ialt(data):
    b, m = data["meta"]["banks"], data["meta"]["months"]
    capt = _df(data, "ind", "capt_pasivo")
    capt_s = capt.T.rolling(CAPT_VENTANA, min_periods=1).median().T
    g = pd.DataFrame(np.nan, index=b, columns=m, dtype=object)
    for ent in b:
        if ent == BANCO_SISTEMA:
            g.loc[ent] = "Sistema"; continue
        gc = data["meta"]["grupo_cnbv"].get(ent)
        if gc not in GRUPOS_IALT:
            continue
        g.loc[ent] = np.where(capt_s.loc[ent] >= CAPT_MINIMA, gc, "Excluido")
        g.loc[ent] = g.loc[ent].where(capt_s.loc[ent].notna())
    return g


def _pct_cdf(valores, grupo):
    out = pd.DataFrame(np.nan, index=valores.index, columns=valores.columns)
    ind = [x for x in valores.index if x != BANCO_SISTEMA]
    v = valores.loc[ind].to_numpy(dtype=float); g = grupo.loc[ind].to_numpy(dtype=object)
    cdfs = {n: np.sort(v[(g == n) & ~np.isnan(v)]) for n in GRUPOS_IALT}
    ok = np.isin(g, GRUPOS_IALT) & ~np.isnan(v)
    glob = np.sort(v[ok])
    def p(x, c):
        if c is None or c.size == 0 or pd.isna(x):
            return np.nan
        return (np.searchsorted(c, x, "left") + np.searchsorted(c, x, "right")) / (2.0 * len(c))
    for e in valores.index:
        if e == BANCO_SISTEMA:
            out.loc[e] = [p(x, glob) for x in valores.loc[e]]
        else:
            out.loc[e] = [p(x, cdfs.get(gg)) for x, gg in zip(valores.loc[e], grupo.loc[e])]
    return out


def _historia(s, dirn, months, cortar_en=None):
    shifted = s.shift(1, axis=1)
    if cortar_en is not None:
        # la ventana de historia no cruza el quiebre: lo previo no existe para los meses posteriores
        j0 = months.index(cortar_en)
        pre = shifted.copy()
        post_cols = months[j0:]
        base = shifted[post_cols].copy()
        base[months[j0]] = np.nan   # el mes del quiebre no ve historia previa
        med_post = base.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).median().T
        sd_post = base.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).std().T
        med = pre.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).median().T
        sd = pre.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).std().T
        med[post_cols] = med_post; sd[post_cols] = sd_post
    else:
        med = shifted.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).median().T
        sd = shifted.T.rolling(IALT_VENTANA_HIST, min_periods=IALT_MIN_HIST).std().T
    z = (s - med) / sd.replace(0, np.nan)
    if dirn == "bajo":
        z = -z
    return 100 / (1 + np.exp(-z.clip(-4, 4)))


def compute_persistencia(alerta, banks):
    NIV = {"Verde": 0, "Amarillo": 1, "Naranja": 2, "Rojo": 3}; inv = {v: k for k, v in NIV.items()}
    nb, nm = alerta.shape
    niv = [[NIV.get(alerta.iat[i, j]) for j in range(nm)] for i in range(nb)]
    rb_m = [[None] * nm for _ in range(nb)]; ra_m = [[None] * nm for _ in range(nb)]
    a12 = [[None] * nm for _ in range(nb)]; p12 = [[None] * nm for _ in range(nb)]
    for i in range(nb):
        rb = ra = 0
        for j in range(nm):
            n = niv[i][j]
            if n is None:
                rb = ra = 0; continue
            rb = rb + 1 if (j > 0 and niv[i][j - 1] == n) else 1
            ra = ra + 1 if n >= 2 else 0
            rb_m[i][j], ra_m[i][j] = rb, ra
            w = [niv[i][k] for k in range(max(0, j - 11), j + 1) if niv[i][k] is not None]
            a12[i][j] = sum(1 for x in w if x >= 2); p12[i][j] = inv[max(w)]
    buckets = [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 10**6, "6+")]
    acum = {l: [0, 0] for _, _, l in buckets}
    for i, bk in enumerate(banks):
        if bk == BANCO_SISTEMA:
            continue
        for j in range(nm - 6):
            r, f = ra_m[i][j], niv[i][j + 6]
            if r is None or f is None:
                continue
            for lo, hi, l in buckets:
                if lo <= r <= hi:
                    acum[l][0] += 1; acum[l][1] += f >= 2; break
    tasas = {l: {"n": n, "tasa": round(k / n * 100, 1) if n else None} for l, (n, k) in acum.items()}
    return {"racha_banda": rb_m, "racha_adversa": ra_m, "adversos_12m": a12, "peor_12m": p12,
            "tasas_escalamiento": tasas, "horizonte_tasas": 6, "buckets": [list(x) for x in buckets]}


def compute_ialt(data):
    banks, months = data["meta"]["banks"], data["meta"]["months"]
    dep = _df(data, "bal", "depositos"); efe = _df(data, "bal", "ictl_fondos")
    mor = _df(data, "ind", "mor_total"); icap = _df(data, "pt", "coef_basilea")
    bajo_min = _df(data, "pt", "bajo_minimo_cat1")
    grupo = grupos_ialt(data)

    delta = mor.diff(periods=6, axis=1)
    jq, jf = months.index(QUIEBRE_IFRS9), months.index(QUIEBRE_FIN_DELTA)
    for j in range(jq, jf + 1):
        delta[months[j]] = mor[months[j]] - mor[QUIEBRE_IFRS9]

    sen = {"cobertura_caja": efe / dep.where(dep > 0), "solvencia": icap,
           "fuga_dep_6m": dep.pct_change(periods=6, axis=1, fill_method=None),
           "morosidad": mor, "moro_delta_6m": delta}

    # eventos corporativos: fuga neutra durante EVENTO_MESES
    evento = pd.DataFrame(np.nan, index=banks, columns=months, dtype=object)
    for ent, mes, desc in EVENTOS:
        if ent in banks and mes in months:
            j0 = months.index(mes)
            for j in range(j0, min(j0 + EVENTO_MESES, len(months))):
                evento.iat[banks.index(ent), j] = desc

    sx, shf, score = {}, {}, {}
    for s, dirn in IALT_SENALES.items():
        v = sen[s]
        pr = _pct_cdf(v, grupo)
        sx[s] = (1 - pr) * 100 if dirn == "bajo" else pr * 100
        corte = QUIEBRE_IFRS9 if s in ("morosidad", "moro_delta_6m") else None
        h = _historia(v, dirn, months, corte)
        shf[s] = h.where(h.notna(), sx[s])
        score[s] = IALT_ALPHA_TRANSVERSAL * sx[s] + (1 - IALT_ALPHA_TRANSVERSAL) * shf[s]
    ev = evento.notna()
    for d_ in (sx, shf, score):
        d_["fuga_dep_6m"] = d_["fuga_dep_6m"].mask(ev, 50.0)

    bruto = sum(IALT_PESOS[s] * score[s] for s in IALT_SENALES)
    falta = None
    for s in IALT_SENALES:
        falta = score[s].isna() if falta is None else (falta | score[s].isna())
    valido = grupo.isin(GRUPOS_IALT + ["Sistema"])
    bruto = bruto.where(~falta & valido)

    piso_solv = (bajo_min == 1)
    ialt = bruto.mask(piso_solv.fillna(False) & (bruto < PISO_IALT_MIN), PISO_IALT_MIN).round(1)
    piso = pd.DataFrame(np.nan, index=banks, columns=months, dtype=object)
    piso = piso.mask(piso_solv.fillna(False), "solvencia").where(ialt.notna())

    def banda(x):
        if pd.isna(x):
            return None
        return next(n for c, n in IALT_BANDAS if x >= c)
    alerta = ialt.map(banda)

    res = {"IALT": _jm(ialt, 1), "IALT_sin_piso": _jm(bruto, 1), "alerta": _jl(alerta),
           "piso": _jl(piso), "grupo": _jl(grupo), "evento": _jl(evento.where(ialt.notna())),
           "persistencia": compute_persistencia(alerta, banks),
           "config": {"senales": IALT_SENALES, "pesos": IALT_PESOS,
                      "alpha_transversal": IALT_ALPHA_TRANSVERSAL, "ventana_hist": IALT_VENTANA_HIST,
                      "bandas": [[c, n] for c, n in IALT_BANDAS], "grupos": GRUPOS_IALT,
                      "base_percentil": "CDF historica del grupo CNBV",
                      "exclusion": f"captacion tradicional / pasivo < {CAPT_MINIMA:.0%} (mediana movil {CAPT_VENTANA}m)",
                      "piso_solvencia": "fuera de los minimos de categoria I sin suplementos (ICAP 10,5%, CCB 8,5%, CCF 7%)",
                      "piso_liquidez": "no aplica en Mexico", "piso_ialt_min": PISO_IALT_MIN,
                      "quiebre_ifrs9": QUIEBRE_IFRS9, "eventos": EVENTOS, "reinicio_serie": REINICIO_SERIE,
                      "generado": _dt.date.today().isoformat(), "ultimo_mes": months[-1]}}
    for s in IALT_SENALES:
        res[f"score_{s}"] = _jm(score[s], 1); res[f"val_{s}"] = _jm(sen[s], 5)
        res[f"pares_{s}"] = _jm(sx[s], 1); res[f"hist_{s}"] = _jm(shf[s], 1)
    return res


def _pesos(dim):
    n = len(UMBRALES_MX[dim]); p = IFB_PESOS_INTERNOS.get(dim)
    return list(p) if p else [1.0 / n] * n


def compute_ifb(data):
    banks, months = data["meta"]["banks"], data["meta"]["months"]
    nb, nm = len(banks), len(months)
    def cell(sec, key, i, j):
        try:
            v = data[sec][key][i][j]
        except (KeyError, IndexError, TypeError):
            return None
        return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v
    E = lambda: [[None] * nm for _ in range(nb)]
    dims = {d: E() for d in IFB_PESOS}; vals = {d: E() for d in IFB_PESOS}
    ifb, cat, cob, ren, ovr = E(), E(), E(), E(), E()
    ultimo = []
    for i in range(nb):
        js = [j for j in range(nm) if cell("pt", "coef_basilea", i, j) is not None]
        ultimo.append(js[-1] if js else -1)
    for i in range(nb):
        es_sis = banks[i] == BANCO_SISTEMA
        for j in range(nm):
            if cell("bal", "activo", i, j) is None:
                continue
            d, cd = {}, {}
            for dim, lst in UMBRALES_MX.items():
                sc = [score_interp(cell(s, k, i, j), lo, hi, dr) for s, k, lo, hi, dr, _, _ in lst]
                pes = _pesos(dim); num = den = 0.0
                for x, p in zip(sc, pes):
                    if x is not None:
                        num += x * p; den += p
                d[dim] = num / den if den > 0 else None; cd[dim] = den / sum(pes)
            if es_sis:
                d["S"], cd["S"] = 2.0, 1.0
            tot = tw = ct = 0.0
            for k, w in IFB_PESOS.items():
                dims[k][i][j] = None if d[k] is None else round(d[k], 4)
                if d[k] is not None:
                    tot += d[k] * w; tw += w; ct += w * cd[k]
            v = round(tot / tw, 3) if tw > 0 else None
            if v is not None and ct < COBERTURA_MINIMA:
                v = None
            motivo = None
            if v is not None and not es_sis:
                bm = cell("pt", "bajo_minimo_cat1", i, j)
                if bm == 1:
                    motivo = "bajo_minimos_categoria_I"
                elif cell("pt", "coef_basilea", i, j) is None and j > ultimo[i] and ultimo[i] >= 0:
                    motivo = "sin_reporte_de_capital"
                if motivo:
                    v = min(v, TOPE_OVERRIDE)
            ifb[i][j] = v
            if v is not None:
                cat[i][j] = next(n for c, n in CATEGORIAS if v >= c)
                cob[i][j] = round(ct * 100, 1); ren[i][j] = ct < 0.999; ovr[i][j] = motivo
            for k, (s, key) in IFB_TITULARES.items():
                r = cell(s, key, i, j); vals[k][i][j] = None if r is None else round(r, 6)
    res = {"IFB": ifb, "categoria": cat, "cobertura_pct": cob, "renormalizado": ren,
           "override_capital": ovr,
           "config": {"pesos": IFB_PESOS, "categorias": [[c, n] for c, n in CATEGORIAS],
                      "cobertura_minima": COBERTURA_MINIMA, "tope_override": TOPE_OVERRIDE,
                      "override": "fuera de minimos de categoria I (ICAP 10,5% / CCB 8,5% / CCF 7%) o silencio sostenido",
                      "titulares": {k: f"{s}.{v}" for k, (s, v) in IFB_TITULARES.items()},
                      "indicadores": {dim: [{"fuente": s, "clave": k, "t_bajo": lo, "t_alto": hi,
                                             "direccion": dr, "etiqueta": l, "origen": o,
                                             "peso_interno": round(p, 6)}
                                            for (s, k, lo, hi, dr, l, o), p in zip(lst, _pesos(dim))]
                                      for dim, lst in UMBRALES_MX.items()},
                      "estado_umbrales": "PROPUESTA 18-nov-2026, pendiente de aprobacion",
                      "excepciones": {"S_sistema_fija_en_2": "Igual que Ecuador."},
                      "generado": _dt.date.today().isoformat()}}
    for k in IFB_PESOS:
        res[f"dim_{k}"] = dims[k]; res[f"val_{k}"] = vals[k]
    return res


def main(inp, out):
    with open(inp, encoding="utf-8") as f:
        data = json.load(f)
    preparar(data)
    data["ialt"] = compute_ialt(data)
    data["ifb"] = compute_ifb(data)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Listo:", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
