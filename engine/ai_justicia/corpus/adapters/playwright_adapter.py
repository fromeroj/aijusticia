"""Adapter Playwright para estados JS-rendered.

Algunos estados (Sonora, Sinaloa, Chiapas) cargan sus leyes via JavaScript
y no tienen enlaces directos a PDFs en el HTML estático. Este adapter usa
Playwright para renderizar la página y extraer los enlaces.

Estados que usan este adapter:
- San Luis Potosí (WAF Sucuri — Playwright pasa el challenge)
- Sonora (Astro SPA)
- Zacatecas (JS-rendered)
- Veracruz (javascript:PDF() calls)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from io import BytesIO
from typing import Iterator
from urllib.parse import urljoin, unquote

from ai_justicia.corpus.adapters.base import DocumentoMetadata
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.models import Fuente

logger = logging.getLogger(__name__)


class PlaywrightAdapter:
    """Adapter que usa Playwright para extraer leyes de sitios JS-rendered."""

    fuente = Fuente.GACETA_ESTATAL

    def __init__(self, entidad: str, portal_url: str | None = None):
        self.entidad = entidad
        # Leer URL de la DB si no se pasa explícitamente
        if not portal_url:
            portal_url = self._leer_url_db(entidad)
        self.portal_url = portal_url

    def _leer_url_db(self, entidad: str) -> str | None:
        import psycopg
        from ai_justicia.config import settings
        try:
            with psycopg.connect(settings.psycopg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT portal_url FROM source_health WHERE fuente = %s AND entidad = %s",
                        ("GacetaEstatal", entidad),
                    )
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception:
            return None

    def listar_desde(self, fecha_inicio: date | None = None, max_days: int = 1) -> Iterator[DocumentoMetadata]:
        """Lista leyes usando Playwright para renderizar JS."""
        if not self.portal_url:
            logger.warning("Playwright %s: sin URL configurada", self.entidad)
            return

        # Ejecutar el scrapeo async en un loop sincrónico
        links = asyncio.run(self._scrape_links())

        vistos = set()
        for href, text in links:
            if href in vistos:
                continue
            vistos.add(href)

            filename = unquote(href.split("/")[-1])
            nombre = re.sub(r"\.(pdf|doc|docx)$", "", filename, flags=re.IGNORECASE).strip()
            nombre = re.sub(r"[-_]\d{6,8}.*$", "", nombre).strip()
            if len(nombre) < 3:
                nombre = text[:80] if text else filename

            yield DocumentoMetadata(
                id_externo=f"{self.entidad[:3].lower()}_{hash(href) % 100000}",
                fuente=Fuente.GACETA_ESTATAL,
                titulo=nombre[:200],
                fecha_publicacion=date.today(),
                url_origen=href,
                entidad=self.entidad,
                tipo="ley",
                extra={"url": href, "filename": filename},
            )

    async def _scrape_links(self) -> list[tuple[str, str]]:
        """Scrapea enlaces a PDFs/DOCs con Playwright."""
        from playwright.async_api import async_playwright

        links: list[tuple[str, str]] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            try:
                await page.goto(self.portal_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                # Extraer enlaces <a> con PDF/DOC + onclick goToUrl (Chiapas pattern)
                raw_links = await page.evaluate("""
                    () => {
                        const r = [];
                        
                        // 1. Standard <a> links to PDFs
                        document.querySelectorAll('a').forEach(a => {
                            const href = a.href || '';
                            if (href.match(/\\.(pdf|doc|docx)/i)) {
                                r.push({ href, text: a.textContent.trim().substring(0, 80) });
                            }
                        });
                        
                        // 2. onclick="goToUrl('...')" pattern (Chiapas, others)
                        document.querySelectorAll('[onclick]').forEach(el => {
                            const onclick = el.getAttribute('onclick') || '';
                            const m = onclick.match(/goToUrl\\(['"]([^'"]+)['"]\\)/);
                            if (m) {
                                const name = el.textContent.trim().substring(0, 80) || el.querySelector('td')?.textContent?.trim()?.substring(0, 80) || 'Ley';
                                r.push({ href: m[1], text: name });
                            }
                        });
                        
                        // 3. javascript:PDF('...') pattern (Veracruz)
                        const html = document.documentElement.innerHTML;
                        const jsPdfMatches = [...html.matchAll(/PDF\\?['"]([^'"]+\\.pdf)['"]\)/gi)];
                        for (const m of jsPdfMatches) {
                            r.push({ href: m[1], text: 'PDF' });
                        }
                        
                        // 4. URLs de PDF/DOC en todo el HTML (tablas, etc.)
                        const allUrls = html.match(/[a-zA-Z0-9_\\-\\/\\.\\%]+\\.(?:pdf|doc|docx)/gi) || [];
                        const baseUrl = window.location.origin + window.location.pathname.substring(0, window.location.pathname.lastIndexOf('/'));
                        for (const u of allUrls) {
                            let fullUrl = u;
                            if (!fullUrl.startsWith('http')) {
                                fullUrl = u.startsWith('/') ? window.location.origin + u : baseUrl + '/' + u;
                            }
                            r.push({ href: fullUrl, text: '' });
                        }
                        
                        return r;
                    }
                """)

                base = self.portal_url
                for l in raw_links:
                    href = l["href"]

                    # Skip non-URL values
                    if not href or href == "#":
                        continue

                    # Resolver URLs relativas
                    if not href.startswith("http"):
                        href = urljoin(base, href)

                    # Filtrar archivos administrativos (avisos, convocatorias, banners)
                    if any(skip in href.lower() for skip in ["avisos/", "convocatoria", "banner", "protocolo", "transparencia/up"]):
                        continue

                    links.append((href, l["text"]))

            except Exception as e:
                logger.warning("Playwright %s: error: %s", self.entidad, e)
            finally:
                await browser.close()

        return links

    def obtener_texto(self, metadata: DocumentoMetadata) -> str:
        """Descarga el PDF/DOC y extrae texto."""
        import time
        import requests
        # Usar requests directo con follow_redirects (el EducationalHTTPClient a veces
        # no sigue redirects correctamente para PDFs con query params tipo ?v=XXX)
        try:
            time.sleep(0.5)  # delay educativo
            resp = requests.get(
                metadata.url_origen,
                verify=False,
                timeout=30,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            if resp.status_code != 200 or len(resp.content) < 1000:
                return ""
            content = resp.content
        except Exception as e:
            logger.warning("Playwright %s: error descargando %s: %s", self.entidad, metadata.id_externo, e)
            return ""

        url_lower = metadata.url_origen.lower()

        if url_lower.endswith(".pdf") or "pdf" in url_lower or content[:4] == b'%PDF':
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(content))
                textos = [page.extract_text() or "" for page in reader.pages]
                return limpiar_texto("\n\n".join(t for t in textos if t))
            except Exception as e:
                logger.warning("Playwright %s: error PDF: %s", self.entidad, e)
                return ""

        elif url_lower.endswith((".doc", ".docx")):
            import tempfile, subprocess, os
            ext = ".docx" if url_lower.endswith(".docx") else ".doc"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(content)
                tmp_path = f.name
            try:
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", tmp_path],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return limpiar_texto(result.stdout)
                return ""
            finally:
                os.unlink(tmp_path)

        return ""
