# AI Justicia: Building a Sovereign Legal Language Model for Mexico

**From 430M to 10B tokens of primary legal sources — a full-stack approach to Mexican legal AI**

*Working draft for publication · August 2026*

---

## Abstract (draft)

Legal AI in Spanish — and specifically Mexican law — is structurally underserved. The dominant legal LLMs are trained on Anglo-American corpora, cite hallucinated articles when asked about Mexican law, and cannot be deployed on-premise for law firms bound by professional secrecy. We present AI Justicia, an end-to-end effort to build a Mexican legal AI system: (1) the construction of a **10B-token corpus of exclusively Mexican primary legal sources** — laws, official gazettes, case law from state judiciary APIs, and doctrinal works harvested at scale from public government portals; (2) a **retrieval-anchored generation harness** where every legal claim must be verified against retrieved passages, with honest abstention when evidence is insufficient; and (3) **Tlamatini**, a sovereign base model for Mexican law (from the Nahuatl *tlamatini*, "one who knows" — the sage-counselors of pre-Hispanic central Mexico), whose training strategy combines the lessons of SaulLM-7B (domain CPT with replay) and Thomson-1.0 (strong CPT + linear merging), extended with **harness training** — teaching the model the citation-anchored response format during pretraining itself. We also document the data-engineering reality of the project: most Mexican legal data sits behind recaptcha gates, JWT chains, geo-blocks, and legacy ASP.NET portals, and we describe reproducible techniques for each.

---

## 1. The Problem

Three failures define the current state of legal AI for Mexico:

**1.1 Hallucinated law.** We evaluated Thomson-1.0-Small (a strong English legal foundation model) on 30 canonical Mexican citizen legal questions — labor, family, consumer, housing. It answered 30/30 fluently and 93% cited statutes. But inspection revealed systematic citation errors: it cited "Art. 139 LFT" for pregnancy-related dismissal protection (the correct article is 164), and attributed the "3 months + 20 days/year" indemnification formula to Art. 48 (it is Art. 50). A fluent, confident, wrong citation is the worst failure mode for a citizen who cannot verify it.

An honest note: while drafting this very paper, one author cited "Art. 225 CPF" as the basis of professional secrecy. It is Arts. 210–211 — the reviewer caught it, and the correction was verified by querying this project's own corpus (the ingested Código Penal Federal returns the exact text: Art. 211 punishes revelation of secrets "por persona que presta servicios profesionales o técnicos" with 1–5 years and suspension of the profession). Citation drift is not a weakness of weak models; it is the default failure mode of *any* memory-based legal reasoning, human or machine. This is the core argument for retrieval-anchored generation.

**1.2 Cloud dependency vs. professional secrecy.** Mexican law firms operate under professional secrecy obligations (Arts. 210–211 CPF) and LFPDPPP rules on sensitive personal data. Uploading privileged client documents to a foreign cloud LLM API — which may retain and train on inputs — is legally unacceptable for despachos. A sovereign, locally-deployable model is not a nice-to-have; it is a compliance requirement.

**1.3 No Mexican corpus exists.** SaulLM trained on 30B tokens of English law. Thomson trained on proprietary Anglo-American corpora. For Mexico, no equivalent existed — not because the data doesn't exist, but because it is scattered across 33+ judicial portals, 32 state gazette systems, a 107-year-old federal gazette, and university repositories, most behind anti-bot protections.

## 2. Prior Art

### 2.1 SaulLM-7B: the open blueprint

