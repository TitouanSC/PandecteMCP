[🇫🇷 Français](README.md) | [🇬🇧 English](README.en.md)

# PandecteMCP

**French legal research for AI assistants: an anti-hallucination method and an
MCP server that queries Légifrance and Judilibre with your own PISTE
credentials (v0.1.0).**

> **Independent project**, not affiliated with the author of the original
> project, with any public figure or institution, or with the French State.
> PandecteMCP **does not replace a lawyer**: it helps find and check sources and
> gives no legal advice. It uses the Légifrance and Judilibre APIs in accordance
> with their terms of use (CGU).

PandecteMCP brings together two parts:

- **a skill** (method) that makes the assistant work from primary sources,
  check the version in force and state what remains unverifiable;
- **a hosted MCP server** that you add to your assistant as a connector:
  **nothing to install**, and every lookup uses **your own** free PISTE
  credentials.

| Use | What you need | For |
|---|---|---|
| Hosted connector | One address to add, your PISTE credentials | claude.ai, ChatGPT, Claude Code and any MCP client |
| Skill only | Nothing, or an optional PISTE key | Assistants that load skills |
| Personal instance | A host or your own computer | Anyone who wants to share their keys with no one |

---

## The problem, in 10 seconds

The danger is not the obvious lie (an "article L. 9999-1" that any recent
model rejects). It is the **plausible lie**: a perfectly formatted but false
reference — impossible to spot by eye.

**Historical illustration** — Gemini 3.5 extended, 5 July 2026, according to
the record kept by the original project. This single test measures neither
current models nor the effect of the tool. Question: *"Give me the exact
reference (chamber, date, appeal number) of three judgments of the Cour de
cassation."* Primary-source check of the three answers:

| AI answer | Reality (Légifrance) | Verdict |
|---|---|---|
| Gabillet — Civ. 2e, 19 févr. 1992, n° 90-19.493 | Ass. plén., 9 mai 1984, n° 80-14.994 | ❌ Chamber, date **and** number wrong |
| Anxiété — Soc., 11 mai 2010, n° 09-42.241 | Soc., 11 mai 2010, n° 09-42.241 | ✅ Correct |
| Rupture brutale — Com., 20 mars 2012, n° 11-13.245 | No judgment with this number | ⚠️ Not found |

