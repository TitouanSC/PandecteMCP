#!/usr/bin/env python3
"""Pages « Mon compte » et « Clé personnelle », jouées hors réseau.

L'échange du code WorkOS est simulé ; tout le reste — garde HTTP, routes,
cookies signés, jeton anti-CSRF, base SQLite, transport MCP — est réel.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_oauth_end_to_end import OAuthServerCase  # noqa: E402

from mcp_server import account  # noqa: E402
from mcp_server import server as mcp_app  # noqa: E402
from mcp_server.access import hash_personal_token  # noqa: E402
from mcp_server.quotas import QuotaPolicy  # noqa: E402

CLIENT_ID = "client_01TESTCLIENTID000000"
USER_ID = "user_01ALICEALICEALICE"
EMAIL = "alice@example.org"


def cookie_value(response, name: str) -> str | None:
    """Valeur posée par ``Set-Cookie`` (les cookies ``Secure`` ne circulent pas
    en HTTP clair : les tests les recopient à la main)."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(name + "="):
            return header.split(";", 1)[0].split("=", 1)[1].strip('"')
    return None


def set_cookie_header(response, name: str) -> str:
    return next(h for h in response.headers.get_list("set-cookie") if h.startswith(name + "="))


class SignedCookiesTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000.0
        self.cookies = account.SignedCookies(b"k" * 32, clock=lambda: self.now)

    def test_round_trip(self):
        raw = self.cookies.dump("session", {"sub": USER_ID}, 60)
        self.assertEqual(USER_ID, self.cookies.load("session", raw)["sub"])

    def test_tampered_expired_or_misused_values_are_refused(self):
        raw = self.cookies.dump("session", {"sub": USER_ID}, 60)
        body, signature = raw.split(".")
        forged = json.dumps({"sub": "user_01MALLORYMALLORY", "p": "session", "exp": 2_000_000})
        forged_body = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
        self.assertIsNone(self.cookies.load("session", f"{forged_body}.{signature}"))
        self.assertIsNone(self.cookies.load("login", raw))
        other = account.SignedCookies(b"x" * 32, clock=lambda: self.now)
        self.assertIsNone(other.load("session", raw))
        for bad in ("", "abc", "a.b.c", "x" * 5000):
            self.assertIsNone(self.cookies.load("session", bad))
        self.now += 61
        self.assertIsNone(self.cookies.load("session", raw))


class ExchangeCodeTests(unittest.TestCase):
    def test_pkce_exchange_sends_no_secret_and_keeps_only_the_user(self):
        reponse = io.BytesIO(
            json.dumps(
                {
                    "user": {"id": USER_ID, "email": EMAIL},
                    "access_token": "eyJ.jeton.workos",
                    "refresh_token": "refresh-workos",
                }
            ).encode()
        )
        with mock.patch("urllib.request.urlopen", return_value=reponse) as urlopen:
            user = account.exchange_code("https://api.workos.com", CLIENT_ID, "code-1", "verif")
        self.assertEqual({"id": USER_ID, "email": EMAIL}, user)
        request = urlopen.call_args.args[0]
        self.assertEqual("https://api.workos.com/user_management/authenticate", request.full_url)
        sent = json.loads(request.data)
        self.assertEqual(
            {"client_id": CLIENT_ID, "grant_type": "authorization_code",
             "code": "code-1", "code_verifier": "verif"},
            sent,
        )

    def test_failures_become_categories_without_detail(self):
        http_error = urllib.error.HTTPError(
            "https://api.workos.com", 400, "Bad Request", {}, io.BytesIO(b'{"code":"secret"}')
        )
        for effect, expected in (
            (http_error, "http_400"),
            (urllib.error.URLError("dns"), "URLError"),
        ):
            with mock.patch("urllib.request.urlopen", side_effect=effect):
                with self.assertRaises(account.WorkOSError) as caught:
                    account.exchange_code("https://api.workos.com", CLIENT_ID, "c", "v")
            self.assertEqual(expected, str(caught.exception))
        for document in ({"user": {"id": "pas-un-id"}}, {"autre": 1}, []):
            with mock.patch(
                "urllib.request.urlopen", return_value=io.BytesIO(json.dumps(document).encode())
            ):
                with self.assertRaises(account.WorkOSError):
                    account.exchange_code("https://api.workos.com", CLIENT_ID, "c", "v")


