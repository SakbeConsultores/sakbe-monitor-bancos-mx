"""
Limpieza del ICAP de banca multiple (CNBV) para el Monitor Bancario Mexico.

Entrada:  data/ICAP_Banca_Multiple.csv  (extraido de los PDF ICAP_BM_AAAAMM.pdf,
          por texto o por OCR; una fila por institucion y mes)
Salida:   data/icap_mx.csv  (una fila por clave CNBV y mes, en fraccion)
          data/icap_nombres_sin_clave.csv  (nombres que no tienen balance en
          sh_datos_40 y por eso no entran al monitor)

Reglas (revision del 18-nov-2026):
  1. Las marcas de nota al pie pegadas al nombre ("6/", "7/", "CIBanco6/") se
     separan en la columna nota_revision. Caen casi siempre en bancos con el
     ICAP en revision (Famsa 2019-2020, Accendo y ABC Capital 2021, Bankaool
     2025, CIBanco sep-2025) y son informacion, no ruido. La cifra que trae el
     CSV es la de la tabla; la corregida por Banxico, cuando existe, vive en
     el texto de la nota y NO esta en este archivo (ej. Famsa jul-2019: tabla
     12.51, nota 10.88).
  2. Nombre -> clave CNBV con la tabla NOMBRE_A_CLAVE. Los renombres se
     verificaron contra la continuidad de la clave en sh_datos_40.
  3. CCB de OCR con valor < 5 y ICAP > 8 se anula: en 2013 el OCR leyo la
     columna de variacion (186 filas con valores de 1 a 3).
  4. La categoria del PDF solo se conserva en filas extraidas por texto. En
     OCR es inservible (abr-2013 pone 17 bancos en categoria V con ICAP 15).
  5. bajo_minimo_cat1 = ICAP < 10.5% o CCB < 8.5% o CCF < 7%. Son los minimos
     de la categoria I SIN suplemento de sistemico ni colchon contraciclico;
     es una aproximacion conservadora a "fuera de categoria I", no la
     categoria oficial.
"""
import os, re, sys
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_IN  = os.path.join(BASE, "data", "ICAP_Banca_Multiple.csv")
F_OUT = os.path.join(BASE, "data", "icap_mx.csv")
F_SIN = os.path.join(BASE, "data", "icap_nombres_sin_clave.csv")

MIN_ICAP, MIN_CCB, MIN_CCF = 10.5, 8.5, 7.0

