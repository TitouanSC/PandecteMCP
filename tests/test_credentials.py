#!/usr/bin/env python3
"""Identifiants PISTE par requête : isolation, cache et masquage.

Fondation du mode « clés personnelles » : les identifiants transmis par une
requête ne servent qu'à elle, ne retombent jamais sur ceux du titulaire du
serveur, n'alimentent pas le cache d'un autre appelant et n'apparaissent ni
dans une réponse ni dans un journal.
"""
from __future__ import annotations

import os
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import anyio
import anyio.to_thread

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

import pandecte.judilibre as judilibre_client  # noqa: E402
import pandecte.legifrance as legifrance_client  # noqa: E402
from pandecte.credentials import (  # noqa: E402
    MASK,
    PisteCredentials,
    active_credentials,
    mask_secrets,
    request_credentials,
    use_credentials,
)
from pandecte.errors import LegifranceError  # noqa: E402

TITULAIRE_ENV = {
    "LEGIFRANCE_CLIENT_ID": "titulaire-id",
    "LEGIFRANCE_CLIENT_SECRET": "titulaire-secret",
    "JUDILIBRE_KEY_ID": "titulaire-keyid",
}
ALICE = PisteCredentials("alice-id", "alice-secret")
BOB = PisteCredentials("bob-id", "bob-secret")


def _token_server():
    """Faux serveur de jetons : un jeton distinct par client_id, compteur d'appels."""
    calls: list[str] = []

    def post(url, payload, headers):
        form = urllib.parse.parse_qs(payload.decode("utf-8"))
        client_id = form["client_id"][0]
        calls.append(client_id)
        return {"access_token": f"jeton-{client_id}-{form['client_secret'][0]}", "expires_in": 3600}

    return post, calls


class CredentialResolutionTests(unittest.TestCase):
    def test_request_credentials_override_the_environment(self):
        with mock.patch.dict(os.environ, TITULAIRE_ENV, clear=True):
            self.assertEqual("titulaire-id", active_credentials().client_id)
            with use_credentials(ALICE):
                self.assertIs(ALICE, active_credentials())
            self.assertIsNone(request_credentials())

    def test_request_without_key_id_never_borrows_the_owner_key_id(self):
        with mock.patch.dict(os.environ, TITULAIRE_ENV, clear=True):
            with use_credentials(ALICE):
                modes = [label for label, _ in judilibre_client.auth_modes()]
            self.assertEqual(["OAuth"], modes)
            with use_credentials(PisteCredentials("a", "b", "alice-keyid")):
                label, headers = judilibre_client.auth_modes()[0]
            self.assertEqual(("KeyId", "alice-keyid"), (label, headers["KeyId"]))

    def test_representation_never_reveals_values(self):
        creds = PisteCredentials("visible-id", "visible-secret", "visible-key")
        for rendu in (repr(creds), str(creds), f"{creds}"):
            self.assertNotIn("visible", rendu)
        self.assertNotIn("visible", creds.fingerprint)

    def test_fingerprint_covers_the_secret(self):
        self.assertNotEqual(
            PisteCredentials("meme-id", "secret-1").fingerprint,
            PisteCredentials("meme-id", "secret-2").fingerprint,
        )


