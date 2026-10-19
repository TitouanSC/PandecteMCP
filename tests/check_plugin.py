#!/usr/bin/env python3
"""Contrôles locaux du socle plugin, sans dépendance externe.

Le validateur officiel reste la référence pour le paquet final. Ces contrôles
reproduisent les invariants du dépôt qui doivent aussi rester vérifiables dans
la CI publique : manifeste minimal, découverte native du skill et maintien du
point d'entrée historique.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
SERVER = ROOT / "mcp_server" / "server.py"

#: Socle du plugin Claude Code. Il n'etait couvert par aucun controle : sa
#: version pouvait diverger de SERVER_VERSION en silence, alors meme que
#: `.github/auto-review.md` affirmait que ce fichier le verifiait.
#: Le plugin Claude vit dans son propre dossier : claude.ai ne lui donne que
#: ce dossier, d'où la copie générée du skill complet.
PLUGIN_CLAUDE = ROOT / "plugin"
MANIFEST_CLAUDE = PLUGIN_CLAUDE / ".claude-plugin" / "plugin.json"
MARKETPLACE_CLAUDE = ROOT / ".claude-plugin" / "marketplace.json"

# Limites publiees par OpenAI pour la soumission au repertoire d'applications.
# Elles sont recopiees ici plutot que deduites : un depassement fait echouer la
# soumission sans que rien, dans le depot, ne l'ait signale auparavant.
# Source : https://developers.openai.com/plugins/deploy/submission-errors
LIMITES_TEXTE = {
    "displayName": 30,
    "shortDescription": 30,
    "longDescription": 4000,
    "developerName": 80,
}
CATEGORIES = frozenset(
    {
        "Productivity", "Creativity", "Developer Tools", "Business & Operations",
        "Data & Analytics", "Communication", "Education & Research", "Security",
        "Finance", "Healthcare", "Travel", "Entertainment", "Other",
    }
)
MAX_PROMPTS = 3
MAX_LONGUEUR_PROMPT = 128
MAX_CAPABILITIES = 20
MAX_LONGUEUR_CAPABILITY = 120
MAX_LONGUEUR_URL = 1024

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PLUGIN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLUGIN_FIELDS = ("name", "version", "description", "author", "skills", "interface")
INTERFACE_FIELDS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "defaultPrompt",
)
#: Les quatre URL exigees a la soumission. « supportURL » manquait au
#: manifeste : son absence ne se serait vue qu'au depot du dossier.
PUBLIC_URL_FIELDS = (
    "websiteURL",
    "supportURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
)
#: Logo et icône sont obligatoires a la soumission (erreurs
#: plugin_logo_path_missing et plugin_composer_icon_path_missing).
LOCAL_ASSET_FIELDS = (
    "composerIcon",
    "logo",
)
#: Formats acceptes pour les visuels du paquet, et leurs bornes.
FORMATS_IMAGE = frozenset({".png", ".jpg", ".jpeg", ".webp", ".svg"})
MAX_OCTETS_IMAGE = 5 * 1024 * 1024
MIN_COTE_IMAGE = 48
MAX_COTE_IMAGE = 4096
#: brandColor : hexadecimal a six chiffres, contraste d'au moins 2:1 sur blanc.
COULEUR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
CONTRASTE_MIN = 2.0


def luminance(couleur: str) -> float:
    """Luminance relative WCAG d'une couleur #RRGGBB."""
    canaux = []
    for i in (1, 3, 5):
        c = int(couleur[i:i + 2], 16) / 255
        canaux.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canaux
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    claire, sombre = sorted((luminance(a), luminance(b)), reverse=True)
    return (claire + 0.05) / (sombre + 0.05)


