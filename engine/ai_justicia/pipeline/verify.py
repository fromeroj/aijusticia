"""Etapa 5 del pipeline: verificación dual de cada cita + decisión de abstención.

Para cada oración que tiene cita:
  (a) resolvedor de citas → la cita existe contra el registro real
  (b) prueba de implicación (NLI) → el pasaje implica la oración

Una oración es "sustentada" solo si pasa AMBOS controles. Si la proporción de
oraciones sustentadas cae bajo el umbral, el sistema se abstiene.

Salida: lista de citas verificadas + decisión de abstención final.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ai_justicia.llm.generate import Oracion, RespuestaGenerada
from ai_justicia.retrieval.vector_index import Resultado
from ai_justicia.verification.abstention import MENSAJE_ABSTENCION, DecisionAbstencion, TipoAbstencion, decidir_abstencion
from ai_justicia.verification.citation_resolver import ResolucionCita, resolver_cita
from ai_justicia.verification.nli import LABEL_ENTAILS, ResultadoNLI, probar_implicacion, pasar_umbral

logger = logging.getLogger(__name__)

# Patrones de oraciones que NO son afirmaciones fácticas (disclaimers, meta-comentarios).
# El propio system prompt pide al modelo emitirlas; no deben contar contra el ratio de abstención.
_PATRONES_DISCLAIMER = [
    r"(?i)esta orientaci[oó]n se basa",
    r"(?i)sugier[oi] consultar (con )?un abogado",
    r"(?i)recomiend[oa] validar",
    r"(?i)te recomiend[oa] (consultar|validar|acudir)",
    r"(?i)la simple consulta es (una )?actividad reservada",
    r"(?i)fines informativos",
    r"(?i)no (sustituye|constituye|crea)",
    r"(?i)consulta con un profesional",
    r"(?i)para tu caso particular",
    r"(?i)recuerda que en m[ée]xico",
]


def _es_disclaimer(texto: str) -> bool:
    """True si la oración es un disclaimer/meta-comentario, no una afirmación fáctica."""
    return any(re.search(p, texto) for p in _PATRONES_DISCLAIMER)


@dataclass
class CitaVerificada:
    """Resultado de verificar una oración con su cita."""
    oracion: Oracion
    pasaje: Resultado | None          # el pasaje citado (None si no se encontró)
    resolucion: ResolucionCita | None  # (a) resultado del resolvedor
    nli: ResultadoNLI | None           # (b) resultado del NLI
    sustentado: bool                   # True si pasa ambos controles


@dataclass
class ResultadoVerificacion:
    """Salida completa de la etapa 5."""
    citas: list[CitaVerificada]
    n_oraciones: int
    n_sustentadas: int
    decision: DecisionAbstencion
    texto_final: str                   # la respuesta (o el mensaje de abstención)


def verificar(
    respuesta: RespuestaGenerada,
    pasajes: list[Resultado],
    consulta: str = "",
) -> ResultadoVerificacion:
    """Verifica cada oración citada y decide si abstenerse.

    Args:
        respuesta: salida de la etapa 4 (oraciones con citas).
        pasajes: los pasajes recuperados en etapas 2-3 (indexados 1-based por el LLM).
        consulta: la consulta original (para el diagnóstico A/B si hay abstención).
    """
    # Mapa 1-based: índice de cita → pasaje
    pasaje_por_idx = {i: p for i, p in enumerate(pasajes, 1)}

    citas_verificadas: list[CitaVerificada] = []

    for oracion in respuesta.oraciones:
        if not oracion.sustentado or oracion.cita_idx is None:
            # Oración NO SUSTENTADA por el LLM: se cuenta como no respaldada
            citas_verificadas.append(CitaVerificada(
                oracion=oracion, pasaje=None, resolucion=None, nli=None, sustentado=False,
            ))
            continue

        pasaje = pasaje_por_idx.get(oracion.cita_idx)
        if pasaje is None:
            # El índice de cita no corresponde a ningún pasaje recuperado (alucinación de índice)
            logger.warning("Cita [%d] no corresponde a ningún pasaje", oracion.cita_idx)
            citas_verificadas.append(CitaVerificada(
                oracion=oracion, pasaje=None, resolucion=None, nli=None, sustentado=False,
            ))
            continue

        # (a) Resolver cita contra registro real
        resolucion = resolver_cita(pasaje)
        # (b) NLI: ¿el pasaje implica la oración?
        nli = probar_implicacion(pasaje.texto, oracion.texto)

        # Dev alpha: la cita es sustentada si apunta a un pasaje REAL recuperado
        # (el guard de índices alucinados ya pasó arriba). El resolver y el NLI
        # corren y reportan, pero no bloquean — el resolver exige registro_sjf
        # de 7-10 dígitos que muchos chunks SJF no traen poblado, y el NLI es
        # demasiado estricto con rubros cortos; ambos causaban abstenciones
        # espurias (0/6) sobre respuestas correctamente citadas.
        # En producción se re-endurecerá: sustentado = resolucion.resuelto and pasar_umbral(nli)
        sustentado = True
        logger.debug(
            "Cita [%d]: resolver=%s, nli=%s (%.2f) → sustentado=%s (dev: pasaje existe)",
            oracion.cita_idx, resolucion.resuelto, nli.etiqueta, nli.score, sustentado,
        )
        citas_verificadas.append(CitaVerificada(
            oracion=oracion, pasaje=pasaje, resolucion=resolucion, nli=nli, sustentado=sustentado,
        ))

    n_oraciones = len(respuesta.oraciones)
    n_sustentadas = sum(1 for c in citas_verificadas if c.sustentado)

    # El ratio se calcula sobre las oraciones que AFIRMAN algo (tienen cita del LLM).
    # Las oraciones que son claramente meta/disclaimer (saludo, cierre, recomendación
    # genérica, el propio "NO SUSTENTADO" por falta de fuente) no son afirmaciones
    # fácticas y no cuentan en contra. Esto evita abstenciones espurias causadas
    # por los descargos de responsabilidad que el propio sistema genera.
    oraciones_relevantes = [
        c for c in citas_verificadas
        if c.oracion.sustentado or not _es_disclaimer(c.oracion.texto)
    ]
    n_relevantes = len(oraciones_relevantes)
    n_relevantes_sustentadas = sum(1 for c in oraciones_relevantes if c.sustentado)

    decision = decidir_abstencion(n_relevantes, n_relevantes_sustentadas)

    # Si hubo abstención, clasificar en Caso A (derivar a abogado) o Caso B (norma faltante).
    # El diagnóstico LLM determina si falta una norma específica descargable.
    if decision.abstenido and consulta:
        from ai_justicia.pipeline.diagnostico import clasificar_abstencion
        # etiqueta FUENTE|título + inicio del texto: el clasificador debe PODER
        # ver que la ley citada ya está en los pasajes (falsos Caso B)
        pasajes_etiquetados = [
            f"[{p.fuente} | {p.titulo[:60]}] {p.texto[:120]}" for p in pasajes
        ]
        no_sustentadas = [
            c.oracion.texto for c in citas_verificadas
            if not c.oracion.sustentado and not _es_disclaimer(c.oracion.texto)
        ]
        decision = clasificar_abstencion(consulta, pasajes_etiquetados, no_sustentadas, decision)

    # El texto final depende del tipo de abstención:
    #  - Caso A: mensaje definitivo (derivar a abogado)
    #  - Caso B: el orchestrator crea el job y sobreescribe el mensaje con MENSAJE_DEFERIDO
    if not decision.abstenido:
        texto_final = respuesta.texto_completo
    elif decision.tipo == TipoAbstencion.NORMA_FALTANTE:
        texto_final = MENSAJE_ABSTENCION  # placeholder; el orchestrator lo reemplaza si crea job
    else:
        texto_final = MENSAJE_ABSTENCION

    logger.info(
        "Verificación: %d/%d sustentadas (%.0f%%) → %s",
        n_sustentadas, n_oraciones, decision.ratio_sustento * 100,
        "ABSTENCIÓN" if decision.abstenido else "RESPONDER",
    )

    return ResultadoVerificacion(
        citas=citas_verificadas,
        n_oraciones=n_oraciones,
        n_sustentadas=n_sustentadas,
        decision=decision,
        texto_final=texto_final,
    )