@mock.patch.dict(os.environ, TITULAIRE_ENV, clear=True)
class TokenCacheIsolationTests(unittest.TestCase):
    def setUp(self):
        legifrance_client.clear_token_cache()

    def test_each_caller_gets_its_own_token_and_never_the_owner_one(self):
        post, calls = _token_server()
        with mock.patch("pandecte.legifrance.http_post_json", side_effect=post):
            with use_credentials(ALICE):
                alice = legifrance_client.get_token()
            with use_credentials(BOB):
                bob = legifrance_client.get_token()
            titulaire = legifrance_client.get_token()
            with use_credentials(ALICE):
                alice_again = legifrance_client.get_token()
        self.assertEqual("jeton-alice-id-alice-secret", alice)
        self.assertEqual("jeton-bob-id-bob-secret", bob)
        self.assertEqual("jeton-titulaire-id-titulaire-secret", titulaire)
        self.assertEqual(alice, alice_again)
        self.assertEqual(["alice-id", "bob-id", "titulaire-id"], calls)

    def test_known_client_id_with_wrong_secret_does_not_reuse_the_token(self):
        post, calls = _token_server()
        with mock.patch("pandecte.legifrance.http_post_json", side_effect=post):
            with use_credentials(ALICE):
                legifrance_client.get_token()
            with use_credentials(PisteCredentials("alice-id", "devine")):
                usurpe = legifrance_client.get_token()
        self.assertEqual("jeton-alice-id-devine", usurpe)
        self.assertEqual(2, len(calls))

    def test_cache_is_bounded(self):
        post, _ = _token_server()
        with mock.patch("pandecte.legifrance.http_post_json", side_effect=post), \
                mock.patch.object(legifrance_client, "MAX_CACHED_TOKENS", 2):
            for index in range(5):
                with use_credentials(PisteCredentials(f"id-{index}", "s")):
                    legifrance_client.get_token()
        self.assertEqual(2, len(legifrance_client._TOKEN_CACHE))

    def test_cache_never_stores_raw_credentials(self):
        post, _ = _token_server()
        with mock.patch("pandecte.legifrance.http_post_json", side_effect=post):
            with use_credentials(ALICE):
                legifrance_client.get_token()
        cles = " ".join(legifrance_client._TOKEN_CACHE)
        self.assertNotIn("alice-id", cles)
        self.assertNotIn("alice-secret", cles)

    def test_concurrent_threads_stay_isolated(self):
        post, _ = _token_server()
        results: dict[str, str] = {}
        barrier = threading.Barrier(8)

        def worker(index: int) -> None:
            creds = PisteCredentials(f"user-{index}", f"secret-{index}")
            with use_credentials(creds):
                barrier.wait()
                results[creds.client_id] = legifrance_client.get_token()

        with mock.patch("pandecte.legifrance.http_post_json", side_effect=post):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        for index in range(8):
            self.assertEqual(
                f"jeton-user-{index}-secret-{index}", results[f"user-{index}"]
            )

    def test_credentials_follow_the_sdk_worker_thread(self):
        # Le SDK MCP exécute les outils synchrones via anyio.to_thread.run_sync :
        # les identifiants posés dans la tâche doivent y être visibles.
        async def scenario() -> PisteCredentials | None:
            with use_credentials(ALICE):
                return await anyio.to_thread.run_sync(request_credentials)

        self.assertIs(ALICE, anyio.run(scenario))


class MaskingTests(unittest.TestCase):
    def test_request_credentials_are_masked_raw_and_encoded(self):
        creds = PisteCredentials("id/avec+signes", "secret à masquer", "cle-judilibre")
        texte = (
            "id/avec+signes secret à masquer cle-judilibre "
            + urllib.parse.urlencode({"client_id": creds.client_id, "client_secret": creds.client_secret})
            + " "
            + urllib.parse.quote(creds.client_secret, safe="")
        )
        with mock.patch.dict(os.environ, {}, clear=True), use_credentials(creds):
            rendu = mask_secrets(texte)
        for valeur in (creds.client_id, creds.client_secret, creds.key_id):
            self.assertNotIn(valeur, rendu)
            self.assertNotIn(urllib.parse.quote_plus(valeur), rendu)
            self.assertNotIn(urllib.parse.quote(valeur, safe=""), rendu)
        self.assertIn(MASK, rendu)

    def test_owner_credentials_are_masked_too(self):
        with mock.patch.dict(os.environ, TITULAIRE_ENV, clear=True):
            self.assertNotIn("titulaire-secret", mask_secrets("x titulaire-secret y"))

    def test_server_error_masks_request_credentials(self):
        from mcp_server import server as mcp_app

        def fail():
            raise LegifranceError(
                "refus pour alice-secret",
                exit_code=3,
                detail="HTTP 401 client_id=alice-id&client_secret=alice-secret",
            )

        with mock.patch.dict(os.environ, {}, clear=True), use_credentials(ALICE):
            with self.assertLogs("pandecte.mcp", level="WARNING") as journal:
                with self.assertRaises(mcp_app.ToolError) as caught:
                    mcp_app._safe_call(fail)
        rendu = str(caught.exception) + " | ".join(journal.output)
        self.assertNotIn("alice-secret", rendu)
        self.assertNotIn("alice-id", rendu)


if __name__ == "__main__":
    unittest.main()
