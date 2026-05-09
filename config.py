# config.py
import os
import private

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Banco de controle (só no seu PC, nunca vai pro Drive) ───────────────────
CONTROLE_DB = os.path.join(BASE_DIR, "controle.db")

# ─── Pasta raiz dos bancos dos clientes (dentro do Google Drive) ─────────────
# Exemplos:
# Windows: r"C:\Users\Você\Google Drive\My Drive\ContaAzul"
# Mac:     "/Users/você/Library/CloudStorage/GoogleDrive-email/My Drive/ContaAzul"
DRIVE_ROOT = r"G:\Meu Drive\database"  # ← ajuste para o caminho real

# ─── OAuth2 — suas credenciais fixas ─────────────────────────────────────────
CLIENT_ID     = private.CLIENT_ID
CLIENT_SECRET = private.CLIENT_SECRET
REDIRECT_URI  = "https://contaazul.com"   # URI cadastrada no app Conta Azul

# ─── URLs da API ─────────────────────────────────────────────────────────────
AUTH_URL      = "https://auth.contaazul.com/oauth2/authorize"
TOKEN_URL     = "https://auth.contaazul.com/oauth2/token"
API_BASE      = "https://api-v2.contaazul.com"

# ─── Comportamento do sync ───────────────────────────────────────────────────
PAGE_SIZE              = 1000   # máximo suportado pela API
MAX_RETRIES            = 3
RETRY_DELAY            = 5      # segundos entre tentativas
DELAY_ENTRE_CLIENTES   = 2      # segundos de pausa entre clientes

# Range de datas para contas a pagar/receber (exigido pela API)
# Primeira sync: ANOS_HISTORICO para trás + ANOS_FUTURO para frente
ANOS_HISTORICO = 5
ANOS_FUTURO    = 2

os.makedirs(DRIVE_ROOT, exist_ok=True)
