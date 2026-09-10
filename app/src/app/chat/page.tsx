"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/lib/store";

function ChatRedirect({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const sesion = useChatStore((s) => s.sesion);
  useEffect(() => {
    if (sesion?.tipo === "abogado") router.replace("/studio");
  }, [sesion, router]);
  if (sesion?.tipo === "abogado") return null;
  return <>{children}</>;
}

import { ChatWindow } from "@/components/chat/ChatWindow";

export default function ChatPageWrapper() {
  return (
    <ChatRedirect>
      <ChatPage />
    </ChatRedirect>
  );
}

function ChatPage() {
  // Modo abierto: no se requiere sesión para conversar.
  // El store hidrata localStorage automáticamente al montar en cliente.
  return <ChatWindow />;
}