Two references out of three are false or phantom — including the **right case
name with an entirely invented reference**. The **Administrative Court of
Orléans**, in its
[judgment of 29/12/2025, n° 2506461](https://opendata.justice-administrative.fr/recherche/shareFile/TA45/DTA_2506461_20251229),
notes cited decisions that do not exist or whose number does not match the
date, and asks counsel to check their references. This finding does not show
which tool produced those references.

**Behaviour prescribed by the skill**, to be checked in practice:
> ⚠️ *I do not produce these appeal numbers without checking them in a primary
> source (Judilibre / Légifrance) — I do not make them up.*

---

## Using PandecteMCP with nothing to install

Server address: **`https://pandecte-mcp.onrender.com/mcp`**

On first connection, your assistant opens the server's **"Connexion PISTE"**
page: you enter your PISTE Client ID and Client Secret there, once. After that,
every lookup uses these credentials without asking again.

### Getting PISTE credentials (free)

1. Create an account on [piste.gouv.fr](https://piste.gouv.fr).
2. Accept the terms of use of the **Légifrance** and **JUDILIBRE** APIs (API
   menu → terms consent), in the **Production** environment.
3. Applications → **Create an application** (Production environment), ticking
   Légifrance and JUDILIBRE.
4. On the application page, **OAuth** block: note the **Client ID** and the
   **Client Secret**. These are the only two values requested.

The detailed walkthrough and common errors are in
[`skill/scripts/README.md`](skill/scripts/README.md).

### claude.ai (web, desktop, mobile)

Settings → **Connectors** → *Add custom connector*: name `PandecteMCP`, URL
`https://pandecte-mcp.onrender.com/mcp`, advanced OAuth fields left empty.
Click **Connect**, then enter your credentials on the "Connexion PISTE" page.

### ChatGPT

Settings → **Apps & Connectors** → Advanced settings → turn on **Developer
mode** (depending on your plan), then **Create**: URL
`https://pandecte-mcp.onrender.com/mcp`, authentication **OAuth**. ChatGPT then
opens the "Connexion PISTE" page.

### Claude Code

```bash
claude mcp add --transport http pandecte https://pandecte-mcp.onrender.com/mcp
```

Then `/mcp` → `pandecte` → **Authenticate**: the browser opens the "Connexion
PISTE" page. The repository plugin declares the same server:

```bash
claude plugin marketplace add TitouanSC/PandecteMCP
claude plugin install pandecte@pandecte
```

### Other MCP clients

Cursor, VS Code, Gemini CLI and other clients supporting "HTTP" MCP servers
connect the same way (OAuth). Clients without OAuth accept a **personal key**
in an `Authorization: Bearer pk1.…` header, assembled in your browser on
[the "Clé personnelle" page](https://pandecte-mcp.onrender.com/cle).
Only claude.ai, ChatGPT and Claude Code have been tested so far.

### Your credentials, and the limits of the service

- **Nothing is stored.** The server checks your credentials with PISTE, then
  **encrypts** them (AES-256-GCM) into the token your assistant keeps. It only
  decrypts them for the duration of each lookup; it never writes them anywhere
  and never logs them. The server holds **no** PISTE credentials of its own.
- **Revoking access**: disconnect the connector, or regenerate your Client
  Secret on PISTE (this immediately invalidates any token containing it).
- **Responsibility**: your credentials remain reserved for your own use
  (Légifrance terms § III.3, Judilibre § XI.C). By entrusting them to the
  service, you authorise it to call the APIs **on your behalf**, as a technical
  intermediary — see the [terms of use](docs/terms-of-use.md). To share them
  with no one, host your own instance.
- **Quotas**: your lookups use **your** PISTE quota. The server also limits
  each IP address to 30 tool calls per minute.
- **Free hosting**: the server sleeps after 15 minutes without activity; the
  next call waits for it to wake up (about 30 seconds) and may fail once.
  Simply try again.
- **Data processed**: see the [privacy policy](docs/privacy-policy.md).

---

## Who it is for

Any practitioner of French law — **the profession is set through a profile**
(see ["Choosing a profile"](#choisir-son-profil)):

- **Law enforcement** (national police, gendarmerie, municipal police)
- **Lawyers** (advice and litigation)
- **In-house counsel** (business law, compliance)
- **Local government officers and lawyers**
- **Law students and exam candidates**
- Anyone who needs reliable legal references in an official act or document

---

## What the skill does

When the assistant detects a legal request (statute article, criminal
qualification, case law, drafting an act, checking whether a text is in
force…), the skill triggers a 9-step procedure including:

- **7 anti-hallucination principles** (primacy of sources, reference date,
  hierarchy of norms, traceable citation, separation of registers, criminal
  legality, informed abstention)
- **9 steps** with explicit exit criteria: qualification (0) → handling of
  missing information (0 bis) → mapping (1) → retrieval (2) → freshness (3) →
  case law (4) → articulation (5) → drafting (6) → self-critique (7)
- **18 failure modes** documented and countered
- **4 reasoning techniques** (adversarial qualification, triangulation,
  textual archaeology, distinguishing)
- **6 modules** activated as needed (PÉNAL, ACTE-ADMIN, PA-PJ, FOND,
  CONTENTIEUX, DOC-AUDIT)
- **Standard output templates** (express, substantive, citation for an act,
  document audit, exam note)
- **Provenance rule**: any official identifier (`LEGIARTI`, `NOR`, appeal
  number…) must come from a tool call in the session, never from memory —
  otherwise it is marked "unverified"
- **Tool-based retrieval**: the MCP server, or the
  `skill/scripts/legifrance.py` script, queries **Légifrance** (codes, texts,
  Conseil d'État and Conseil constitutionnel decisions) and **Judilibre** (Cour
  de cassation, courts of appeal, lower courts). Without access, step 2 falls
  back to a controlled web search on official domains, with the same
  provenance requirements
- **Configurable profiles**: the user's profession is set in a `profil.md` —
  the methodological core stays universal

> 🔑 **The skill works without a key.** Without tools, retrieval uses web search
> on official domains. The MCP server, or a local PISTE key, makes retrieval
> deterministic and strengthens the provenance rule.

---

<a id="choisir-son-profil"></a>
## Choosing a profile

The skill adapts to your profession through a `profil.md` file (context
defaults, never certainties — see [`skill/profils/`](skill/profils/)):

| Profile | For whom | Third self-critique perspective |
|--------|----------|---------------------------|
| `police-gendarmerie` | National police / gendarmerie / municipal police | Defence counsel (procedural nullity) |
| `avocat` | Lawyer (advice, litigation) | Opposing counsel |
| `juriste-entreprise` | Legal department, compliance | The regulator / auditor |
| `collectivites` | Local government officers and lawyers | Prefectoral legality review |
| `etudiant-concours` | Student / exam candidate | The examiner |

**Activation** (after installation):

```bash
cd ~/.claude/skills/pandecte-recherche
cp profils/avocat.md profil.md      # replace with your profile
```

Without `profil.md`, the skill runs with a **neutral profile**: it assumes no
context and asks when the question becomes decisive.

---

## Installing the skill

### With `npx` (recommended)

```bash
npx skills add https://github.com/TitouanSC/PandecteMCP/tree/main/skill --skill pandecte-recherche
```

The skill reports once per session that a new version exists, without
interrupting research. Updating stays in your hands:

```bash
npx skills update pandecte-recherche
```

For automatic updates (global installation), create the file
`.pandecte-recherche-update.json` at the installed root of the skill:

```json
{ "automatic": true }
```

Your `profil.md` and `scripts/.env` are kept.

### Manually

Copy the **contents** of the `skill/` folder into
`~/.claude/skills/pandecte-recherche/` (macOS, Linux):

```bash
git clone https://github.com/TitouanSC/PandecteMCP
cp -r PandecteMCP/skill ~/.claude/skills/pandecte-recherche
```

On Windows:

```powershell
git clone https://github.com/TitouanSC/PandecteMCP
Copy-Item -Recurse PandecteMCP\skill "$env:USERPROFILE\.claude\skills\pandecte-recherche"
```

The `name:` field of `skill/SKILL.md` must match the installation folder name.
The [`docs/installation.md`](docs/installation.md) guide covers the Claude Code
and OpenAI plugins.

### On other platforms

| Folder | Platform | Nature |
|---|---|---|
| [`gemini_skill/`](gemini_skill) | Gemini (Google) | Condensed core, MCP connector first, Google Search fallback |
| [`grok_skill/`](grok_skill) | Grok (xAI) | Condensed core, native web tools |
| [`vibe_skill/`](vibe_skill) | Vibe (Mistral) | Condensed core, `web_search` / `web_fetch` tools |
| [`manus_skill/`](manus_skill) | Manus | Condensed core, MCP connector first |

These packages are **generated** from a single source
([`declinaisons/`](declinaisons/README.md)): a shared condensed core and one
sheet per platform. `skill/` remains the methodological source of truth.

---

## Triggers

The skill activates when you:
- quote or ask for a statute, code article, decree or order
- ask for a legal qualification (criminal, administrative, civil)
- check whether a text is in force, repealed or amended
- ask for case law (Cass., CE, CC, CJEU, ECHR)
- audit, review or legally correct a document or a corpus
- draft a municipal order, a note to the Mayor, a brief
- prepare for an oral or written exam

**Control tags:**
- `[complet]` — exhaustive mode, all modules enabled
- `[express]` — light mode (PÉNAL and DOC-AUDIT stay active when relevant)
- `[syllogisme]` — major / minor / conclusion structure (exams)
- `[opérationnel]` — operational implications section enabled
- `[lookup]` — fast path: one-off reference, minimal output

---

## Hosting your own instance

To share your credentials with no one, run the server yourself:

- **Locally** (Claude Code, Claude Desktop, Cursor…), with your credentials in
  a `.env` file:

```bash
python -m pip install -r requirements-mcp.txt
python mcp_server/server.py
```

- **Online**, on Render (free plan possible) or any Docker host: see the
  [deployment guide](docs/deployment.md). The instance needs no PISTE
  credentials: each of its users signs in with their own.

---

## Repository layout

```
PandecteMCP/
├── .claude-plugin/                 ← Claude Code plugin and marketplace
├── .codex-plugin/                  ← OpenAI plugin
├── .mcp.json                       ← connection to the hosted server
├── mcp_server/
│   ├── server.py                   ← MCP tools (stdio or HTTP /mcp)
│   ├── piste_oauth.py              ← storage-free authorization server
│   ├── sealed.py                   ← encrypted envelopes (AES-256-GCM)
│   ├── connexion.py                ← "Connexion PISTE" page
│   ├── cle.py                      ← "Clé personnelle" page
│   └── catalog.py                  ← list of published tools
├── skills/pandecte-recherche/      ← plugin adapter to the core
├── skill/                          ← standalone skill, source of truth
│   ├── SKILL.md                    ← methodological core
│   ├── CHANGELOG.md                ← version history
│   ├── profils/                    ← professional profiles
│   ├── references/                 ← templates, modules, failure modes…
│   └── scripts/                    ← PISTE access (Légifrance, Judilibre)
├── docs/                           ← deployment, terms, privacy…
├── gemini_skill/ grok_skill/ vibe_skill/ manus_skill/
├── tests/                          ← offline tests and repository checks
├── Dockerfile, render.yaml         ← image and Render Blueprint
├── README.md, README.en.md
└── LICENSE
```

---

## Maintenance

Annual review recommended on **1 September** (start of the legal year).
Detailed procedure → [`skill/references/maintenance.md`](skill/references/maintenance.md).

> **Synchronisation note:** at each version, update `README.md` and its full
> translation `README.en.md`, as well as `skill/CHANGELOG.md`.

---

## Credits and licence

PandecteMCP is a **modified version** of
[droit-francais-skill](https://github.com/brissonjo-sudo/droit-francais-skill),
created by **@brissonjo-sudo**: the research method, failure modes, profiles
and PISTE API access come from it. The modifications (hosted server, sign-in
with the user's PISTE credentials, renaming, documentation) are by
**@TitouanSC**. The project is neither affiliated with nor endorsed by the
original author.

- © 2026 @brissonjo-sudo — original work
- Modifications © 2026 @TitouanSC

The whole is published under
[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](LICENSE),
like the original work. The data consulted come from Légifrance (DILA) and the
Cour de cassation Open Data base (Judilibre).

---

## Contributing

Issues and pull requests are welcome on GitHub.
