"""Convierte docs/index.html del monitor de Ecuador en el tablero de Mexico.

Cada reemplazo debe encontrarse al menos una vez; si el HTML de Ecuador cambia y un
reemplazo deja de aplicar, el script se detiene en lugar de generar un tablero a medias.
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()


def R(old, new, count=None):
    global s
    n = s.count(old)
    if n == 0 or (count is not None and n != count):
        raise SystemExit(f"Reemplazo no aplicado ({n} coincidencias): {old[:90]!r}")
    s = s.replace(old, new)


# Identidad y datos
R("Monitor Bancos Privados Ecuador", "Monitor Banca Múltiple México")
R("Monitor de Bancos Privados Ecuador", "Monitor de Banca Múltiple México")
R("fetch('data/bancos.json'", "fetch('data/bancos_mx_v2_scored.json'")

# Pestaña IALT: se dibuja al abrirla (en Ecuador quedaba en blanco hasta cambiar de banco o periodo)
R("""  document.getElementById('pane-'+id).classList.add('active');
  event.target.classList.add('active');
}""", """  document.getElementById('pane-'+id).classList.add('active');
  event.target.classList.add('active');
  if (id === 'ialt' && DATA) renderIALT();
}""")
R("""  if (btn) btn.classList.add('active');
}""", """  if (btn) btn.classList.add('active');
  if (id === 'ialt' && DATA) renderIALT();
}""")

# Tarjetas KPI sin ninguna dato en la serie (indicadores que la CNBV no publica): no se dibujan
R("kpis.forEach(k => {", "kpis.forEach(k => {\n    if (Array.isArray(k.serie) && !k.serie.some(v => v != null)) return;")
R("kpis.forEach(k=>{", "kpis.forEach(k=>{\n    if (Array.isArray(k.serie) && !k.serie.some(v => v != null)) return;")

# Cartera
R("['Por vencer','No devenga intereses','Vencida'],", "['Etapa 1','Etapa 2','Etapa 3'],")
R("{ label:'Mora Productivo',", "{ label:'Mora Comercial',")
R("{ label:'Mora Microcrédito',", "{ label:'Mora Vivienda',")
R("""      <div class="chart-wrap">
        <div class="chart-title">Cartera vencida: antigüedad — cartera consumo</div>""",
  """      <div class="chart-wrap" style="display:none">
        <div class="chart-title">Cartera vencida: antigüedad — cartera consumo</div>""")

# Liquidez y depositos
R("Fondos disponibles vs. Obligaciones con el público", "Efectivo vs. Depósitos del público")
R("'Oblig. con el Público'", "'Depósitos del público'")
R("label:'Oblig. público'", "label:'Depósitos del público'")
R("label:'Fondos disponibles'", "label:'Efectivo y equivalentes'")
R("label:'Oblig. con el público'", "label:'Depósitos del público'")
R("'Liquidez (FD/Dep CP)'", "'Liquidez CNBV'")
R("""    { label:'Mín. referencia (14%)', data:flat(0.14),""", """    { label:'Alerta IFB (25%)', data:flat(0.25),""")

# Solvencia: ICAP y minimos de la categoria I de alertas tempranas
R('<span class="ref-tag">Mín. 9% LGISF Art. 47</span>', '<span class="ref-tag">Mín. 10,5% categoría I</span>', 2)
R("Coef. Solvencia (PT/APR) por banco", "ICAP por banco")
R("Coeficiente de Solvencia (PT/APR) — Histórico", "ICAP (capital neto / APSRT) — Histórico")
R("{ label:'Solvencia (PT/APR)', data:getSerie('coef_basilea',bi,'pt')", "{ label:'ICAP', data:getSerie('coef_basilea',bi,'pt')")
R("{ label:'Mín. regulatorio (9%)', data:flat(0.09),", "{ label:'Mín. categoría I (10,5%)', data:flat(0.105),")
R("{ label:'Coef. Solvencia (PT/APR)', v:getPT('coef_basilea')", "{ label:'ICAP', v:getPT('coef_basilea')")
R("{ label:'PT/Activos Totales',       v:getPT('pt_activos'),   prev:prevMi!=null?getPT('pt_activos',bi,prevMi):null,   serie:getSerie('pt_activos',bi,'pt'),",
  "{ label:'Capital básico (CCB)',     v:getPT('ccb'),          prev:prevMi!=null?getPT('ccb',bi,prevMi):null,          serie:getSerie('ccb',bi,'pt'),")
R("{ label:'PT Constituido',           v:getPT('pt_const'),     prev:prevMi!=null?getPT('pt_const',bi,prevMi):null,     fmt:fmtM, serie:getSerie('pt_const',bi,'pt'),",
  "{ label:'Capital fundamental (CCF)', v:getPT('ccf'),         prev:prevMi!=null?getPT('ccf',bi,prevMi):null,          serie:getSerie('ccf',bi,'pt'),")
R("r.sol<0.09?C_RED:r.sol<0.11?'#c8820a':C_TEAL", "r.sol<0.105?C_RED:r.sol<0.12?'#c8820a':C_TEAL")
R("{ label:'Mínimo 9%', data:rows.map(()=>9),", "{ label:'Mínimo 10,5%', data:rows.map(()=>10.5),")
R("{ label:'Mínimo 9%', data:DATA.meta.months.map(()=>0.09),", "{ label:'Mínimo 10,5%', data:DATA.meta.months.map(()=>0.105),")
R("{ label:'Coef. Solvencia', data:", "{ label:'ICAP', data:")
R("""<th class="num">Coef. Solvencia</th><th class="num">PT/Activos</th>
    <th class="num">PT Constituido</th><th class="num">APR</th><th class="num">ICN (FK/FI)</th>""",
  """<th class="num">ICAP</th><th class="num">CCB</th>
    <th class="num">CCF</th><th class="num">Categoría I</th><th class="num"></th>""")
R("cb:DATA.pt.coef_basilea?.[i]?.[mi]??null, pa:DATA.pt.pt_activos?.[i]?.[mi]??null,",
  "cb:DATA.pt.coef_basilea?.[i]?.[mi]??null, pa:DATA.pt.ccb?.[i]?.[mi]??null,")
R("pt:DATA.pt.pt_const?.[i]?.[mi]??null, apr:DATA.pt.apr?.[i]?.[mi]??null,",
  "pt:DATA.pt.ccf?.[i]?.[mi]??null, apr:DATA.pt.bajo_minimo_cat1?.[i]?.[mi]??null,")
R("const cbOk = r.cb!=null&&r.cb>=0.09;", "const cbOk = r.cb!=null&&r.apr!==1;")
R("""<td class="num">${fmtPct(r.pa)}</td><td class="num">${fmtM(r.pt)}</td>
      <td class="num">${fmtM(r.apr)}</td><td class="num">${fmtPct(r.icn)}</td></tr>`;""",
  """<td class="num">${fmtPct(r.pa)}</td><td class="num">${fmtPct(r.pt)}</td>
      <td class="num">${r.apr==null?'—':(r.apr===1?'Fuera':'Cumple')}</td><td class="num"></td></tr>`;""")
R("coef_basilea:'Coef. Solvencia'", "coef_basilea:'ICAP'")

# IALT: textos de las senales, piso y estacionalidad
R("desc:'Variación de las obligaciones con el público a 6 meses. Una caída es la señal más temprana de retiro de fondeo.'",
  "desc:'Variación de los depósitos del público a 6 meses, en pesos corrientes. Una caída es la señal más temprana de retiro de fondeo.'")
R("desc:'Fondos disponibles sobre depósitos totales. Cuánto del pasivo con el público está respaldado en caja.'",
  "desc:'Efectivo y equivalentes sobre depósitos del público. Cuánto de los depósitos está respaldado en caja.'")
R("desc:'Cartera improductiva sobre cartera bruta. La mora deteriora el flujo antes que el balance.'",
  "desc:'IMOR de la CNBV: cartera en etapa 3 sobre cartera total. La mora deteriora el flujo antes que el balance.'")
R("desc:'Patrimonio técnico sobre activos ponderados por riesgo. El colchón que absorbe pérdidas antes de tocar la liquidez.'",
  "desc:'ICAP: capital neto sobre activos ponderados sujetos a riesgo total. El colchón que absorbe pérdidas antes de tocar la liquidez.'")
R("nombre:'Solvencia (Basilea)'", "nombre:'Solvencia (ICAP)'")
R("solvencia: `Basilea por debajo del 9% regulatorio.`",
  "solvencia: `Fuera de los mínimos de la categoría I (ICAP 10,5%, CCB 8,5%, CCF 7%).`")
R("la señal de fuga de depósitos mide la variación a 6 meses, y en junio la base es diciembre, el pico anual por décimo tercer sueldo y cierre fiscal. Sobre 12 años y 23 bancos, la mediana del compuesto es 41 en diciembre y 55 en junio.",
  "la señal de fuga de depósitos mide la variación a 6 meses y arrastra el calendario del fondeo, con diciembre alto por aguinaldo y cierres de año. En México la mediana del IALT del sistema es 47 en diciembre y 57 en septiembre, y de mayo a junio sube en 8 de 12 años.")
R("Ver el lineamiento, sección 11.", "Ver la metodología del IALT México, sección 11.")
R("const IALT_GRUPO_LBL = { Sistemico:'Sistémico', Mediano:'Mediano', Pequeno:'Pequeño', Sistema:'Sistema' };",
  "const IALT_GRUPO_LBL = { Sistema:'Sistema', Excluido:'Fuera del IALT (captación menor al 20% del pasivo)' };")

R("Activos, Cartera y Obligaciones — histórico", "Activos, Cartera y Depósitos — histórico")
R("const ley = x.clave === 'coef_basilea' ? ' (LGISF Art. 47)' : '';", "const ley = x.clave === 'coef_basilea' ? ' (mínimo categoría I)' : '';")
R("ambos:     `Basilea bajo 9% y liquidez bajo 14% al mismo tiempo.`", "ambos:     `Fuera de los mínimos de la categoría I.`")
R("'Banco privado') + ' · '", "'Banca múltiple') + ' · '")
R("<br>Esta capa sustituyó a las pendientes S3/S6 del ICTL, que medidas contra los datos resultaron invertidas: el IALT revierte a la media y su pendiente pasada anticipa lo contrario de lo que parece. Ver el lineamiento, sección 9.",
  "<br>La pendiente del IALT no se usa como señal: el índice revierte a la media y su pendiente pasada anticipa lo contrario de lo que parece. Ver la metodología del IALT México, sección 10.")

open(dst, "w", encoding="utf-8").write(s)
print("ok", dst)
