import { redirect } from "next/navigation";

/** El panel vive ahora en /app (abogados + despachos). Redirect permanente. */
export default function PanelRedirect() {
  redirect("/app");
}
