#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Storage em Backblaze B2 (bucket privado + URL de download autorizada).

Arquitetura:
  - Upload: S3-compatible API via boto3 (mais simples e estável).
  - Download URL: API nativa B2 (`b2_get_download_authorization`) — gera um
    token embutido na URL, válido por `validDurationInSeconds`. Como o bucket
    é PRIVADO, o TikTok (e qualquer outro fetch) só consegue baixar pela URL
    assinada, que expira automaticamente.

Credenciais são lidas de `segredos.txt` no BASE_DIR. Não commit nada disso.
"""

import os
import json
import base64
import urllib.request
import urllib.error

import boto3
from botocore.exceptions import ClientError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEGREDOS = os.path.join(BASE_DIR, "segredos.txt")


def _ler_segredo(chave):
    """Lê `chave=` de segredos.txt. Retorna None se não existir."""
    try:
        with open(SEGREDOS, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha.startswith(chave + "="):
                    return linha.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def _credenciais():
    """Lê e devolve (key_id, app_key, bucket, endpoint) do segredos.txt."""
    key_id = _ler_segredo("b2_key_id")
    app_key = _ler_segredo("b2_application_key")
    bucket = _ler_segredo("b2_bucket")
    endpoint = _ler_segredo("b2_endpoint")
    if not all([key_id, app_key, bucket, endpoint]):
        raise RuntimeError(
            "Faltam credenciais B2 no segredos.txt. Precisa de: "
            "b2_key_id, b2_application_key, b2_bucket, b2_endpoint"
        )
    return key_id, app_key, bucket, endpoint


def _b2_authorize(key_id, app_key):
    """Faz b2_authorize_account. Retorna dict com authorizationToken, apiUrl,
    downloadUrl, s3ApiUrl, allowed.bucketId, etc.
    """
    creds_b64 = base64.b64encode(f"{key_id}:{app_key}".encode()).decode()
    req = urllib.request.Request(
        "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
        headers={"Authorization": f"Basic {creds_b64}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"), strict=False)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"b2_authorize_account falhou: HTTP {e.code}: {corpo}")


def _b2_call(api_url, auth_token, body):
    """POST genérico na API B2 com auth_token."""
    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": auth_token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"), strict=False)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"b2_api falhou ({body.get('bucketId', '?')[:8]}...): "
                           f"HTTP {e.code}: {corpo}")


class B2Storage:
    """Cliente B2 com upload (S3-compat) + URL assinada (API nativa).

    Uso:
        b2 = B2Storage()
        b2.upload("videos/2026-09-09/video.mp4", "/local/path/video.mp4")
        url = b2.get_download_url("videos/2026-09-09/video.mp4", valid_seconds=86400)
    """

    def __init__(self):
        key_id, app_key, bucket, endpoint = _credenciais()
        self.key_id = key_id
        self.app_key = app_key
        self.bucket = bucket
        self.endpoint = endpoint
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key,
        )
        # Cache de authorize_account pra não fazer nova chamada a cada operação
        self._acct = None

    def _ensure_account(self):
        if self._acct is None or self._is_token_expired(self._acct):
            self._acct = _b2_authorize(self.key_id, self.app_key)
        return self._acct

    @staticmethod
    def _is_token_expired(acct):
        """Tokens de authorize_account valem ~24h; aqui só checamos se o campo
        existe (não há timestamp público). Como só usamos em POC e o ciclo é
        curto, confiamos no cache em memória entre chamadas."""
        return "authorizationToken" not in acct

    @property
    def bucket_id(self):
        return self._ensure_account()["allowed"]["bucketId"]

    @property
    def api_url(self):
        return self._ensure_account()["apiUrl"]

    @property
    def download_url(self):
        return self._ensure_account()["downloadUrl"]

    def upload(self, key, caminho_local, content_type="video/mp4"):
        """Sobe um arquivo local pro bucket. `key` é o caminho dentro do bucket."""
        with open(caminho_local, "rb") as f:
            self._s3.put_object(
                Bucket=self.bucket, Key=key, Body=f.read(), ContentType=content_type,
            )
        return f"s3://{self.bucket}/{key}"

    def upload_bytes(self, key, dados, content_type="video/mp4"):
        """Sobe bytes direto (sem ler de disco)."""
        self._s3.put_object(
            Bucket=self.bucket, Key=key, Body=dados, ContentType=content_type,
        )
        return f"s3://{self.bucket}/{key}"

    def get_download_url(self, key, valid_seconds=86400):
        """Gera URL HTTPS direta pro arquivo, válida por `valid_seconds`.

        URL formato: https://f005.backblazeb2.com/file/BUCKET/KEY?Authorization=TOKEN
        TikTok (e qualquer cliente HTTP) consegue baixar normalmente.
        """
        acct = self._ensure_account()
        r = _b2_call(
            f"{self.api_url}/b2api/v2/b2_get_download_authorization",
            acct["authorizationToken"],
            {
                "bucketId": self.bucket_id,
                "fileNamePrefix": key,
                "validDurationInSeconds": int(valid_seconds),
            },
        )
        return (
            f"{self.download_url}/file/{self.bucket}/{key}"
            f"?Authorization={r['authorizationToken']}"
        )

    def delete(self, key):
        """Remove um arquivo (útil pra cleanup / testes)."""
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass


def chave_existe():
    """True se segredos.txt tem pelo menos b2_key_id preenchido."""
    return _ler_segredo("b2_key_id") is not None


if __name__ == "__main__":
    # Sanity check quando rodado direto: sobe um arquivo de teste, baixa pela
    # URL assinada, valida conteúdo e limpa.
    import tempfile
    import time
    from datetime import datetime

    if not chave_existe():
        print("B2 não configurado em segredos.txt")
        raise SystemExit(1)

    b2 = B2Storage()
    key = f"tests/b2_module_test_{int(time.time())}.txt"
    payload = (f"b2_storage.py self-test @ {datetime.now().isoformat()}").encode()

    print(f"upload_bytes: {key} ({len(payload)} bytes)")
    b2.upload_bytes(key, payload, content_type="text/plain")

    print("get_download_url(valid_seconds=60)...")
    url = b2.get_download_url(key, valid_seconds=60)
    print(f"  URL: {url[:60]}...{url[-25:]}")

    print("fetch via urllib (simula TikTok pull_from_url)...")
    with urllib.request.urlopen(url, timeout=15) as r:
        body = r.read()
        ct = r.headers.get("Content-Type")
    assert body == payload, "conteúdo retornado difere do enviado"
    print(f"  ✓ HTTP 200  {len(body)} bytes  Content-Type={ct}")

    print("cleanup...")
    b2.delete(key)
    print("OK")