class CookieSecurityTests(unittest.TestCase):
    """HTTPS : cookies Secure et préfixe __Host- ; http://localhost : ni l'un ni
    l'autre, sans quoi Safari ne renvoie jamais le cookie de connexion."""

    def login_cookie_header(self, public_url: str, environment: str) -> tuple[str, str]:
        from starlette.requests import Request

        from mcp_server.runtime import RuntimeSettings

        settings = RuntimeSettings.from_env({
            "MCP_ENV": environment, "MCP_AUTH_MODE": "oauth", "MCP_PUBLIC_URL": public_url,
            "MCP_OAUTH_ISSUER": "https://exemple.authkit.app", "WORKOS_CLIENT_ID": CLIENT_ID,
        })
        pages = account.AccountPages(
            settings=settings, store=lambda: None, quotas=lambda: None,
            pepper=lambda: b"p" * 32,
        )
        request = Request({"type": "http", "method": "GET", "path": "/compte/connexion",
                           "headers": [], "query_string": b""})
        response = asyncio.run(pages.login(request))
        return pages.login_cookie, response.headers["set-cookie"].lower()

    def test_https_uses_secure_host_prefixed_cookies(self):
        name, header = self.login_cookie_header("https://pandecte.example.com", "production")
        self.assertEqual(account.LOGIN_COOKIE, name)
        self.assertIn("; secure", header)

    def test_localhost_development_drops_secure_for_safari(self):
        name, header = self.login_cookie_header("http://localhost:8765", "development")
        self.assertEqual("pandecte_login", name)
        self.assertNotIn("secure", header)
        self.assertIn("httponly", header)


class AccountCase(OAuthServerCase):
    extra_env = {"WORKOS_CLIENT_ID": CLIENT_ID}

    def setUp(self) -> None:
        # La base du serveur rechargé : le vérificateur de jetons la détient.
        self.store = mcp_app.STORE
        self.store.revoke(USER_ID)
        mcp_app.QUOTAS = QuotaPolicy(
            self.store, user_per_minute=50, user_per_day=100,
            global_per_day=1000, keys_per_minute_per_ip=30,
        )
        self.exchanged: list[tuple] = []

        def fake_exchange(api_base, client_id, code, verifier):
            self.exchanged.append((api_base, client_id, code, verifier))
            return {"id": USER_ID, "email": self.email}

        self.email = EMAIL
        patcher = mock.patch.object(mcp_app.ACCOUNT_PAGES, "_exchange", fake_exchange)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_flow(self, flow):
        async def run():
            async with self._running(None) as client:
                return await flow(client)

        return asyncio.run(run())

    async def sign_in(self, client) -> str:
        """Parcours de connexion complet ; rend la valeur du cookie de session."""
        start = await client.get("/compte/connexion")
        login = cookie_value(start, account.LOGIN_COOKIE)
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(start.headers["location"]).query)[
            "state"
        ][0]
        back = await client.get(
            f"/compte/callback?code=code-workos&state={state}",
            headers={"Cookie": f"{account.LOGIN_COOKIE}={login}"},
        )
        self.assertEqual(303, back.status_code, back.text)
        return cookie_value(back, account.SESSION_COOKIE)

    @staticmethod
    def csrf(page) -> str:
        return re.search(r'name="csrf" value="([0-9a-f]{64})"', page.text).group(1)


