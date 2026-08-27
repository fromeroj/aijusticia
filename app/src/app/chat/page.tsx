"use client";

import { ChatWindow } from "@/components/chat/ChatWindow";

export default function ChatPage() {
  // Modo abierto: no se requiere sesión para conversar.
  // El store hidrata localStorage automáticamente al montar en cliente.
  return <ChatWindow />;
}
