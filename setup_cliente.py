# setup_cliente.py
"""
Cadastra um novo cliente e realiza o fluxo OAuth2 inicial.
Execute uma vez por cliente.

    python setup_cliente.py
"""
import sys
import base64
import requests
from database import init_controle, cadastrar_cliente
from auth import salvar_tokens_iniciais
from config import TOKEN_URL

REDIRECT_URI = "https://seuapp.com/callback"  # ajuste para o seu redirect cadastrado na Conta Azul


def url_autorizacao(client_id: str) -> str:
    return (
        "https://auth.contaazul.com/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid"
    )


def trocar_code(client_id: str, client_secret: str, code: str) -> dict:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[ERRO] {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.json()


def main():
    init_controle()

    print("\n=== Cadastro de Cliente — Conta Azul ===\n")
    cid    = input("ID único do cliente (ex: empresa_xpto): ").strip()
    nome   = input("Nome do cliente: ").strip()
    clt_id = input("Client ID (OAuth2): ").strip()
    secret = input("Client Secret (OAuth2): ").strip()

    cadastrar_cliente(cid, nome, clt_id, secret)

    print(f"\n[AUTH] Abra no navegador e autorize:\n\n  {url_autorizacao(clt_id)}\n")
    code = input("Cole o `code` da URL de callback: ").strip()

    print("[AUTH] Trocando code por tokens...")
    tokens = trocar_code(clt_id, secret, code)

    salvar_tokens_iniciais(
        cliente_id=cid,
        client_id=clt_id,
        client_secret=secret,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"],
    )

    print(f"\n✓ Cliente '{nome}' pronto.")
    print(f"  Execute: python main.py {cid}")


if __name__ == "__main__":
    main()