def cotes_svg(texte: str) -> tuple[float, float] | None:
    """Côtés d'un SVG : viewBox numérique, sinon width/height sans unité."""
    racine = re.search(r"<svg\b[^>]*>", texte)
    if racine is None:
        return None
    balise = racine.group(0)
    vue = re.search(r'viewBox="([^"]+)"', balise)
    if vue:
        try:
            nombres = [float(x) for x in vue.group(1).replace(",", " ").split()]
        except ValueError:
            return None
        return (nombres[2], nombres[3]) if len(nombres) == 4 else None
    largeur = re.search(r'\bwidth="([0-9.]+)"', balise)
    hauteur = re.search(r'\bheight="([0-9.]+)"', balise)
    if largeur and hauteur:
        return float(largeur.group(1)), float(hauteur.group(1))
    return None


def cotes_png(octets: bytes) -> tuple[int, int] | None:
    if octets[:8] != b"\x89PNG\r\n\x1a\n" or octets[12:16] != b"IHDR":
        return None
    return int.from_bytes(octets[16:20], "big"), int.from_bytes(octets[20:24], "big")


def defaut_image(chemin: Path) -> str | None:
    """Ce qui empêcherait OpenAI d'accepter ce logo ou cette icône, sinon None."""
    suffixe = chemin.suffix.lower()
    if suffixe not in FORMATS_IMAGE:
        return f"format refusé ({suffixe or 'sans extension'})"
    octets = chemin.read_bytes()
    if len(octets) > MAX_OCTETS_IMAGE:
        return "dépasse 5 Mio"
    if suffixe == ".svg":
        try:
            cotes = cotes_svg(octets.decode("utf-8"))
        except UnicodeDecodeError:
            return "SVG non UTF-8"
        if cotes is None:
            return "SVG sans viewBox ni width/height numériques"
    elif suffixe == ".png":
        cotes = cotes_png(octets)
        if cotes is None:
            return "PNG illisible"
    else:
        # JPEG et WebP : format accepté, dimensions non lues ici.
        return None
    largeur, hauteur = cotes
    if largeur != hauteur:
        return f"image non carrée ({largeur:g}×{hauteur:g})"
    if largeur < MIN_COTE_IMAGE:
        return f"image trop petite ({largeur:g} px, minimum {MIN_COTE_IMAGE})"
    if suffixe == ".png" and largeur > MAX_COTE_IMAGE:
        return f"image trop grande ({largeur:g} px, maximum {MAX_COTE_IMAGE})"
    return None


def fail(message: str, problems: list[str]) -> None:
    problems.append(message)


def charger_json(chemin: Path, problems: list[str]) -> dict | None:
    """Lit un manifeste JSON, en signalant absence et illisibilite."""
    if not chemin.is_file():
        fail(f"manifeste absent : {chemin.relative_to(ROOT)}", problems)
        return None
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"manifeste illisible ({chemin.relative_to(ROOT)}) : {exc}", problems)
        return None


def controler_socle_claude(
    manifeste: dict,
    marketplace: dict,
    server_version: str,
    problems: list[str],
) -> None:
    """Controle le couple manifeste/marketplace du plugin Claude Code.

    Fonction pure, sans acces disque : elle reste ainsi eprouvable sur des
    donnees qui violent chaque invariant, faute de quoi le controle passerait
    toujours sans rien verifier.
    """
    nom = manifeste.get("name")
    if not isinstance(nom, str) or PLUGIN_NAME.fullmatch(nom) is None:
        fail("name du plugin Claude Code absent ou hors kebab-case", problems)

    version = manifeste.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        fail("version du plugin Claude Code hors SemVer strict", problems)
        version = None
    elif server_version and version != server_version:
        fail(
            f"version du manifeste Claude Code ({version}) differente de "
            f"SERVER_VERSION ({server_version}) : le plugin suit le serveur MCP",
            problems,
        )

    proprietaire = marketplace.get("owner")
    if not isinstance(proprietaire, dict) or not str(
        proprietaire.get("name", "")
    ).strip():
        fail("marketplace.owner doit etre un objet portant un nom", problems)

    entrees = marketplace.get("plugins")
    if not isinstance(entrees, list) or not entrees:
        fail("marketplace.plugins doit etre une liste non vide", problems)
        return

    entree = next(
        (item for item in entrees if isinstance(item, dict) and item.get("name") == nom),
        None,
    )
    if entree is None:
        fail(f"le marketplace ne reference pas le plugin {nom!r}", problems)
        return

    # Le plugin est le dossier plugin/ du depot : toute autre source ferait
    # installer autre chose que ce qui est versionne et controle ici.
    if entree.get("source") != "./plugin":
        fail(
            "l'entree marketplace doit porter source './plugin' "
            "(le dossier du plugin Claude)",
            problems,
        )
    if version is not None and entree.get("version") != version:
        fail(
            f"version de l'entree marketplace ({entree.get('version')}) "
            f"differente du manifeste Claude Code ({version})",
            problems,
        )


