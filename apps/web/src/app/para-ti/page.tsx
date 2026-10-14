"use client";

import {
  MessageCircleQuestion, FileSearch, BookOpenCheck, Lock,
  Handshake, FolderOpen, ShieldCheck, Wallet, MapPin, Clock,
} from "lucide-react";
import { PathLanding } from "@/components/marketing/PathLanding";

export default function ParaTi() {
  return (
    <PathLanding
      color="bg-[#047857]"
      colorHover="hover:bg-[#064e3b]"
      colorSoft="bg-[#047857]/10 text-[#047857]"
      emoji="🧑‍⚖️"
      publico="Para personas"
      titular="Saber tus derechos no debe costar una fortuna"
      promesa="Platica tu caso como se lo contarías a un amigo abogado. La IA lo entrevista, busca la ley de tu estado y te orienta gratis con citas exactas. Si el caso va en serio, un abogado verificado lo retoma con tu expediente listo — desde $100 MXN."
      features={[
        {
          icon: <MessageCircleQuestion className="h-5 w-5" />,
          titulo: "Entrevista que entiende tu lengua",
          texto: "No formularios: conversación. La IA pregunta solo lo que la ley necesita — dónde vive la menor, si firmaron contrato, cuánto tiempo llevas en el trabajo — y en español mexicano.",
        },
        {
          icon: <FileSearch className="h-5 w-5" />,
          titulo: "La ley de TU estado, no de cualquier lado",
          texto: "El divorcio en Jalisco no es igual que en Yucatán. La IA detecta tu entidad y busca en la normativa aplicable: federal, estatal y jurisprudencia del SJF.",
        },
        {
          icon: <BookOpenCheck className="h-5 w-5" />,
          titulo: "Cada dicho, con su artículo",
          texto: "Nada de respuestas al aire: cada afirmación trae su artículo, fracción o tesis citada. Si la IA no encuentra base legal, te lo dice — no inventa.",
        },
        {
          icon: <FolderOpen className="h-5 w-5" />,
          titulo: "Tu expediente digital, cifrado",
          texto: "Todo tu caso queda en un expediente privado que solo tú controlas con tu frase de recuperación. Puedes subir contratos y documentos a tu bóveda cifrada.",
        },
        {
          icon: <Handshake className="h-5 w-5" />,
          titulo: "Enlace con abogado verificado",
          texto: "Cuando necesitas más que orientación, compartes tu expediente con un abogado de tu materia y entidad. Él ya llega conociendo tu caso — la consulta cuesta menos porque el diagnóstico está hecho.",
        },
        {
          icon: <ShieldCheck className="h-5 w-5" />,
          titulo: "Tú decides qué compartir",
          texto: "Tu expediente es tuyo: lo compartes con el abogado que elijas y lo revocas cuando quieras. Cada acceso queda registrado en tu auditoría.",
        },
      ]}
      proceso={[
        {
          titulo: "Cuenta tu caso (2–3 minutos)",
          texto: "Escribe o platica lo que te pasa: 'Me despidieron estando embarazada', 'Mi casero quiere subir la renta al doble'. Sin lenguaje jurídico.",
        },
        {
          titulo: "La IA entrevista (1–2 rondas de preguntas)",
          texto: "Te pregunta lo relevante según tu materia — y según la ley de tu estado. Entre menos federal tu asunto, más precisa la pregunta de ubicación.",
        },
        {
          titulo: "Recibe tu orientación con citas",
          texto: "Una respuesta clara: qué dice la ley, qué te protege, qué pasos seguir — cada afirmación con su fuente oficial verificada.",
        },
        {
          titulo: "¿Necesitas abogado? Compártelo con un clic",
          texto: "Si tu caso requiere acción formal (demanda, convenio, defensa), eliges un abogado verificado y le compartes tu expediente. Él da la respuesta formal.",
        },
      ]}
      accesoTitulo="Empieza gratis hoy"
      accesoItems={[
        "Orientación inicial 100% gratis, ilimitada",
        "Sin registro: solo guarda tu frase de recuperación",
        "Validación con abogado desde $100 MXN (pagable en OXXO)",
        "Acompañamiento mensual desde $250 MXN si tu caso es largo",
        "Cancela cuando quieras — tu expediente es tuyo",
      ]}
      ctaTexto="Preguntar ahora — sin registro"
      ctaHref="/onboarding/ciudadano"
      ctaLibreHref="/chat"
    />
  );
}
