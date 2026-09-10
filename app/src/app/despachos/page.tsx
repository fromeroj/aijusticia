"use client";

import {
  Building2, Lock, Brain, Users, FolderOpen,
  TrendingUp, FileSearch, ShieldCheck,
} from "lucide-react";
import { PathLanding } from "@/components/marketing/PathLanding";

export default function Despachos() {
  return (
    <PathLanding
      color="bg-gray-900"
      colorHover="hover:bg-gray-800"
      colorSoft="bg-gray-900/10 text-gray-700"
      emoji="🏛️"
      publico="Para despachos y firmas"
      titular="Tlamatini: la IA que litiga como su despacho… porque la entrenó su despacho"
      promesa="Tlamatini —el modelo jurídico mexicano de AI Justicia— corre DENTRO de tu firma, y cada caso, contrato y demanda entrena tu adapter privado. La IA de TU despacho habla con vuestro estilo, cita vuestras estrategias — y ese conocimiento jamás sale de la firma."
      features={[
        {
          icon: <Brain className="h-5 w-5" />,
          titulo: "Tlamatini on-premise + adapter privado",
          texto: "El modelo jurídico mexicano desplegado en tu infraestructura, con un adapter exclusivo entrenado solo con los casos de tu firma: tus plantillas, tus estrategias, tu manera de redactar. La base es común; el know-how es tuyo.",
        },
        {
          icon: <Lock className="h-5 w-5" />,
          titulo: "Aislamiento garantizado por diseño",
          texto: "Los datos de tu despacho viven en datasets separados y entrenan solo tu adapter. Jamás alimentan el modelo general ni el de otras firmas — verificable técnica y contractualmente.",
        },
        {
          icon: <Users className="h-5 w-5" />,
          titulo: "Toda la firma, más rápida",
          texto: "Los asociados investigan en minutos lo que tomaba horas: jurisprudencia aplicable, precedentes del propio despacho, borradores de escritos con el estilo de la casa.",
        },
        {
          icon: <FolderOpen className="h-5 w-5" />,
          titulo: "Expedientes de ciudadanos listos",
          texto: "Recibe casos de tus materias con la entrevista hecha, hechos estructurados y documentos en la bóveda. Menos triaje, más litigio.",
        },
        {
          icon: <FileSearch className="h-5 w-5" />,
          titulo: "Memoria institucional",
          texto: "El despacho acumula conocimiento: cuando un asociado se va, el modelo se queda. Cada caso ganado hace a la firma entera más fuerte.",
        },
        {
          icon: <TrendingUp className="h-5 w-5" />,
          titulo: "Sin crecer nómina",
          texto: "Capacidad de investigación adicional sin contratar. El modelo privado trabaja 24/7 con el estándar de tu firma.",
        },
      ]}
      proceso={[
        {
          titulo: "Registra tu despacho",
          texto: "Nombre de la firma y datos del socio responsable. Creamos tu espacio aislado y generamos las claves de tu modelo privado.",
        },
        {
          titulo: "Tu equipo entra",
          texto: "Cada abogado de la firma se registra con su cédula y se asocia al despacho. Todos comparten el adapter privado, nadie ve otros bufetes.",
        },
        {
          titulo: "La IA aprende de vuestros casos",
          texto: "Con cada expediente trabajado — consultas, documentos generados, correcciones — el modelo privado se afina al estilo y doctrina de la firma.",
        },
        {
          titulo: "Litigien con ventaja",
          texto: "Investigación al instante, borradores con fundamento, precedentes propios a un clic. Y si un ciudadano comparte un caso con ustedes, llega listo para trabajar.",
        },
      ]}
      accesoTitulo="Plan despacho — a medida"
      accesoItems={[
        "Modelo privado aislado de tu firma (adapter exclusivo)",
        "Usuarios ilimitados de tu despacho",
        "Aislamiento de datos contractual y técnicamente garantizado",
        "Onboarding y migración de precedentes asistida",
        "Beta fundadora: condiciones preferentes de por vida",
      ]}
      ctaTexto="Entrar a la app de trabajo"
      ctaHref="/app"
      notaLegal="AI Justicia procesa los datos del despacho como encargado; el responsable del tratamiento es la firma. El modelo privado es propiedad conjunta: la base de AI Justicia y el know-how del despacho permanecen separados."
    />
  );
}
