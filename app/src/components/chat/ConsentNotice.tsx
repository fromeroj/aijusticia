"use client";

/**
 * Leyenda de envío (chat público, antes de hacer el caso).
 * Se muestra bajo los mensajes, ENCIMA del botón enviar.
 */
export function ConsentNotice() {
  return (
    <div className="px-4 pb-1.5 pt-2">
      <p className="mx-auto max-w-2xl text-center text-[11px] leading-snug text-gray-400">
        Al enviar esta pregunta, autorizo que esta conversación —{" "}
        <span className="text-gray-500">
          anónimizada (sin tu nombre ni datos que te identifiquen) — sea usada para mejorar el
          modelo. Entiendo que el contenido generado por IA es exclusivamente informativo. No
          constituye asesoramiento legal ni sustituye la consulta con un abogado colegiado, quien
          es el único profesional autorizado para brindar orientación jurídica formal.
        </span>
      </p>
    </div>
  );
}
