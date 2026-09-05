# El Harness de Agente — Diseño y decisión
## AI Justicia como entorno operativo para Tlamatini

*Septiembre 2026*

---

## 1. La observación correcta

Todo lo que hemos construido — pipeline de 7 etapas, RAG con verificación, expedientes,
Nextcloud con WebDAV/workflows, PII-gate, router de modelos — **es un harness**: el entorno
que el agente percibe y sobre el que actúa. Hoy ese entorno se recorre por una tubería fija
(el pipeline). El spec de bufetes exige recorrerlo **agentivamente**: "genera el acta, compárala
con nuestra plantilla, extrae las cláusulas nuevas, promuévelas a biblioteca" es un plan
multi-paso con herramientas, no un query.

**Decisión**: formalizar el harness como runtime de agente con herramientas + ciclo + verificador
— sin framework pesado, evolucionando el pipeline existente.

---

## 2. Arquitectura del harness

```
┌──────────────────────────────────────────────────────┐
│                    AGENTE (Tlamatini)                 │
│   plan → tool_call → observar → ajustar → entregar    │
└──────────────┬───────────────────────────────────────┘
               │ tools (esquema function-calling)
┌──────────────▼───────────────────────────────────────┐
│                  HARNESS (nuestro engine)             │
│                                                      │
│  Percepción              Acción                      │
│  ├── leer_archivo        ├── escribir_archivo (WebDAV)│
│  ├── listar_caso         ├── generar_doc (docxtpl)    │
│  ├── buscar_ley (RAG)    ├── pii_scan                 │
│  ├── buscar_clausula     ├── insertar_clausula        │
│  ├── historial_caso      ├── notificar (OCS)          │
│  └── estado_monitor      └── crear_tarea              │
│                                                      │
│  GATES (siempre, no negociables)                     │
│  ├── Verificador de citas (afirmaciones legales)      │
│  ├── PII-gate (flujos de datos)                      │
│  └── Permisos (RLS + rol socio/asociado/pasante)     │
└──────────────────────────────────────────────────────┘
```

**Principio rector — "el agente propone, el harness dispone"**: el modelo decide qué
herramienta llamar; el harness valida SIEMPRE el efecto (una afirmación legal sin ancla se
bloquea igual que un write_archivo que cruce el perímetro PII). Es la misma lógica del router
de modelos, extendida a acciones.

---

## 3. Las tres capas del diseño

### 3.1 Tool schema (el contrato agente↔harness)

~12 herramientas en formato function-calling estándar. Las etapas del pipeline actual
SE CONVIERTEN en herramientas (`buscar_ley` = retrieve; `pii_scan` ya existe como gate) —
migración natural, no reescritura.

### 3.2 El ciclo del agente (executor en nuestro engine)

Loop acotado: `plan (max 8 pasos) → tool → observación → ... → entrega`. Presupuesto de
pasos y tokens por tarea. En modo ciudadano el ciclo se degrada al pipeline actual (1
"paso" compuesto — compatible hacia atrás); en modo despacho corre el ciclo completo.

### 3.3 MCP como capa de interoperabilidad

El mismo conjunto de herramientas se expone como **servidor MCP** (Model Context Protocol).
Consecuencias:
- Tlamatini actúa como cliente MCP de su propio harness — un solo contrato
- El ecosistema se abre: cualquier cliente MCP puede consumir NUESTRAS herramientas
  (buscar_ley sobre el corpus mexicano es un MCP server que nadie más tiene)
- **Soberanía gobernada**: si un despacho permite apuntar Claude/Cursor a sus archivos
  NC vía NUESTRO MCP, es una decisión de gobernanza del bufete con el PII-gate
  interceptando igual — el control queda en el harness, no en el modelo

### 3.4 Por qué NO framework (LangGraph & co.)

Nuestro pipeline YA es el esqueleto del executor; el verificador YA es el reward-signal.
Añadir un framework intermedio compra velocidad inicial y cuesta dependencia + opacidad en
el bucle de entrenamiento (ver §4). El patrón DeepSeek que citamos — planner mínimo +
executor + verificador, cero bloat — es exactamente la línea.

---

## 4. El cierre del círculo: harness → entrenamiento → agente

Esta decisión conecta con el harness training del whitepaper (§5.2):

1. **Hoy**: las trayectorias del pipeline (query → pasajes → respuesta verificada) son
   pares de entrenamiento simples
2. **Con el runtime agente**: cada tarea del despacho genera una TRAYECTORIA completa
   (plan → llamadas → observaciones → entregable verificado) — el formato exacto de datos
   que entrena agentes
3. **Tlamatini v2** se entrena con esas trayectorias (con consentimiento del bufete):
   el harness operacional se convierte en el generador del corpus de entrenamiento del
   agente que lo operará

