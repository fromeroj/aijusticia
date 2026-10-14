"use client";

import {
  Search, FileText, BookOpenCheck, FolderOpen, Zap,
  Handshake, Clock, TrendingUp,
} from "lucide-react";
import { PathLanding } from "@/components/marketing/PathLanding";

export default function Abogados() {
  return (
    <PathLanding
      color="bg-[#c81e1e]"
      colorHover="hover:bg-[#a01717]"
      colorSoft="bg-[#c81e1e]/10 text-[#c81e1e]"
      emoji="⚖️"
      publico="Para abogados independientes"
      titular="Tu practicing, con la ley completa al instante"
      promesa="Preguntas técnicas, respuestas con artículos, fracciones, épocas y registros del SJF citados. Genera contratos y demandas con fundamento en minutos. Y recibe casos de tu especialidad con el expediente ya integrado."
      features={[
        {
          icon: <Search className="h-5 w-5" />,
          titulo: "Consultas técnicas directas",
          texto: "Sin entrevistas ciudadanas: preguntas como colega, la IA responde con precisión normativa. '¿Prescribe la acción de 123 en materia estatal?' — con la tesis exacta.",
        },
        {
          icon: <FileText className="h-5 w-5" />,
          titulo: "Generación de documentos con fundamento",
          texto: "'Genera un contrato de compraventa', 'redacta una demanda de alimentos'. Documentos ejecutables con placeholders y los artículos base citados al final.",
        },
        {
          icon: <BookOpenCheck className="h-5 w-5" />,
          titulo: "159,000+ fuentes indexadas",
          texto: "Leyes federales consolidadas, legislación de los 32 estados y jurisprudencia y tesis del SJF — con jerarquía normativa aplicada en el ranking.",
        },
        {
          icon: <FolderOpen className="h-5 w-5" />,
          titulo: "Casos que llegan listos",
          texto: "Los ciudadanos comparten su expediente contigo: hechos estructurados, documentos en la bóveda, preguntas y respuestas de la entrevista. Tú llegas al fondo del asunto.",
        },
        {
          icon: <Zap className="h-5 w-5" />,
          titulo: "Modo bufete privado (próximo)",
          texto: "Cuando trabajas en despacho, tus casos entrenan un modelo exclusivo de tu firma. Tu estrategia litigiosa jamás alimenta el modelo general.",
        },
        {
          icon: <TrendingUp className="h-5 w-5" />,
          titulo: "Crece tu práctica",
          texto: "Recibe casos de tu materia y entidad. El diagnóstico inicial ya está hecho por la IA — tú cobras por la respuesta formal, no por escuchar.",
        },
      ]}
      proceso={[
        {
          titulo: "Crea tu cuenta profesional",
          texto: "Cédula, especialidades y — si aplica — tu despacho. La verificación de cédula está en proceso; entretanto registramos tus datos.",
        },
        {
          titulo: "Usa el modo técnico",
          texto: "Chat directo sin entrevistas: consulta artículos, jurisprudencia, genera documentos. Todo con citas listas para copiar a tus escritos.",
        },
        {
          titulo: "Recibe expedientes compartidos",
          texto: "Los ciudadanos de tu especialidad te encuentran, comparten su dossier y tú decides si tomas el caso.",
        },
        {
          titulo: "Toma el caso y crece",
          texto: "Con un clic aceptas el expediente: la IA queda a tu disposición durante todo el litigio como asistente de investigación.",
        },
      ]}
      accesoTitulo="Cuenta profesional — gratis en beta"
      accesoItems={[
        "Acceso completo al modo técnico durante la beta",
        "Casos de tu especialidad sin costo de referimiento",
        "Tu frase de acceso privada — sin contraseñas que filtrar",
        "Cuando lancemos planes, los usuarios fundadores conservarán condiciones preferentes",
      ]}
      ctaTexto="Crear mi cuenta profesional"
      ctaHref="/onboarding/abogado"
      notaLegal="AI Justicia es una herramienta de apoyo a la práctica jurídica. La dirección de los asuntos y la responsabilidad profesional corresponden exclusivamente al abogado titular."
    />
  );
}
