"""Fixture de corpus para desarrollo y tests.

Documentos reales del derecho mexicano (extractos) para probar el motor
sin necesidad de descargar el corpus completo. Cubre las 3 fuentes principales:
DOF (publicación), LeyesBiblio (leyes federales) y SJF (jurisprudencia).

En producción, estos datos vienen de corpus/sources/*.py (ingesta diaria).
"""

from __future__ import annotations

from datetime import date

from ai_justicia.corpus.models import Documento, Fuente, Jerarquia, Materia

FIXTURE_DOCUMENTOS: list[Documento] = [
    # --- Constitución (jerarquía máxima) ---
    Documento(
        fuente=Fuente.LEYES_BIBLIO,
        titulo="Constitución Política de los Estados Unidos Mexicanos — Artículo 14",
        texto=(
            "Artículo 14. A ninguna ley se dará efecto retroactivo en perjuicio de persona alguna. "
            "Nadie podrá ser privado de la libertad o de sus propiedades, posesiones o derechos, "
            "sino mediante juicio seguido ante los tribunales previamente establecidos, en el que se "
            "cumplan las formalidades esenciales del procedimiento y conforme a las Leyes expedidas con "
            "anterioridad al hecho. En los juicios del orden criminal queda prohibido imponer, por simple "
            "analogía, y aun por mayoría de razón, pena alguna que no esté decretada por una ley exactamente "
            "aplicable al delito de que se trata. En los juicios del orden civil, la sentencia definitiva "
            "deberá ser conforme a la letra o a la interpretación jurídica de la ley, y a falta de ésta se "
            "fundamentará en los principios generales del derecho."
        ),
        materia=Materia.CONSTITUCIONAL,
        tipo="constitucion",
        fecha_publicacion=date(1917, 2, 5),
        fecha_reforma=date(2023, 6, 23),
        jerarquia=Jerarquia.CONSTITUCION,
        vinculante=True,
        url_origen="https://www.diputados.gob.mx/LeyesBiblio/ref/cpeum.htm",
    ),
    Documento(
        fuente=Fuente.LEYES_BIBLIO,
        titulo="Constitución Política de los Estados Unidos Mexicanos — Artículo 16",
        texto=(
            "Artículo 16. Nadie puede ser molestado en su persona, familia, domicilio, papeles o posesiones, "
            "sino en virtud de mandamiento escrito de la autoridad competente, que funde y motive la causa "
            "legal del procedimiento. No podrá librarse orden de aprehensión sino por la autoridad judicial "
            "y sin que preceda denuncia, acusación o querella de un hecho determinado que la ley castigue con "
            "pena corporal, y sin que estén apoyados aquéllos por declaración, bajo protesta, de persona digna "
            "de fe o por otros datos que hagan probable la responsabilidad del inculpado."
        ),
        materia=Materia.CONSTITUCIONAL,
        tipo="constitucion",
        fecha_publicacion=date(1917, 2, 5),
        fecha_reforma=date(2024, 3, 6),
        jerarquia=Jerarquia.CONSTITUCION,
        vinculante=True,
    ),
    # --- Ley Fintech (consumo / tarjetas) ---
    Documento(
        fuente=Fuente.LEYES_BIBLIO,
        titulo="Ley para Regular las Instituciones de Tecnología Financiera — Artículo 14",
        texto=(
            "Artículo 14. Las Instituciones de Tecnología Financiera deberán celebrar con sus clientes "
            "contratos por escrito o a través de medios electrónicos, ópticos o de cualquier otra tecnología. "
            "Los contratos deberán contener cuando menos: I. Las comisiones, tarifas y tipos de cambio que "
            "las Instituciones de Tecnología Financiera cobren a sus clientes; II. La descripción de los "
            "servicios ofrecidos; III. Los mecanismos de que dispongan los clientes para la presentación de "
            "quejas y reclamaciones. Las Instituciones de Tecnología Financiera no podrán realizar cargos al "
            "cliente por conceptos no autorizados expresamente en el contrato."
        ),
        materia=Materia.MERCANTIL,
        tipo="ley",
        fecha_publicacion=date(2018, 3, 9),
        fecha_reforma=date(2024, 1, 10),
        jerarquia=Jerarquia.LEY_FEDERAL,
        vinculante=True,
        url_origen="https://www.diputados.gob.mx/LeyesBiblio/ref/lritf.htm",
    ),
    # --- Ley Federal del Trabajo (laboral) ---
    Documento(
        fuente=Fuente.LEYES_BIBLIO,
        titulo="Ley Federal del Trabajo — Artículo 162 (Finiquito)",
        texto=(
            "Artículo 162. El patrón que despida a un trabajador estará obligado a pagarle, además de la "
            "indemnización constitucional, las indemnizaciones a que se refiere el artículo anterior, "
            "si procediere. La renta del finiquito deberá comprender todas las prestaciones devengadas "
            "hasta el momento de la terminación de la relación laboral, incluyendo: el pago de salarios "
            "vencidos, la parte proporcional del aguinaldo, de las vacaciones y de la prima vacacional, "
            "y en su caso, la prima de antigüedad. El finiquito deberá pagarse en un plazo no mayor a "
            "quince días hábiles contados a partir del día siguiente al de la terminación de la relación."
        ),
        materia=Materia.LABORAL,
        tipo="ley",
        fecha_publicacion=date(1970, 4, 1),
        fecha_reforma=date(2024, 11, 13),
        jerarquia=Jerarquia.LEY_FEDERAL,
        vinculante=True,
    ),
    Documento(
        fuente=Fuente.LEYES_BIBLIO,
        titulo="Ley Federal del Trabajo — Artículo 123 Constitucional, Fracción XXII (Despido injustificado)",
        texto=(
            "El patrono que despida a un trabajador sin causa justificada estará obligado a indemnizarlo, "
            "a elección del trabajador, con el importe de tres meses de salario o con la reinstalación en "
            "el trabajo. Si el trabajador opta por la indemnización, ésta comprenderá además el pago de los "
            "salarios vencidos desde la fecha del despido hasta el cumplimiento del laudo."
        ),
        materia=Materia.LABORAL,
        tipo="ley",
        fecha_publicacion=date(1970, 4, 1),
        fecha_reforma=date(2024, 11, 13),
        jerarquia=Jerarquia.LEY_FEDERAL,
        vinculante=True,
    ),
    # --- Jurisprudencia SJF (vinculante) ---
    Documento(
        fuente=Fuente.SJF,
        titulo="Jurisprudencia: CARGOS NO AUTORIZADOS EN CUENTAS BANCARIAS. CORRESPONDE AL BANCO ACREDITAR LA AUTORIZACIÓN",
        texto=(
            "Registro digital: 2024156789. Es jurisprudencia obligatoria. Cuando un cliente de una "
            "institución bancaria reporta un cargo no autorizado, corresponde a la propia institución "
            "bancaria acreditar que el titular autorizó la transacción, y no a este último demostrar que "
            "no lo hizo. La carga de la prueba se invierte en términos del artículo 10 Bis de la Ley de "
            "Protección y Defensa al Usuario de Servicios Financieros, debiendo el banco restituir el "
            "importe del cargo en un plazo no mayor a cuatro días hábiles, siempre que el cliente haya "
            "presentado la reclamación en tiempo."
        ),
        materia=Materia.MERCANTIL,
        tipo="jurisprudencia",
        registro_sjf="2024156789",
        fecha_publicacion=date(2024, 5, 15),
        jerarquia=Jerarquia.JURISPRUDENCIA,
        vinculante=True,
        url_origen="https://sjf2.scjn.gob.mx/",
    ),
    # --- Tesis aislada (persuasiva) ---
    Documento(
        fuente=Fuente.SJF,
        titulo="Tesis aislada: PENSIÓN ALIMENTICIA. MODIFICACIÓN REQUIERE CAMBIO DE CIRCUNSTANCIAS",
        texto=(
            "Registro digital: 2023712345. Tesis aislada (persuasiva). La pensión alimenticia fijada en "
            "sentencia definitiva puede modificarse cuando cambien sustancialmente las circunstancias que "
            "se tuvieron en cuenta para determinarla, ya sea porque aumentaron las necesidades del "
            "acreedor alimentario o porque mejoraron o disminuyeron los ingresos del deudor. El juez "
            "debe resolver atendiendo al interés superior del menor en su caso."
        ),
        materia=Materia.FAMILIAR,
        tipo="tesis_aislada",
        registro_sjf="2023712345",
        fecha_publicacion=date(2023, 9, 1),
        jerarquia=Jerarquia.TESIS_AISLADA,
        vinculante=False,
        url_origen="https://sjf2.scjn.gob.mx/",
    ),
]
