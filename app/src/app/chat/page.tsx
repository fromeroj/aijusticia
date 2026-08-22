"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { useChatStore } from "@/lib/store";

export default function ChatPage() {
  const router = useRouter();
  const sesion = useChatStore((s) => s.sesion);

  // Guard: sin sesión (recién llegada directa a /chat), mandar a la landing
  useEffect(() => {
    // pequeño delay para dejar hidratar localStorage en SSR-safe
    const t = setTimeout(() => {
      if (!useChatStore.getState().sesion) {
        router.replace("/");
      }
    }, 100);
    return () => clearTimeout(t);
  }, [router]);

  // Mientras valida la sesión no pintamos el chat (evita flash en modo incorrecto)
  if (typeof window !== "undefined" && !sesion) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white text-sm text-gray-400">
        Redirigiendo…
      </div>
    );
  }

  return <ChatWindow />;
}
