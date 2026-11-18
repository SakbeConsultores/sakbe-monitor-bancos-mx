"""
Núcleo compartido de scoring IFC / IFB — Sakbé Consultores.

Este archivo es CANÓNICO y vive por duplicado en dos repos:

    sakbe-monitor-cooperativas/src/sakbe_scoring_common.py
    sakbe-monitor-bancos-ec/src/sakbe_scoring_common.py

Las dos copias deben ser IDÉNTICAS BYTE A BYTE. La prueba
`test_scoring_common.py` verifica el SHA-256 declarado más abajo; si alguien
edita una copia y no la otra, la prueba falla en el repo desactualizado.

La razón de esta disciplina es concreta: mantener el mismo cálculo en dos
lugares fue lo que hizo que el ICTL del reporte y el del tablero divergieran
hasta 45 puntos en un mismo banco.

Origen: "Solicitud de cambios — Alineación metodológica IFC / IFB" v1.0
(6 ago 2026), secciones 4 y 5, decisiones D1 y D2.

FASE 0. Este módulo todavía NO está conectado a ningún cálculo. Se introduce
primero, con sus pruebas, para que las fases siguientes solo tengan que
sustituir llamadas. Ver el plan de implementación F0..F7.
"""
import math

__version__ = "2.0.0-f0"


# ═════════════════════════════════════════════════════════════════════════
# Escala y nomenclatura unificadas (sección 4 de la solicitud)
# ═════════════════════════════════════════════════════════════════════════
#
# Una sola tabla de clasificación para IFC e IFB. Los cortes son los del IFC,
# que son los únicos con validación empírica detrás (Cámara de Comercio de
# Ambato, CREA, Policía Nacional). El IFB abandona 2,50 / 2,00 / 1,50.
#
# Los nombres de color (Verde / Amarillo / Naranja / Rojo) quedan RESERVADOS
# para el IALT, que es un índice de riesgo de liquidez, escala 0-100 y
# dirección invertida. Que ambos índices usaran los mismos nombres con
# direcciones opuestas era la colisión del hallazgo 3.8.

CORTE_SOLIDO = 2.30
CORTE_ESTABLE = 2.00
CORTE_ATENCION = 1.70

CATEGORIAS = [
    (CORTE_SOLIDO,   "Solido"),
    (CORTE_ESTABLE,  "Estable"),
    (CORTE_ATENCION, "Atencion"),
    (0.0,            "Fragil"),
]

# Tope del índice cuando se activa un override de capital. Se expresa en
# función del corte para que siga al corte si algún día se mueve, en vez de
# quedar como el literal 2.29 que hoy está en el IFC (cambio C4).
TOPE_OVERRIDE = round(CORTE_SOLIDO - 0.01, 2)

# Cobertura mínima de peso para emitir índice (sección 6, guardarraíl).
# Si las dimensiones excluidas por falta de dato suman más de 30% del peso
# original, no se emite índice: un compuesto armado con dos tercios del
# modelo se lee como si fuera completo y engaña.
COBERTURA_MINIMA = 0.70


def clasificar(v):
    """Categoría unificada de un índice en escala 1,0-3,0. None si no hay dato."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return next(nombre for corte, nombre in CATEGORIAS if v >= corte)


# ═════════════════════════════════════════════════════════════════════════
# Scoring interpolado (sección 5 de la solicitud, decisión D1)
# ═════════════════════════════════════════════════════════════════════════

def score_interp(v, t_bajo, t_alto, direccion):
    """Score continuo 1.0-3.0. t_bajo < t_alto siempre.

    direccion 'alto': valores altos son buenos.
    direccion 'bajo': valores bajos son buenos.

    Sustituye a `_score1()` en bancos y a `_score_umbral()` en cooperativas.
    Bajo el esquema discreto anterior todo el tramo entre umbrales valía 2,0;
    ahora ese tramo se abre linealmente entre 1,0 y 3,0 con 2,0 en el centro.

    Fuera del rango el score se RECORTA: un banco con Basilea de 25% saca lo
    mismo que uno con 12%. Es una limitación aceptada de un índice acotado y
    hay que declararla en la metodología v2.0.
    """
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    span = t_alto - t_bajo
    if span <= 0:
        raise ValueError(
            f"t_alto debe ser mayor que t_bajo (recibido t_bajo={t_bajo}, t_alto={t_alto})"
        )
    if direccion == "alto":
        pos = (v - t_bajo) / span
    elif direccion == "bajo":
        pos = (t_alto - v) / span
    else:
        raise ValueError(f"direccion debe ser 'alto' o 'bajo' (recibido {direccion!r})")
    return 1.0 + 2.0 * min(max(pos, 0.0), 1.0)


def score_interp_series(serie, t_bajo, t_alto, direccion):
    """Versión vectorizada para pandas. Equivalente exacto a score_interp()
    celda a celda, incluido el recorte y el NaN pasante.

    Se usa en el motor de cooperativas, que trabaja con DataFrames completos
    en vez de celda a celda como el de bancos. La equivalencia entre ambas
    rutas está cubierta por las pruebas.
    """
    span = t_alto - t_bajo
    if span <= 0:
        raise ValueError(
            f"t_alto debe ser mayor que t_bajo (recibido t_bajo={t_bajo}, t_alto={t_alto})"
        )
    if direccion == "alto":
        pos = (serie - t_bajo) / span
    elif direccion == "bajo":
        pos = (t_alto - serie) / span
    else:
        raise ValueError(f"direccion debe ser 'alto' o 'bajo' (recibido {direccion!r})")
    return 1.0 + 2.0 * pos.clip(lower=0.0, upper=1.0)


# ═════════════════════════════════════════════════════════════════════════
# Traducción de los umbrales heredados de cooperativas
# ═════════════════════════════════════════════════════════════════════════

def umbrales_desde_verde_amarillo(verde, amarillo):
    """(verde, amarillo) del viejo `_score_umbral()` -> (t_bajo, t_alto).

    En cooperativas los umbrales se declaraban como el par (verde, amarillo),
    cuyo orden depende de la dirección: para 'alto' verde > amarillo, para
    'bajo' verde < amarillo. score_interp() exige siempre t_bajo < t_alto, así
    que la traducción es tomar el mínimo y el máximo.

    En bancos no hace falta: IFB_INDICADORES ya guarda (t_bajo, t_alto) en el
    orden correcto.
    """
    return min(verde, amarillo), max(verde, amarillo)
