"""Cliente de email via Resend."""
import logging
from ai_justicia.config import settings

logger = logging.getLogger(__name__)
API = "https://api.resend.com/emails"
FROM = "AI Justicia <no-reply@aijusticia.mx>"


def _enviar(to, subject, html):
    import requests
    key = settings.resend_api_key
    if not key:
        logger.info("EMAIL (sin key): %s %s", to, subject)
        return False
    try:
        r = requests.post(API, json={
            "from": FROM, "to": [to], "subject": subject, "html": html,
        }, headers={"Authorization": "Bearer " + key}, timeout=15)
        ok = r.status_code in (200, 201)
        logger.info("EMAIL %s %s: %s", to, subject, "OK" if ok else r.text[:200])
        return ok
    except Exception as e:
        logger.error("EMAIL %s FALLO: %s", to, str(e)[:200])
        return False


def _base(titulo, contenido, accion_url="", accion_texto=""):
    btn = ""
    if accion_url:
        btn = ('<div style="text-align:center;margin:28px 0;">'
               f'<a href="{accion_url}" style="background:#047857;color:#fff;'
               'text-decoration:none;padding:12px 32px;border-radius:10px;'
               f'font-weight:600;display:inline-block;font-size:15px;">{accion_texto}</a></div>')
    return f'''<!DOCTYPE html><html lang="es"><body style="margin:0;padding:0;background:#f8fafc;font-family:sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:32px 20px;">
<div style="background:#fff;border-radius:16px;padding:32px;border:1px solid #e2e8f0;">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:24px;">
<div style="width:36px;height:36px;background:#047857;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;color:#fff;">S</div>
<span style="font-size:15px;font-weight:700;color:#1e293b;">AI Justicia</span></div>
<h2 style="margin:0 0 16px;color:#0f172a;font-size:20px;">{titulo}</h2>
<div style="color:#475569;font-size:15px;line-height:1.6;">{contenido}</div>
{btn}
<hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0;">
<p style="color:#94a3b8;font-size:12px;margin:0;">AI Justicia - justicia precisa, verificable.<br>Correo automatico, no responder.</p>
</div></div></body></html>'''


def enviar_invitacion_caso(to, nombre, codigo, url):
    return _enviar(to, f"{nombre} compartio un caso contigo - AI Justicia",
        _base("Tienes un caso compartido",
            f"<p><strong>{nombre}</strong> te esta compartiendo un caso.</p>"
            f'<p>Codigo: <strong style="font-size:22px;letter-spacing:0.2em;">{codigo}</strong></p>'
            '<p style="color:#94a3b8;font-size:13px;">Vence en 72 horas.</p>', url, "Acceder"))


def enviar_invitacion_firma(to, nombre_firma, rol, codigo, url):
    return _enviar(to, f"Invitacion a {nombre_firma} - AI Justicia",
        _base(f"Unete a {nombre_firma}",
            f"<p>Te invitaron como <strong>{rol}</strong>.</p>"
            f'<p>Codigo: <strong style="font-size:22px;letter-spacing:0.2em;">{codigo}</strong></p>',
            url, "Unirme"))


def enviar_notificacion_caso(to, nombre_caso, evento):
    return _enviar(to, f"Actualizacion en '{nombre_caso}' - AI Justicia",
        _base("Actualizacion en tu caso",
            f"<p>Caso: <strong>{nombre_caso}</strong></p>"
            f'<p style="background:#f1f5f9;padding:12px;border-radius:8px;">{evento}</p>',
            "https://aijusticia.mx/casos", "Ver caso"))