class SignInTests(AccountCase):
    def test_anonymous_page_offers_sign_in_with_strict_headers(self):
        page = self.run_flow(lambda client: client.get("/compte"))
        self.assertEqual(200, page.status_code)
        self.assertIn("/compte/connexion", page.text)
        self.assertIn("https://exemple.test/mcp", page.text)
        self.assertEqual("no-store", page.headers["cache-control"])
        csp = page.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        self.assertIn(f'<style nonce="{nonce}">', page.text)

    def test_sign_in_redirects_to_authkit_with_pkce(self):
        start = self.run_flow(lambda client: client.get("/compte/connexion"))
        self.assertEqual(302, start.status_code)
        location = urllib.parse.urlsplit(start.headers["location"])
        self.assertEqual(
            "https://api.workos.com/user_management/authorize",
            f"{location.scheme}://{location.netloc}{location.path}",
        )
        query = dict(urllib.parse.parse_qsl(location.query))
        self.assertEqual(CLIENT_ID, query["client_id"])
        self.assertEqual("https://exemple.test/compte/callback", query["redirect_uri"])
        self.assertEqual(("code", "authkit", "S256"),
                         (query["response_type"], query["provider"], query["code_challenge_method"]))
        header = set_cookie_header(start, account.LOGIN_COOKIE).lower()
        for attribute in ("httponly", "secure", "samesite=lax", "path=/"):
            self.assertIn(attribute, header)

    def test_full_sign_in_uses_the_verifier_matching_the_challenge(self):
        async def flow(client):
            start = await client.get("/compte/connexion")
            login = cookie_value(start, account.LOGIN_COOKIE)
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start.headers["location"]).query))
            await client.get(
                f"/compte/callback?code=code-workos&state={query['state']}",
                headers={"Cookie": f"{account.LOGIN_COOKIE}={login}"},
            )
            return start, login, query

        start, login, query = self.run_flow(flow)
        api_base, client_id, code, verifier = self.exchanged[-1]
        self.assertEqual(("https://api.workos.com", CLIENT_ID, "code-workos"),
                         (api_base, client_id, code))
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        self.assertEqual(query["code_challenge"], challenge)
        self.assertGreaterEqual(len(verifier), 43)
        # Le vérificateur ne circule ni dans l'URL ni dans le cookie.
        self.assertNotIn(verifier, start.headers["location"])
        self.assertNotIn(verifier, base64.urlsafe_b64decode(login.split(".")[0] + "==").decode())

    def test_callback_refuses_bad_state_missing_cookie_and_provider_errors(self):
        async def flow(client):
            start = await client.get("/compte/connexion")
            login = cookie_value(start, account.LOGIN_COOKIE)
            cookie = {"Cookie": f"{account.LOGIN_COOKIE}={login}"}
            return [
                await client.get("/compte/callback?code=c&state=" + "A" * 32, headers=cookie),
                await client.get("/compte/callback?code=c&state=" + "A" * 32),
                await client.get("/compte/callback?error=access_denied"),
            ]

        for reponse in self.run_flow(flow):
            self.assertEqual(400, reponse.status_code)
            self.assertIsNone(cookie_value(reponse, account.SESSION_COOKIE))
        self.assertEqual([], self.exchanged)

    def test_exchange_failure_gives_a_clean_error(self):
        def fail(*_args):
            raise account.WorkOSError("http_400")

        with mock.patch.object(mcp_app.ACCOUNT_PAGES, "_exchange", fail):
            async def flow(client):
                start = await client.get("/compte/connexion")
                login = cookie_value(start, account.LOGIN_COOKIE)
                state = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(start.headers["location"]).query
                )["state"][0]
                return await client.get(
                    f"/compte/callback?code=c&state={state}",
                    headers={"Cookie": f"{account.LOGIN_COOKIE}={login}"},
                )

            reponse = self.run_flow(flow)
        self.assertEqual(502, reponse.status_code)
        self.assertIsNone(cookie_value(reponse, account.SESSION_COOKIE))


class PersonalTokenTests(AccountCase):
    def test_generate_use_and_revoke_a_personal_token(self):
        async def flow(client):
            session = await self.sign_in(client)
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            created = await client.post(
                "/compte/jeton", data={"csrf": self.csrf(page)}, headers=cookie
            )
            return session, page, created

        with self.assertLogs("pandecte.mcp.account", level="INFO") as journal:
            session, page, created = self.run_flow(flow)
        self.assertIn(EMAIL, page.text)
        self.assertIn("aucun jeton personnel", page.text)
        self.assertEqual(200, created.status_code)
        self.assertEqual("no-store", created.headers["cache-control"])
        token = re.search(r"pdt_[A-Za-z0-9_-]{43}", created.text).group(0)

        # Seule l'empreinte est stockée, et le jeton ouvre le mode partagé.
        self.assertEqual(USER_ID, self.store.subject_for(hash_personal_token(token, mcp_app.token_pepper())))
        with mock.patch.object(mcp_app.legal_tools, "search", return_value={"ok": True}):
            resultat = self.call_tool(token, "search", {"query": "x"})
        self.assertFalse(self.en_erreur(resultat), resultat.content)
        self.assertEqual(1, mcp_app.QUOTAS.usage_today(USER_ID)[0])

        # Rien de sensible au journal.
        rendu = " | ".join(journal.output)
        for sensible in (token, EMAIL, USER_ID, session):
            self.assertNotIn(sensible, rendu)

        async def revoke(client):
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            self.assertIn("un jeton personnel actif", page.text)
            self.assertIn("1 / 100", page.text)
            return await client.post(
                "/compte/revoquer", data={"csrf": self.csrf(page)}, headers=cookie
            )

        self.assertEqual(303, self.run_flow(revoke).status_code)
        self.assertEqual(401, self.post_mcp(token).status_code)

    def test_new_token_replaces_the_previous_one(self):
        async def flow(client):
            session = await self.sign_in(client)
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            first = await client.post("/compte/jeton", data={"csrf": self.csrf(page)}, headers=cookie)
            second = await client.post("/compte/jeton", data={"csrf": self.csrf(page)}, headers=cookie)
            return [re.search(r"pdt_[A-Za-z0-9_-]{43}", r.text).group(0) for r in (first, second)]

        first, second = self.run_flow(flow)
        self.assertNotEqual(first, second)
        self.assertEqual(401, self.post_mcp(first).status_code)
        self.assertEqual(USER_ID, self.store.subject_for(hash_personal_token(second, mcp_app.token_pepper())))

    def test_forms_require_session_csrf_and_same_origin(self):
        async def flow(client):
            session = await self.sign_in(client)
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            csrf = self.csrf(page)
            return [
                await client.post("/compte/jeton", data={"csrf": csrf}),
                await client.post("/compte/jeton", data={}, headers=cookie),
                await client.post("/compte/jeton", data={"csrf": "0" * 64}, headers=cookie),
                await client.post(
                    "/compte/jeton", data={"csrf": csrf},
                    headers=dict(cookie, Origin="https://site-hostile.example"),
                ),
                await client.post(
                    "/compte/jeton", data={"csrf": csrf},
                    headers=dict(cookie, **{"Sec-Fetch-Site": "cross-site"}),
                ),
            ]

        statuts = [reponse.status_code for reponse in self.run_flow(flow)]
        self.assertEqual([401, 403, 403, 403, 403], statuts)
        self.assertFalse(self.store.has_token(USER_ID))

    def test_browser_form_with_same_origin_headers_is_accepted(self):
        # Ce qu'envoie un vrai navigateur depuis la page : Origin du site et
        # Sec-Fetch-Site same-origin. La politique de référent doit le permettre.
        async def flow(client):
            session = await self.sign_in(client)
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            self.assertEqual("same-origin", page.headers["referrer-policy"])
            return await client.post(
                "/compte/jeton", data={"csrf": self.csrf(page)},
                headers=dict(cookie, Origin="https://exemple.test",
                             **{"Sec-Fetch-Site": "same-origin"}),
            )

        self.assertEqual(200, self.run_flow(flow).status_code)
        self.assertTrue(self.store.has_token(USER_ID))

    def test_logout_clears_the_session(self):
        async def flow(client):
            session = await self.sign_in(client)
            cookie = {"Cookie": f"{account.SESSION_COOKIE}={session}"}
            page = await client.get("/compte", headers=cookie)
            return await client.post(
                "/compte/deconnexion", data={"csrf": self.csrf(page)}, headers=cookie
            )

        reponse = self.run_flow(flow)
        self.assertEqual(303, reponse.status_code)
        self.assertIn("max-age=0", set_cookie_header(reponse, account.SESSION_COOKIE).lower())

    def test_email_is_escaped(self):
        self.email = '<script>alert("x")</script>@example.org'

        async def flow(client):
            session = await self.sign_in(client)
            return await client.get(
                "/compte", headers={"Cookie": f"{account.SESSION_COOKIE}={session}"}
            )

        page = self.run_flow(flow)
        self.assertNotIn('<script>alert("x")', page.text)
        self.assertIn("&lt;script&gt;", page.text)


