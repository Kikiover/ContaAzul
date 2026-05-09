# auth.py
import time
import base64
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs
import requests

from config import CLIENT_ID, CLIENT_SECRET, AUTH_URL, TOKEN_URL, REDIRECT_URI
from database import atualizar_tokens


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _basic_auth() -> str:
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(raw.encode()).decode()


def _salvar(cliente_id: str, data: dict, refresh_token_fallback: str = None):
    expires_at = time.time() + data["expires_in"] - 60  # 60s de margem
    atualizar_tokens(
        cliente_id,
        data["access_token"],
        data.get("refresh_token") or refresh_token_fallback,
        expires_at,
    )


# ─── Fluxo inicial (chamado pelo Tkinter ao cadastrar cliente) ────────────────

def gerar_url_autorizacao() -> str:
    params = {
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "state":         "ESTADO",
        "scope":         "openid profile aws.cognito.signin.user.admin",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def extrair_code_da_url(url_retorno: str) -> str:
    """Extrai o `code` da URL colada pelo usuário."""
    parsed = urlparse(url_retorno)
    params = parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if not code:
        raise ValueError("URL inválida: parâmetro `code` não encontrado.")
    return code


def trocar_code_por_tokens(cliente_id: str, code: str):
    import json
    payload = {
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": REDIRECT_URI,
    }
    print("=== DEBUG TOKEN REQUEST ===")
    print(f"URL: {TOKEN_URL}")
    print(f"CLIENT_ID: {CLIENT_ID}")
    print(f"REDIRECT_URI: '{REDIRECT_URI}'")
    print(f"CODE: {code}")
    print(f"PAYLOAD: {payload}")

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data=payload,
        timeout=15,
    )
    print(f"STATUS: {resp.status_code}")
    print(f"RESPOSTA: {resp.text}")
    print("==========================")

    if resp.status_code != 200:
        raise RuntimeError(f"Erro ao obter tokens: {resp.status_code} — {resp.text}")

    _salvar(cliente_id, resp.json())


# ─── Renovação automática ─────────────────────────────────────────────────────

def _renovar(cliente_id: str, refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"[AUTH] Falha ao renovar token ({cliente_id}): "
            f"{resp.status_code} — {resp.text}"
        )

    data = resp.json()
    _salvar(cliente_id, data, refresh_token_fallback=refresh_token)
    print(f"[AUTH] Token renovado: {cliente_id}")
    return data["access_token"]


def get_token_valido(cliente) -> str:
    """
    Retorna um access_token válido. Renova automaticamente se expirado.
    `cliente` é um sqlite3.Row da tabela clientes.
    """
    if not cliente["refresh_token"]:
        raise RuntimeError(
            f"Cliente '{cliente['id']}' sem refresh_token. "
            "Faça o login OAuth2 pela interface."
        )

    expires_at = cliente["expires_at"] or 0
    if time.time() < expires_at and cliente["access_token"]:
        return cliente["access_token"]

    return _renovar(cliente["id"], cliente["refresh_token"])
