"use client";

import { ChatWindow } from "@/components/chat/ChatWindow";

export default function ChatPage() {
  // Modo abierto: no se requiere sesión para conversar.
  // Los abogados entran por /studio; el chat es para ciudadanos.
  return <ChatWindow />;
}
