# Autenticación Progresiva — Diseño

## Principio

El usuario nunca ve una decisión de autenticación hasta que la necesita.
Empieza anónimo, conversa con Izel, y cuando quiere guardar su caso elige
entre dos caminos — ninguno es la "frase de 12 palabras".

## Los tres niveles

| Nivel | Qué pide | Qué obtiene | Cuándo aparece |
|---|---|---|---|
| **0 — Anónimo** | Nada | Chat ilimitado con Izel, citas verificadas | Siempre (default) |
| **1 — Correo** | Email + contraseña | Expediente persistente, bóveda, acceso desde cualquier dispositivo | Cuando guarda su caso |
| **2 — Frase** | 12 palabras | Identidad sin datos personales, bóveda cifrada | Opción avanzada |

## Por qué progresivo

- **Sin fricción inicial**: el ciudadano conversa sin dar nada — el gancho de adquisición.
- **Familiar**: el nivel 1 es email + contraseña como cualquier servicio web.
- **Gradual**: solo pide datos cuando el usuario ya vio el valor (su respuesta con citas verificadas).
- **Dual**: ambos caminos producen el mismo JWT y el mismo expediente.

## Arquitectura

```
Ciudadano conversa → [anónimo, sin JWT]
       │
       └── "Guardar caso" →
              ├── Correo + contraseña → Nextcloud OCS user → JWT
              └── Frase de 12 palabras → hash → JWT
```

Ambos caminos producen el mismo JWT:
```json
{
  "sub": "<actor_id>",
  "tier": "ciudadano",
  "auth": "email" | "frase",
  "exp": "..."
}
```

El engine no distingue: mismo expediente, misma bóveda, mismos derechos.

## Nextcloud como proveedor de identidad

El tier despacho ya usa Nextcloud para bóveda y Collabora. Extenderlo a
ciudadanos significa:

- **Un solo sistema de usuarios**: Nextcloud gestiona ciudadanos y despachos.
- **Bóveda automática**: cada usuario Nextcloud tiene su carpeta de documentos.
- **Recuperación por correo**: Nextcloud maneja el "olvidé mi contraseña".
- **Contraseñas hasheadas** por Nextcloud (bcrypt/argon2), no en nuestra DB.

## Qué se elimina

- La frase de 12 palabras **deja de ser la única opción** para guardar un caso.
- El usuario que prefiera anonimato total sigue teniendo la frase.
- El nivel 1 (correo) es el default para usuarios nuevos que quieren persistencia.

## Migración

- Usuarios existentes con frase: siguen funcionando. Pueden agregar correo
  después desde su cuenta (vinculación progresiva).
- Usuarios nuevos: eligen correo o frase en el "guardar caso".
- La frase nunca desaparece — es una opción más, no un requisito.
