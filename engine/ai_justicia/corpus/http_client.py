"""Cliente HTTP educativo para scraping de fuentes oficiales.

Características:
- User-Agent de navegador real (algunos sitios dan 403 a curl/requests default).
- Rate limit configurable (default 1 req/s) por cortesía a servidores gubernamentales.
- Retry con backoff exponencial en 403/429/5xx.
- Cookie jar persistente (DOF lo requiere).
- Soporte gzip (los servidores lo ofrecen).
- decode() inteligente: detecta charset del Content-Type o del contenido.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# User-Agent de navegador real (LeyesBiblio da 403 a "python-requests/X")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class EducationalHTTPClient:
    """Cliente HTTP con rate-limiting, retry y cookie jar para scraping educativo.

    Uso típico:
        client = EducationalHTTPClient(referer="https://sjf2.scjn.gob.mx/")
        html = client.get_text("https://www.dof.gob.mx/index_111.php?...")
    """

    def __init__(
        self,
        referer: str | None = None,
        min_interval: float = 0.75,  # ~1.3 req/s máximo
        max_retries: int = 3,
        verify_tls: bool = True,
        timeout: float = 30.0,
    ):
        self.min_interval = min_interval
        self.verify_tls = verify_tls
        self.timeout = timeout
        self._last_request_time: float = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        })
        if referer:
            self.session.headers["Referer"] = referer

        # Configurar retry a nivel de transporte para errores de red
        retry = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Suprimir warning de TLS si verify=False (CDMX tiene cert inválido)
        if not verify_tls:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _throttle(self) -> None:
        """Espera si la última petición fue demasiado reciente."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.time()

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        """GET con throttle y retry de aplicación para 403 (WAF)."""
        self._throttle()
        resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout, verify=self.verify_tls)
        # Algunos WAF (Imperva SJF) dan 403 esporádicos; reintentar una vez con delay
        if resp.status_code == 403:
            logger.warning("403 en %s — reintentando tras 2s", url[:80])
            time.sleep(2.0)
            self._throttle()
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout, verify=self.verify_tls)
        return resp

    def post(self, url: str, *, json_body: dict | None = None, headers: dict | None = None) -> requests.Response:
        """POST con throttle."""
        self._throttle()
        h = {"Content-Type": "application/json", **(headers or {})}
        return self.session.post(url, json=json_body, headers=h, timeout=self.timeout, verify=self.verify_tls)

    def get_text(
        self,
        url: str,
        *,
        params: dict | None = None,
        fallback_encoding: str | None = None,
        referer: str | None = None,
    ) -> str:
        """GET que devuelve texto decodificado correctamente.

        Detecta charset del Content-Type; si no está, prueba UTF-8 y fallback.
        fallback_encoding se usa si el servidor no declara charset (ej. DOF usa ISO-8859-1).
        referer permite override por-request (el DOF lo exige en nota_detalle).
        """
        headers = {"Referer": referer} if referer else None
        resp = self.get(url, params=params, headers=headers)
        resp.raise_for_status()

        # requests usa apparent_encoding si r.encoding es None, pero podemos forzar
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            # Solo confiar en apparent si el contenido parece tener caracteres no-ASCII
            if fallback_encoding:
                resp.encoding = fallback_encoding
            else:
                resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        """GET que devuelve JSON parseado."""
        resp = self.get(url, params=params, headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()

    def post_json(self, url: str, *, json_body: dict | None = None) -> dict:
        """POST que devuelve JSON parseado."""
        resp = self.post(url, json_body=json_body, headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()
