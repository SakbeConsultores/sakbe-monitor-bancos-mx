# Calibración IFB e IALT México · v1.0 (propuesta)

Sakbé Consultores · 18 de noviembre de 2026

Motor: `src/scoring_mx.py`, port del motor de Ecuador (IALT v1.0, IFB v2.3). Datos: `docs/data/bancos_mx_v2.json` (CNBV saldo 130 + ICAP), 2014-01 a 2026-09. Resultado: `docs/data/bancos_mx_v2_scored.json`. Percentiles: `percentiles.json`.

## 1. Umbrales del IFB

Regla única para los 12 indicadores: el umbral saludable es el percentil 25 ponderado por activo del lado bueno y el de alerta el percentil 90 ponderado del lado malo, sobre 2014-2026 sin el agregado. ICAP y CCF usan como alerta el mínimo de la categoría I sin suplementos. Pesos de dimensión y de L (60/40) iguales a Ecuador.

| Dim | Indicador | Alerta | Saludable | En 1,00 / 3,00 (serie) | En 1,00 / 3,00 (12m) |
|---|---|---|---|---|---|
| C | ICAP | 10,5% (R) | 19,5% | 0,2 / 39,5 | 0,0 / 59,5 |
| C | Capital fundamental (CCF) | 7,0% (R) | 16,5% | 0,0 / 48,8 | 0,0 / 61,6 |
| A | Activos improductivos / activo | 14% | 7% | 30,7 / 37,6 | 16,6 / 47,3 |
| A | IMOR | 3,5% | 1,5% | 28,6 / 36,5 | 26,0 / 32,9 |
| A | ICOR | 95% | 185% | 23,7 / 26,0 | 19,0 / 24,8 |
| M | Gastos adm. / ingresos totales op. | 88% | 48% | 32,3 / 14,1 | 20,5 / 27,1 |
| M | Gastos adm. / activo promedio | 5,0% | 2,5% | 39,3 / 28,7 | 34,9 / 42,7 |
| E | ROA | 0,6% | 2,3% | 35,3 / 18,4 | 21,7 / 21,2 |
| E | ROE | 7% | 22% | 38,2 / 9,7 | 30,9 / 14,3 |
| L | Liquidez CNBV | 25% | 52% | 12,7 / 59,9 | 9,7 / 63,0 |
| L | Depósitos / cartera bruta | 0,82 | 1,09 | 43,7 / 33,2 | 27,2 / 45,5 |
| S | Vulnerabilidad patrimonial | +0,7% | −6,0% | 18,4 / 21,2 | 14,1 / 20,6 |

La saturación en 1,00 es alta en eficiencia, rentabilidad y depósitos/cartera. Viene de calibrar ponderado por activo: los umbrales los fija el G-7 y los bancos chicos y nuevos, que son la mayoría de las observaciones, quedan en la nota mínima. Es la misma opción que Ecuador v2.3. La alternativa, percentiles simples, da umbrales extremos (gastos/activo P90 simple 19,5%) que no discriminan.

La liquidez de la CNBV salió con umbrales casi idénticos a los de Ecuador (25%/52% contra 26%/52%), con base distinta: aquí no hay descuento por emisor.

## 2. Resultado

Categorías IFB, bancos: Sólido 31,5%, Estable 29,6%, En Atención 25,5%, Frágil 13,5% de la serie; últimos 12 meses Sólido 43,1% y Frágil 4,4%. El sistema queda en 2,45 (Sólido) a septiembre de 2026.

Bandas IALT, bancos: Verde 34,7%, Amarillo 41,8%, Naranja 20,6%, Rojo 2,9%. Se emite en 5.528 de 7.390 banco-mes; el resto son bancos excluidos (captación < 20% del pasivo), sin clasificar o sin historia suficiente.

Persistencia (sigue en Naranja o peor a 6 meses): sin racha 20,4%, racha de 1-2 meses 31,1%, de 3-5 meses 33,9%, de 6 o más 44,0%. Mismo patrón que Ecuador (21,3% a 47,3%).

Estacionalidad del SISTEMA, mediana del IALT por mes: marzo 44,8 y diciembre 46,6 contra junio 55,8 y septiembre 57,0. Amplitud de 12 puntos, del orden de la de Ecuador (14). En la mediana de los bancos individuales la amplitud es de 4,5 puntos.

Bancos nuevos (Nubank, Revolut, Banco Plata) no tienen IFB: sin 12 meses de flujos no hay ROA, ROE ni eficiencia y la cobertura cae bajo el 70%.

## 3. Casos

| Entidad | Evento | IFB | IALT |
|---|---|---|---|
| Famsa | Revocación jun-2020 | Frágil desde dic-2018 (18 meses antes) | Rojo desde ago-2019 |
| Accendo | Revocación sep-2021 | Frágil o En Atención todo 2020-2021; override desde may-2021 | Irregular: Verde a mediados de 2020, Naranja en jul-2021 |
| CIBanco | FinCEN 25-jun-2025, revocación oct-2025 | En Atención (no se espera señal: el origen es lavado) | Naranja en may-2025, un mes antes de la orden de FinCEN; Rojo en jul-2025 |
| Intercam | FinCEN 25-jun-2025, escisión ago-2025 | Sólido hasta ago-2025 | Naranja en dic-2024 y feb-2025; Rojo en ago-2025 |

Famsa queda sin ICAP en abril y mayo de 2020; la regla del silencio activa el override en esos meses.

## 4. Observación sobre la señal de fuga

Los depósitos van en pesos nominales. Con inflación, un banco con depósitos planos a 6 meses pierde en términos reales y el percentil lo castiga contra la historia de su grupo, que crece en promedio. BBVA y Santander salen en Naranja en septiembre de 2026 con variaciones de −0,2% y una cobertura de caja baja frente a la historia del G-7, en el mes estacionalmente más alto. Es un resultado defendible, pero conviene decidir si la fuga se mide en términos reales.

## 5. Decisiones pendientes

1. Aprobar la regla de calibración (P25 / P90 ponderados) o pedir variantes.
2. ¿Fuga de depósitos en términos nominales o deflactada por INPC?
3. Confirmar la lista de eventos corporativos (Banamex y Citi México dic-2024, Multiva ago-2025, Kapital sep-2025 y jun-2026). Quedan por revisar saltos de Bajío (feb-2022) y Banorte (ene-2022).