SaulLM-7B (Argouarc'h et al., equall.ai, 2024) was the first LLM explicitly designed for the legal domain. Built on Mistral-7B, its recipe remains the reference for domain CPT:

- **30B tokens** of English legal text, distilled from **94B raw tokens** through aggressive cleaning and deduplication — they threw away 68% of collected data (PDF artifacts, duplicated cross-source documents, broken unicode). The lesson: corpus quality engineering dominates volume.
- Sources: MultiLegal Pile (English commercial subset, 50B), FreeLaw (15B), GovInfo statutes/opinions (11B), EuroParl (6B), EDGAR (5B), USPTO (4.7B), plus Australian, EU, and UK legislation.
- **2% general replay** (Wikipedia, StackExchange, GitHub from SlimPajama) to mitigate catastrophic forgetting — since Mistral's original training data is undisclosed.
- **Instruction data during CPT** (FLAN, Super-NaturalInstructions), inspired by "accidental task data" findings in machine translation. Conversational examples are not deferred to SFT; they enter the pretraining mix.
- Released under MIT license.

### 2.2 Thomson-1.0: the industrial validation

Thomson-1.0-Small (technical report, 2025) is a 35B-class MoE model built on the same base family we use (Qwen3.6-35B-A3B). Its key published findings:

- **Strong CPT + linear model merging** as the anti-forgetting mechanism (rather than replay alone).
- Multi-stage curriculum over proprietary legal corpora of tens of billions of tokens.
- License: PolyForm Strict — non-commercial, reference-only. We cannot use the model itself, but its *architecture decisions* are reproducible: it validated that a strong-CPT-plus-merge recipe on this exact base family produces a usable legal model — our local development machine already runs this architecture at 4-bit quantization.

Two domestic efforts define the current Mexican landscape. **lex-mx** (ingteranalvarez) maintains all 317 federal statutes as clean Markdown, auto-updated daily via GitHub Actions with git history doubling as a per-law reform changelog — an elegant differential-harvest pattern we adopt and integrate as a source. **LEX-MX** (eider404) is a RAG API over Mexican law built on closed OpenAI models (gpt-4.1-nano/mini) with ChromaDB — no training, no corpus contribution, and cloud dependency that is precisely the compliance gap for professional use. Neither trains a model; the sovereign-model space remains open.

Our empirical evaluation confirmed both models' lessons and one caveat: domain-trained models produce *lawyer-shaped* answers by default (correct format, correct institution referrals) but still hallucinate jurisdiction-specific article numbers. Domain CPT teaches the *shape* of legal reasoning; it does not guarantee factual grounding in a specific legal system. That is the RAG harness's job.

## 3. AI Justicia: System Overview

AI Justicia is a production system (aijusticia.mx) with three service tiers: **citizen** (free, anonymous, conversational), **lawyer** (professional mode, technical register, document generation), and **firm/despacho** (on-premise sovereign model with private adapters).

The production pipeline is a **two-agent conversation**:

1. **Izel** — an empathic conversational assistant (streaming, voice in/out) that interviews the citizen in plain language, builds a structured case file (expediente), and answers with concrete procedure. First tokens in ~2 seconds.
2. **The Bibliotecario (librarian subagent)** — runs *in parallel* with Izel: identifies the applicable statute from the conversation, searches *inside* that statute with phrase-aware full-text ranking, and returns the exact articles while Izel is still answering.
3. **Verified citations** — every legal claim carries an inline `[n]` citation backed by the official fragment; a references card (law, article number, fragment) is attached to each answer, expandable and exportable.

A public transparency dashboard (aijusticia.mx/estado) reports the live state of every source — documents, coverage window, last ingestion, and a traffic-light computed against each source's expected cadence.

### 3.1 The abstention lesson

An instructive failure: our first full evaluation showed 93% abstention — the system refused nearly everything. Root cause was not the model but *how we called it*: MiniMax-M3 is a reasoning model that burns 5–8K tokens on internal thinking before answering; our stage budgets (128–256 tokens for normalization/relevance filtering) truncated mid-think, yielding empty outputs → colloquial queries reached FTS → irrelevant passages → abstention. After fixing budgets (10K minimum) and adding a self-corrective second generation pass for weak citation formats, response rate went from **2/30 to 18/30** with no loss in citation integrity. Lesson: for reasoning models, prompt engineering includes *token budget engineering*.

## 4. The Corpus: 10B Tokens of Mexican Law

### 4.1 Composition

| Source family | Contents | Approx. tokens |
|---|---|---|
| **Semanario Judicial de la Federación** | 150,187 tesis (jurisprudencia + aisladas), 1900–2026, differential harvest past an Imperva WAF | ~22M |
| **DOF (federal gazette)** | 1999–2026, per-note full text, daily differential | ~300M+ |
| **Federal statutes & regulations** | LeyesBiblio corpus + reglamentos/manuales + lex-mx (317 statutes, daily-synced Markdown) | ~50M |
| **State legislation (32 states)** | **24,076 consolidated codes/laws/reglamentos via Orden Jurídico Nacional** — every state covered | ~85M |
| **Gaceta CDMX** | Complete 2014–2026 archive (via Wayback CDX) | 143M |
| **State case law — CDMX (SIVEPJ)** | 42,947 sentences, full universe ingested | ~52M |
| **State case law — Baja California** | 147K-record public API; 2,849 ingested in first pass, harvest ongoing | ~250M |
| **State case law — Edomex** | 178,439-sentence manifest enumerated via judiciary Elasticsearch API; extraction in progress | ~3–4B |
| **State case law — Jalisco** | 84,731-sentence universe enumerated via reCAPTCHA-gated API; PDFs via CDP-driven S3 pre-signed URLs | ~2–3B |
| **State case law — Querétaro, NL, +** | JWT chains, ASP.NET harvesting | ~1–2B |
| **Doctrina: BJV (IIJ-UNAM)** | 5,680 complete books via OAI-PMH | ~1B |
| **Theses: Repositorio UNAM** | 43,423 theses (~40% with full PDF) | ~2–3B |
| **English instructive data (SFT only)** | 269K reasoning examples — NLI, LSAT logic, case briefs; **no foreign statutes** | SFT mix |

Current status: **421,119 documents · 10.7M chunks · ~3.3B tokens ingested and queryable** (434M prompt-token calibrations against the live RAG); all 32 states already represented through the Orden Jurídico ingestion; remainder in active harvest; total discovered and accessible universe exceeds 12B tokens. A public dashboard (aijusticia.mx/estado) reports every source's count, coverage window, and freshness against its expected cadence.

### 4.2 Data engineering: the reproducible part nobody publishes

Every source required bespoke reverse-engineering. We document the techniques because they are the real bottleneck for legal AI in most countries:

- **OAI-PMH where available** (UNAM IIJ): the clean path — resumption tokens, datestamp-based incremental re-harvest.
- **Open Elasticsearch APIs** (Edomex judiciary): 10K-per-slice limit requires sub-slicing by quarter; PDFs served from a separate predictable file host.
- **reCAPTCHA-gated APIs** (Jalisco STJ): the `_vt` session cookie is IP-bound and quota-limited; we sustain harvest by driving a real browser via CDP, renewing the cookie through full page reloads (which re-execute grecaptcha with acceptable score), and fetching the listing through curl with the extracted cookie while PDFs come from S3 pre-signed URLs that require no session at all.
- **JWT-chained portals** (Querétaro): list endpoint returns structured keys → per-document token endpoint (60s TTL) → PDF endpoint. Pure HTTP, no browser.
- **Geo-blocked portals** (CDX Consejería Jurídica, Veracruz SEGOB): harvest from a Mexican-IP machine; ship JSONL to the data server.
- **Wayback CDX as legal-archive rescue**: the CDMX gazette's own search is an unautomatable ZK Java app; the complete PDF archive exists in the Wayback Machine index and is fully enumerable.
- **Scanned doctrine → OCR**: Apple Vision OCR (es-ES, ~0.7s/page) recovered 445 SCJN cuadernillos and full doctrinal books that had zero embedded text.
- **TLS-fingerprint impersonation past Imperva** (SCJN Semanario): the Semanario's API sits behind an Imperva WAF that silently drops any client whose TLS handshake is not a real browser — curl with a browser User-Agent, cloudscraper, and rotating residential proxies all fail. A Chrome-fingerprint HTTP client (curl_cffi, `impersonate="chrome"`) passes without executing the challenge. The 403 handshake cost us seven weeks of harvest before diagnosis.
- **API contract archaeology from obfuscated SPA bundles** (same SCJN portal): the thesis-detail endpoint changed contract silently — it now requires `isSemanal` and `hostName` query parameters, discoverable only by extracting the route from the webpack chunk that implements the public search UI. When a listing returns empty, the harvest died, not the data.
- **reCAPTCHA v3 score gating** (Jalisco STJ): every API call requires a fresh v3 token (`X-Recaptcha-Token`, action `visitor_verify`) generated in-page; the backend scores the *browser reputation*, so automated Chromium fails while the engineer's daily-profile Chrome passes. Production harvest runs through CDP against a real Chrome profile (or a Chrome extension generating tokens in-page), and presigned S3 URLs carry the files.
- **ASP.NET WebForms postbacks** (Nuevo León): search state lives in `__VIEWSTATE`; the harvest replays viewstate + button event per page.
- **JHipster API-key gating** (Chihuahua PJECZ): the v3 API authenticates with an obfuscated `X-Api-Key` extracted from the SPA's config bundle; routes discoverable from the frontend's own service files.
- **Public transparency as part of the harvest**: every source's count, coverage window, and freshness-vs-cadence traffic light is published live (aijusticia.mx/estado) — a corpus of Mexican law is not a dataset; it is a **living system of record**, and the system of record is public.
- **Everything differential**: each harvester's script, watermark state, and incremental strategy lives in a versioned registry — laws change, gazettes publish daily, courts upload constantly.

## 5. Training Strategy: Tlamatini

*Codename: Tlamatini — Nahuatl for "one who knows things"; the sage who counsels and, crucially, admits what they do not know. Training infrastructure: Tohil (the forge).*

### 5.1 The recipe

Synthesizing SaulLM, Thomson, and our evaluation findings:

1. **Base**: same family as Thomson-1.0-Small (Qwen3.6-35B-A3B) — architecture choice validated by Thomson's result.
2. **Stage 1 — Full-parameter CPT** on the Mexican corpus (~10B tokens):
   - **~80% Mexican primary law** in its natural mix: statutes, gazettes, case law, doctrine. Following SaulLM: aggressive dedup, no artificial upweighting of statutes over case law.
   - **~15% harness-formatted examples** (see 5.2).
   - **~2–5% general replay** (Spanish Wikipedia, code, general instruct) — SaulLM's anti-forgetting dose.
   - Full-parameter (not LoRA-CPT): our earlier LoRA-CPT attempt at high LR diverged (val loss 1.24→10.69); Thomson's result and cost analysis (4×H200, ~$70, ~6h on Vast.ai) favor full CPT.
   - **Linear merge with base** post-CPT — Thomson's anti-forgetting mechanism.
3. **Stage 2 — SFT** on: interview-driven dialogue, citation-anchored answers, abstention calibration; plus the 269K English instructive reasoning examples (contract NLI, LSAT-style logic, case briefs — reasoning patterns, zero foreign statutes).
4. **Stage 3 — Domain adapters per firm (despachos)**: private LoRA adapters trained exclusively on that firm's consented documents, served by merging at runtime. **The dual-adapter invariant**: firm data never enters the general adapter; the general adapter never sees privileged documents. This is the architectural expression of Arts. 210–211 CPF and LFPDPPP.

### 5.2 Harness training: teaching the harness into the weights

Our production system is a harness: retrieve passages → inject as context → demand citation-anchored answers. All our abstention failures were harness failures (format dropped, thinking budget exhausted). The natural extension (independently proposed as "harness training," e.g. Ornith): **train the harness behavior into the model itself** by including millions of examples in the exact inference format during CPT:

```
<retrieved passage(s)> + <citizen question> → <answer with [n] anchors per claim>
```

Three sources of harness pairs, all already in hand:
- **Case law itself**: judicial considerandos are naturally assertion-plus-article — mining (considerando → cited article) pairs from the 200K+ sentences yields anchored-format data for free.
- **Production traces**: with LFPDPPP-compliant citizen consent (the product collects opt-in explicitly, revocably), our verified query→passages→answer logs are gold data of the *real* harness distribution.
- **Synthetic distillation**: passage → generate citizen question + anchored answer, at corpus scale.

This is our central claim: for jurisdiction-specific legal AI, **harness-in-the-weights plus retrieval-at-inference beats either alone** — Thomson showed domain CPT produces the right answer *shape*; our RAG evaluation showed retrieval produces the right *facts*; harness training unifies them.

### 5.3 What we will measure

- 30-question citizen battery (response rate, citation precision, article-level accuracy — the failure mode Thomson's bare answers exhibited).
- Statute QA with reform sensitivity (same question, pre/post reform year).
- Abstention calibration: false abstention rate vs. hallucination rate.
- Professional mode: motion/contract drafting evaluated by practicing attorneys.

### 5.4 Applicability triage: where small, fast, calibrated models fit

The Bibliotecario's core step — *given a citizen case and N candidate passages, which statutes actually apply?* — is a structured classification, not a generation task. We benchmarked our production model (MiniMax-M3) against a frontier model (GPT-4o) on 4 candidate passages for an unauthorized-charge case: identical verdicts on 3 of 4 passages, with the frontier model *less* inclusive on the genuinely contested one (the passage our triage should keep — recall matters more than precision here). Latency: 37.7s vs 2.0s. Conclusion: the triage step does not need a frontier LLM; it needs a **calibrated, fast, structured-output classifier** — the "System One" model class now emerging (e.g., TypeSafe's Jev: 70–500 ms, calibrated probabilities, $0.042/MTok, designed to never hallucinate on typed outputs). Our roadmap assigns this step to such a model, reserving Tlamatini for what it is uniquely trained for: grounded Mexican legal generation.

## 6. Privacy Architecture as Product

The citizen tier is anonymous by design: no email required (recovery phrase), interview data stays local until explicit opt-in, and consent is a first-class UI object. The firm tier is the strategic differentiator: a sovereign model on-premise, private adapters, zero external API calls. In a market where every cloud legal AI is legally unusable for Mexican despachos, compliance *is* the moat.

## 7. Contributions

1. The first large-scale, documented, **living corpus of Mexican law** (421K documents ingested, 10.7M chunks queryable, 10B+ token universe mapped, 32/32 states covered in primary legislation, differential harvest registry, reproducible techniques for every source).
2. A production **retrieval-anchored legal assistant** with a two-agent conversational architecture (empathic interview + librarian subagent), verified citations, and honest abstention — with the token-budget pathology of reasoning models in RAG pipelines identified and fixed.
3. A training recipe unifying **SaulLM replay + Thomson merge + harness training**, targeting Tlamatini, the first sovereign Mexican legal base model.
4. Evidence that **citation hallucination survives domain CPT** — jurisdiction grounding requires retrieval, and harness format can be trained.
5. Evidence that **applicability triage is solved by small calibrated classifiers, not frontier LLMs** — with a reproduction harness.

## 8. Status & Roadmap

- Corpus: **421K documents · 10.7M chunks · ~3.3B tokens ingested and queryable**; 10B+ token universe mapped; 32/32 states covered in primary legislation; harvests ongoing across registered sources (BC, Edomex, Jalisco in flight).
- System: live at aijusticia.mx (citizen/lawyer tiers, two-agent conversational architecture, public corpus dashboard); firm tier in development pending base model.
- Training: Tlamatini CPT run (Tohil pipeline) on rented 4×H200 upon corpus completion; base decision (Qwen 3.6-35B-A3B vs Qwen 3.8 27B dense) pending the running evaluation; evaluation battery automated.
- Applicability triage: migrating to a calibrated structured-output classifier when System One models reach general availability; comparison harness ready.

---

*Data availability: source registry and harvester scripts are documented; corpus redistribution follows each source's public-access terms (all sources are public government or open-access university repositories).*

*Contact / author list: [to fill]*
