"use client";

/**
 * Nota de consentimiento informativo (modo abierto).
 * Se muestra bajo los mensajes, ENCIMA del botón enviar.
 */
export function ConsentNotice() {
  return (
    <div className="px-4 pb-1.5 pt-2">
      <p className="mx-auto max-w-2xl text-center text-[11px] leading-snug text-gray-400">
        ⓘ Al enviar aceptas que esta conversión pueda usarse de forma anónima para mejorar el
        servicio y entrenar la IA jurídica mexicana.{" "}
        <span className="text-gray-500">No pedimos tu nombre ni datos personales.</span>
      </p>
    </div>
  );
}