class PersonalKeyPageTests(AccountCase):
    def test_page_never_sends_the_credentials(self):
        page = self.run_flow(lambda client: client.get("/cle"))
        self.assertEqual(200, page.status_code)
        csp = page.headers["content-security-policy"]
        self.assertIn("default-src 'none'", csp)  # donc aucune connexion sortante
        self.assertNotIn("connect-src", csp)
        # Aucun champ nommé, aucun formulaire : rien ne peut partir même sans JS.
        self.assertNotRegex(page.text, r"<input[^>]*\bname=")
        self.assertNotIn("<form", page.text)
        nonce = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
        self.assertIn(f'<script nonce="{nonce}">', page.text)
        self.assertIn("III.3", page.text)
        self.assertIn("mandat", page.text)

    @unittest.skipUnless(shutil.which("node"), "Node.js absent")
    def test_browser_encoding_matches_the_server(self):
        script = (
            "global.window = {}; global.document = {getElementById: () => null};"
            "global.btoa = s => Buffer.from(s, 'latin1').toString('base64');"
            + account._PERSONAL_KEY_JS
            + "console.log(JSON.stringify(["
            "window.pandecteEncodeKey('identifiant', 'secret-123'),"
            "window.pandecteEncodeKey('0f8c2a54-1b7e', 'c9e1~b7a2?55d0', 'cle-judilibre-01')]));"
        )
        sortie = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        first, second = json.loads(sortie.stdout)
        self.assertEqual("pk1.aWRlbnRpZmlhbnQ.c2VjcmV0LTEyMw", first)
        from mcp_server.access import encode_personal_key
        from pandecte.credentials import PisteCredentials

        self.assertEqual(
            encode_personal_key(PisteCredentials("0f8c2a54-1b7e", "c9e1~b7a2?55d0", "cle-judilibre-01")),
            second,
        )


class WithoutWorkOSTests(OAuthServerCase):
    def test_account_pages_are_absent_but_personal_key_page_remains(self):
        async def flow():
            async with self._running(None) as client:
                return await client.get("/compte"), await client.get("/cle")

        compte, cle = asyncio.run(flow())
        self.assertEqual(404, compte.status_code)
        self.assertEqual(200, cle.status_code)
        self.assertNotIn("/compte", cle.text.split("<footer>")[0].split("</nav>")[0])


if __name__ == "__main__":
    unittest.main()
