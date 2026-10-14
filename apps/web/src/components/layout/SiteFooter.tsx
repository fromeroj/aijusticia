import Link from "next/link";

/** Footer legal compartido para páginas autenticadas (no marketing). */
export function SiteFooter() {
  return (
    <footer className="border-t border-gray-100 bg-white px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-3 text-center">
        <p className="text-xs text-gray-500">
          AI Justicia e Izel ofrecen información jurídica general verificada contra fuentes
          oficiales. <strong>No son abogados ni sustituyen asesoría legal profesional.</strong>
        </p>
        <nav className="flex flex-wrap items-center justify-center gap-4 text-[11px] text-gray-400">
          <Link href="/" className="hover:text-gray-600">Inicio</Link>
          <Link href="/para-ti" className="hover:text-gray-600">Para ti</Link>
          <Link href="/abogados" className="hover:text-gray-600">Abogados</Link>
          <Link href="/despachos" className="hover:text-gray-600">Despachos</Link>
          <span>🇲🇽 Hecho en México · datos soberanos</span>
        </nav>
      </div>
    </footer>
  );
}