NOMBRE_A_CLAVE = {
    "TOTAL BANCA MÚLTIPLE": "5",
    # G-7
    "BANAMEX": "040002",
    "BBVA MÉXICO": "040012", "BBVA BANCOMER": "040012",
    "SANTANDER": "040014", "SANTANDER SERFIN": "040014",
    "HSBC": "040021",
    "INBURSA": "040036",
    "SCOTIABANK": "040044", "SCOTIABANK INVERLAT": "040044",
    "BANORTE": "040072", "MERCANTIL DEL NORTE": "040072",
    # Cambiarios
    "MONEX": "040112",
    "INTERCAM BANCO": "040136", "INTER BANCO": "040136",
    "CIBANCO": "040143", "CONSULTORÍA INTERNACIONAL": "040143",
    "BANCO BASE": "040145",
    # Inversion y servicios
    "INVEX": "040059",
    "AFIRME": "040062",
    "AMERICAN EXPRESS": "040103",
    "BANK OF AMERICA": "040106",
    "MUFG BANK": "040108", "BANK OF TOKYO-MITSUBISHI UFJ": "040108",
    "TOKYO-MITSUBISHI UFJ": "040108", "TOKYO-MITSUBISHI": "040108", "TOKYO": "040108",
    "J.P. MORGAN": "040110",
    "CITI MÉXICO": "040124", "CBM BANCO": "040124",
    "DEUTSCHE BANK": "040124", "DEUTSCHE": "040124",
    "CREDIT SUISSE": "040126", "BANCO CREDIT SUISSE": "040126",
    "BARCLAYS": "040129", "BARCLAYS BANK": "040129",
    "BIAFIRME": "040139", "UBS": "040139", "UBS BANK": "040139",
    "PAGATODO": "040148",
    "BANCO S3": "040160",
    "BNP PARIBAS MÉXICO": "040164",
    # Comercial mediano
    "BANCO DEL BAJÍO": "040030", "DEL BAJÍO": "040030", "BAJÍO": "040030",
    "INTERACCIONES": "040037",
    "BANCA MIFEL": "040042", "MIFEL": "040042",
    "BANREGIO": "040058",
    "VE POR MÁS": "040113",
    "MULTIVA": "040132",
    "SABADELL": "040156",
    # Comercial pequeno
    "BANSÍ": "040060",
    "ACCENDO BANCO": "040102", "INVESTA BANK": "040102",
    "KAPITAL": "040128", "KAPITAL (ANTES AUTOFIN)": "040128", "AUTOFIN": "040128",
    "ACTINVER": "040133",
    "UALÁ": "040138", "BANCO UALÁ": "040138", "ABC CAPITAL": "040138",
    "# ABC CAPITAL (ANTES BANCO AMIGO)": "040138", "BANCO AMIGO": "040138", "AMIGO": "040138",
    "BANKAOOL": "040147",
    "INMOBILIARIO MEXICANO": "040150",
    "DONDÉ BANCO": "040151", "FUNDACIÓN DONDÉ": "040151",
    "BANCREA": "040152", "BANCO BANCREA": "040152",
    "COVALTO": "040154", "BANCO COVALTO": "040154",
    "BANCO COVALTO (ANTES: FINTERRA)": "040154", "FINTERRA": "040154",
    "ICBC": "040155",
    "SHINHAN": "040157",
    "MIZUHO BANK": "040158",
    "BANK OF CHINA": "040159",
    "KEB HANA MÉXICO": "040162", "KEB HANA BANK": "040162",
    # Creditos a los hogares
    "BANCO AZTECA": "040127", "AZTECA": "040127",
    "COMPARTAMOS": "040130",
    "BANCO AHORRO FAMSA": "040131", "AHORRO FAMSA": "040131",
    "BANCOPPEL": "040137",
    "CONSUBANCO": "040140",
    "VOLKSWAGEN BANK": "040141", "VOLKSWAGEN": "040141",
    "BANFELIZ": "040149", "BANFELIZ (ANTES FORJADORES)": "040149", "FORJADORES": "040149",
    "BANCO BINEO": "040165",
    "HEY BANCO": "040167",
    "OPENBANK": "040169", "OPENBANK MÉXICO": "040169",
    "REVOLUT BANK": "040170",
    "BANCO PLATA": "040171",
    "NUBANK": "040638",
    # Historicos con balance en sh_datos_40
    "SERFÍN": "040003",
    "BBVA BANCOMER SERVICIOS": "040017", "BBVA SERVICIOS": "040017", "BANCOMER SERVS.": "040017",
    "GE MONEY": "040022",
    "IXE": "040032",
    "BANCEN": "040086",
    "ING": "040116", "ING BANK": "040116",
    "BANCO WAL-MART": "040134", "WAL-MART": "040134",
    "THE BANK OF NEW YORK MELLON": "040144", "NEW YORK MELLON": "040144", "NY MELLON": "040144",
    "BICENTENARIO": "040146", "BANCO BICENTENARIO": "040146",
}

def main():
    d = pd.read_csv(F_IN, encoding="utf-8-sig", dtype={"periodo": str})
    m = d["institucion"].str.extract(r"^(.*?)\s*(\d/)?\s*$")
    d["nombre"] = m[0].str.strip()
    d["nota_revision"] = m[1]
    d["clave"] = d["nombre"].str.upper().map(NOMBRE_A_CLAVE)

    sin = (d[d.clave.isna()].groupby("nombre")
           .agg(n=("periodo", "size"), desde=("periodo", "min"), hasta=("periodo", "max"))
           .reset_index())
    sin.to_csv(F_SIN, index=False)
    d = d[d.clave.notna()].copy()

    ocr = d.extraccion.eq("ocr")
    d.loc[ocr & (d.CCB < 5) & (d.ICAP > 8), "CCB"] = pd.NA
    d["categoria_pdf"] = d["categoria"].where(~ocr)

    dup = d.duplicated(["clave", "periodo"], keep=False)
    if dup.any():
        print("ERROR: clave-periodo duplicado\n", d[dup][["periodo", "nombre", "clave"]])
        sys.exit(1)

    d["bajo_minimo_cat1"] = ((d.ICAP < MIN_ICAP) | (d.CCB < MIN_CCB) | (d.CCF < MIN_CCF))
    out = d[["periodo", "clave", "nombre", "ICAP", "CCB", "CCF", "categoria_pdf",
             "bajo_minimo_cat1", "nota_revision", "extraccion", "archivo"]].copy()
    for c in ("ICAP", "CCB", "CCF"):
        out[c] = out[c] / 100.0
    out = out.sort_values(["clave", "periodo"])
    out.to_csv(F_OUT, index=False)
    print(f"icap_mx.csv: {len(out)} filas, {out.clave.nunique()} claves, "
          f"{out.periodo.min()}-{out.periodo.max()}")
    print(f"nombres sin clave: {len(sin)} ({int(sin.n.sum())} filas)")
    print(f"marcas de nota: {out.nota_revision.notna().sum()} | bajo minimo cat I: "
          f"{int(out.bajo_minimo_cat1.sum())}")

if __name__ == "__main__":
    main()