**El verifier es el reward**: una trayectoria donde toda afirmación pasó el anclaje y toda
acción pasó los gates = trayectoria positiva. El abstenerse honesto = señal negativa limpia.
Esto es RL-asistido-por-reglas sin construir un entorno de RL completo.

---

## 5. Fases

| Fase | Alcance | Cuándo |
|---|---|---|
| H1 | Tool schema + executor de ciclo (degradación compatible a pipeline) — el pipeline actual corre como caso especial | F1 bufetes |
| H2 | MCP server con las mismas tools; Tlamatini cliente MCP; integración NC completa (WebDAV/OCS como tools) | F2 |
| H3 | Logging de trayectorias → dataset de entrenamiento agéntico; fine-tune de tool-calling sobre Tlamatini | post-CPT |

---

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Agente alucina tool calls (args inválidos) | Validación estricta de esquema en el harness + retry una vez + degradación a pipeline |
| Bucle infinito / costo | Presupuesto duro de pasos y tokens por tarea |
| Acción destructiva errónea | Toda acción de escritura pasa gates + confirmación humana según umbral configurable del bufete |
| Exfiltración por tool-chaining creativo | El PII-gate intercepta SALIDAS de tools también, no solo entradas del usuario |

---

## Referencia: Mercor/SkyRL — guía RL para agentes de trabajo del conocimiento

*Fuente: [Training Frontier Knowledge-Work Agents: A 397B RL Training Guide with SkyRL](https://www.mercor.com/blog/training-frontier-knowledge-work-agents-a-397b-rl-training-guide-with-skyrl/) — receta open-source (scripts, pesos, trazas de eval en GitHub: ApexAgents-SkyRL-Recipe)*

### Por qué nos importa

1. **Validan nuestra base (de nuevo)**: sus ablations corrieron sobre **Qwen3.6-35B-A3B** — la misma
   familia que elegimos para Tlamatini — y con solo post-training **superó a Opus 4.5** en APEX-Agents.
2. **"Los fixes del harness solos valieron una época de entrenamiento"**: arreglar el entorno
   (paquetes faltantes, PDFs ilegibles, truncamiento) subió su 35B de 22.74% → 28.69% —
   **+6 puntos SIN tocar el modelo**. Es la validación más fuerte hasta fecha de nuestra filosofía
   harness-primero (todo lo que invertimos en el harness de RAG/verificación/PII-gate es
   entrenamiento gratis).
3. **"Los datos dominaron a los algoritmos"**: su mejor perilla algorítmica dio +3.9 pts; el
   post-training completo dio +10-12. Nuestra apuesta por el corpus (14B tokens mexicanos)
   sobre la optimización fina de hiperparámetros es la asignación correcta de esfuerzo.

### Qué tomar de su metodología RL (para la fase H3/agentic de Tlamatini)

| Técnica | Resultado | Aplicación nuestra |
|---|---|---|
| **Overfit-run de 32 tareas ANTES del run completo** | expuso grading roto sin gastar compute | Nuestro smoke test de 100M tokens ($3) antes del forge — mismo principio, formalizarlo como gate |
| **DPPO (máscara de tokens divergentes)** | empata en score, pero mÃ¡s turnos cortos (mejor conducta agentic) | Candidato para el trainer de la fase agentic |
| **prompt_mean (agregación DAPO)** | +3.9 pts vs token_mean | Las trayectorias de despacho (2k-128k tokens) sesgan igual — usar prompt_mean |
| **Context nudge al 80% del contexto** | +3.0 pts gratis | Aplicable al ciclo del agente: prompt de cierre cuando el contexto se agota |
| **TITO (token-in-token-out)** | mantiene on-policy sin re-tokenizar | Reescribir el harness alrededor de /completions — para cuando midamos logprobs |
| **Métricas conductuales > reward** | turnos/tool-call-success predicen mejor | Loguear métricas de conducta en las trayectorias del harness (pasos, tools, tasa de anclaje) |
| Transfer a harness held-out | el 35B transfirió MEJOR (aprendió a preferir código sobre MCP) | Nuestro harness training debe incluir trayectorias con herramientas sustitutas |

### Números de referencia

- Hero run: Qwen3.5-397B-A17B, RL puro (sin SFT warmup), 1,928 tareas expertas
- Pass@1: 16.11% → 27.29% (+70% relativo) en APEX-Agents (480 held-out)
- Terminal-Bench 2.1: 44.6% (35B) / 50.6% (397B) baselines, con transferencia
- Ratio inferencia:entrenamiento: 12:4 (35B) / 12:8 (397B); concurrencia limitada por KV-cache
- Sin SFT warmup: el RL directo desde el base funcionó — relevante si Tlamatini post-CPT va directo a RL de trayectorias