def main() -> int:
    problems: list[str] = []

    if not MANIFEST.is_file():
        print("❌ Manifeste absent : .codex-plugin/plugin.json")
        return 1

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ Manifeste illisible : {exc}")
        return 1

    for field in PLUGIN_FIELDS:
        if field not in manifest:
            fail(f"champ obligatoire absent : {field}", problems)

    # Le nom du plugin (« pandecte ») diffère volontairement de celui du dépôt
    # (« PandecteMCP ») : l'égalité qu'exigeait le projet d'origine n'a pas
    # cours ici. La cohérence qui compte — même nom dans les deux manifestes
    # et les marketplaces — est contrôlée plus bas.
    name = manifest.get("name")
    if not isinstance(name, str) or PLUGIN_NAME.fullmatch(name) is None:
        fail("name doit être un slug en minuscules séparé par des tirets", problems)

    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        fail("version doit respecter SemVer strict (x.y.z)", problems)

    if manifest.get("skills") != "./skills/":
        fail("skills doit pointer vers ./skills/", problems)

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        fail("interface doit être un objet JSON", problems)
    else:
        for field in INTERFACE_FIELDS:
            if field not in interface:
                fail(f"champ interface absent : {field}", problems)
        capabilities = interface.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.strip() for item in capabilities
        ):
            fail("interface.capabilities doit être une liste de chaînes", problems)
        for field in PUBLIC_URL_FIELDS:
            value = interface.get(field)
            parsed = urlparse(value) if isinstance(value, str) else None
            if not parsed or parsed.scheme != "https" or not parsed.netloc:
                fail(f"interface.{field} doit être une URL HTTPS publique", problems)
        for field in LOCAL_ASSET_FIELDS:
            value = interface.get(field)
            if not isinstance(value, str) or not value.strip():
                fail(f"interface.{field} doit être un chemin relatif", problems)
                continue
            if not value.startswith("./") or not value[2:].strip():
                fail(
                    f"interface.{field} doit être un chemin relatif au dépôt "
                    f"de la forme ./chemin/fichier.svg",
                    problems,
                )
                continue
            asset = (ROOT / value[2:]).resolve()
            if ROOT not in asset.parents:
                fail(f"interface.{field} sort du dépôt : {value}", problems)
            elif not asset.is_file():
                fail(f"interface.{field} pointe vers un fichier absent : {value}", problems)
            elif (defaut := defaut_image(asset)) is not None:
                fail(f"interface.{field} : {defaut} ({value})", problems)

        couleur = interface.get("brandColor")
        if couleur is not None:
            if not isinstance(couleur, str) or COULEUR_HEX.fullmatch(couleur) is None:
                fail("interface.brandColor doit être de la forme #RRGGBB", problems)
            elif contraste(couleur, "#FFFFFF") < CONTRASTE_MIN:
                fail(
                    f"interface.brandColor {couleur} contraste trop peu sur blanc "
                    f"(minimum {CONTRASTE_MIN:g}:1)",
                    problems,
                )

        for champ, limite in LIMITES_TEXTE.items():
            valeur = interface.get(champ)
            if isinstance(valeur, str) and len(valeur) > limite:
                fail(
                    f"interface.{champ} fait {len(valeur)} caracteres, "
                    f"la soumission OpenAI en accepte {limite} au plus",
                    problems,
                )
        if interface.get("category") not in CATEGORIES:
            fail(
                "interface.category doit figurer dans la liste OpenAI : "
                f"{sorted(CATEGORIES)}",
                problems,
            )
        for champ in PUBLIC_URL_FIELDS:
            valeur = interface.get(champ)
            if isinstance(valeur, str) and len(valeur) > MAX_LONGUEUR_URL:
                fail(
                    f"interface.{champ} depasse {MAX_LONGUEUR_URL} caracteres",
                    problems,
                )
        if isinstance(capabilities, list):
            if len(capabilities) > MAX_CAPABILITIES:
                fail(
                    f"interface.capabilities compte {len(capabilities)} entrees, "
                    f"la soumission en accepte {MAX_CAPABILITIES} au plus",
                    problems,
                )
            for item in capabilities:
                if isinstance(item, str) and len(item) > MAX_LONGUEUR_CAPABILITY:
                    fail(
                        f"une capability depasse {MAX_LONGUEUR_CAPABILITY} caracteres",
                        problems,
                    )
        prompts = interface.get("defaultPrompt")
        if not isinstance(prompts, list) or not prompts:
            fail("interface.defaultPrompt doit etre une liste non vide", problems)
        else:
            if len(prompts) > MAX_PROMPTS:
                fail(
                    f"interface.defaultPrompt compte {len(prompts)} entrees, "
                    f"la soumission en accepte {MAX_PROMPTS} au plus",
                    problems,
                )
            if len(set(prompts)) != len(prompts):
                fail("les prompts de demarrage doivent etre distincts", problems)
            for item in prompts:
                if not isinstance(item, str) or not item.strip():
                    fail("un prompt de demarrage est vide", problems)
                elif len(item) > MAX_LONGUEUR_PROMPT:
                    fail(
                        f"un prompt de demarrage depasse {MAX_LONGUEUR_PROMPT} caracteres",
                        problems,
                    )

    # Le manifeste du plugin suit la version du serveur MCP : ce sont les deux
    # faces d'un meme deploiement. Le skill, lui, garde sa propre ligne
    # editoriale et n'est pas contraint ici.
    server_version = ""
    if SERVER.is_file():
        trouve = re.search(
            r'^SERVER_VERSION = "([^"]+)"', SERVER.read_text(encoding="utf-8"), re.M
        )
        if trouve:
            server_version = trouve.group(1)
            if version != server_version:
                fail(
                    f"version du manifeste ({version}) differente de SERVER_VERSION "
                    f"({server_version}) : le plugin suit le serveur MCP",
                    problems,
                )

    # Meme regle pour le socle Claude Code, jusqu'ici hors de toute couverture.
    manifeste_claude = charger_json(MANIFEST_CLAUDE, problems)
    marketplace_claude = charger_json(MARKETPLACE_CLAUDE, problems)
    if manifeste_claude is not None and marketplace_claude is not None:
        controler_socle_claude(
            manifeste_claude, marketplace_claude, server_version, problems
        )

    if "[TODO:" in json.dumps(manifest, ensure_ascii=False):
        fail("le manifeste contient encore un marqueur TODO", problems)

    adapter = ROOT / "skills" / "pandecte-recherche" / "SKILL.md"
    legacy = ROOT / "skill" / "SKILL.md"
    if not adapter.is_file():
        fail("adaptateur plugin absent : skills/pandecte-recherche/SKILL.md", problems)
    else:
        adapter_text = adapter.read_text(encoding="utf-8")
        if "name: pandecte-recherche" not in adapter_text:
            fail("le nom de l'adaptateur ne correspond pas à son dossier", problems)
        if "../../skill/SKILL.md" not in adapter_text:
            fail("l'adaptateur ne charge pas le skill historique", problems)
        adapter_target = (adapter.parent / "../../skill/SKILL.md").resolve()
        if adapter_target != legacy.resolve():
            fail("le chemin de l'adaptateur ne résout pas vers skill/SKILL.md", problems)

    if not legacy.is_file():
        fail("point d'entrée historique supprimé : skill/SKILL.md", problems)

    # Plugin Claude : skill copié (pas d'adaptateur, rien hors du dossier) et
    # même connecteur que le dépôt.
    skill_plugin = PLUGIN_CLAUDE / "skills" / "pandecte-recherche" / "SKILL.md"
    if not skill_plugin.is_file():
        fail("skill absent du plugin : plugin/skills/pandecte-recherche/SKILL.md", problems)
    elif legacy.is_file() and skill_plugin.read_bytes() != legacy.read_bytes():
        fail("skill du plugin périmé : lancer python declinaisons/generer.py", problems)
    mcp_plugin = charger_json(PLUGIN_CLAUDE / ".mcp.json", problems)
    mcp_racine = charger_json(ROOT / ".mcp.json", problems)
    if mcp_plugin is not None and mcp_racine is not None and mcp_plugin != mcp_racine:
        fail("plugin/.mcp.json diffère de .mcp.json : un seul connecteur", problems)

    for policy in ("docs/privacy-policy.md", "docs/terms-of-use.md"):
        if not (ROOT / policy).is_file():
            fail(f"document public absent : {policy}", problems)

    companions = (("apps", ".app.json"), ("mcpServers", ".mcp.json"))
    for field, filename in companions:
        if field in manifest and not (ROOT / filename).is_file():
            fail(f"{field} est déclaré sans fichier compagnon {filename}", problems)

    mcp_manifest = ROOT / ".mcp.json"
    if manifest.get("mcpServers") == "./.mcp.json" and mcp_manifest.is_file():
        try:
            mcp_payload = json.loads(mcp_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(f".mcp.json est illisible : {exc}", problems)
        else:
            servers = mcp_payload.get("mcpServers")
            if not isinstance(servers, dict) or not servers:
                fail(".mcp.json.mcpServers doit être un objet non vide", problems)
            else:
                legal_server = servers.get("pandecte")
                if not isinstance(legal_server, dict):
                    fail("serveur MCP pandecte absent", problems)
                elif legal_server.get("type") in {"http", "sse"}:
                    url = legal_server.get("url")
                    if not isinstance(url, str) or not url.startswith("https://"):
                        fail("URL du serveur MCP distant absente ou non HTTPS", problems)
                else:
                    command = legal_server.get("command")
                    args = legal_server.get("args")
                    if not isinstance(command, str) or not command.strip():
                        fail("commande du serveur MCP absente", problems)
                    if not isinstance(args, list) or not all(
                        isinstance(item, str) and item.strip() for item in args
                    ):
                        fail("arguments du serveur MCP invalides", problems)
                    elif "./mcp_server/server.py" not in args:
                        fail("le serveur MCP ne lance pas mcp_server/server.py", problems)
                    elif not (ROOT / "mcp_server" / "server.py").is_file():
                        fail("point d'entrée mcp_server/server.py absent", problems)

            serialized_mcp = json.dumps(mcp_payload, ensure_ascii=False)
            for secret_name in (
                "LEGIFRANCE_CLIENT_ID",
                "LEGIFRANCE_CLIENT_SECRET",
                "JUDILIBRE_KEY_ID",
                "PISTE_KEY_ID",
            ):
                if secret_name in serialized_mcp:
                    fail(
                        f"secret ou variable sensible interdit dans .mcp.json : {secret_name}",
                        problems,
                    )

    if problems:
        print(f"❌ {len(problems)} problème(s) dans le socle plugin :")
        for problem in problems:
            print(f"   - {problem}")
        return 1

    print("✅ Socle plugin cohérent ; skill historique préservé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
