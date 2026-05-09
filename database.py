# database.py
import os
import sqlite3
from config import CONTROLE_DB, DRIVE_ROOT


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _conectar(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ═══════════════════════════════════════════════════════════════════════════════
# BANCO DE CONTROLE  (local, só seu — tokens, clientes, logs)
# ═══════════════════════════════════════════════════════════════════════════════

def conn_controle() -> sqlite3.Connection:
    return _conectar(CONTROLE_DB)


def init_controle():
    with conn_controle() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id                      TEXT PRIMARY KEY,
                nome                    TEXT NOT NULL,
                access_token            TEXT,
                refresh_token           TEXT,
                expires_at              REAL,
                -- marcadores de sync por tipo
                ultima_sync_pessoas     TEXT,
                ultima_sync_receber     TEXT,
                ultima_sync_pagar       TEXT,
                ultima_sync_contas      TEXT,
                ultima_sync_saldos      TEXT,
                ultima_sync_saldo_ini   TEXT,
                ultima_sync_categorias  TEXT,
                ativo                   INTEGER DEFAULT 1,
                criado_em               TEXT DEFAULT (datetime('now')),
                atualizado_em           TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id    TEXT NOT NULL,
                tipo          TEXT NOT NULL,
                status        TEXT NOT NULL,   -- 'ok' | 'erro'
                registros     INTEGER DEFAULT 0,
                mensagem      TEXT,
                iniciado_em   TEXT DEFAULT (datetime('now')),
                finalizado_em TEXT
            );
        """)


def cadastrar_cliente(id_cliente: str, nome: str):
    with conn_controle() as conn:
        conn.execute("""
            INSERT INTO clientes (id, nome)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nome=excluded.nome,
                atualizado_em=datetime('now')
        """, (id_cliente, nome))


def get_clientes_ativos() -> list:
    with conn_controle() as conn:
        return conn.execute(
            "SELECT * FROM clientes WHERE ativo = 1 ORDER BY nome"
        ).fetchall()


def get_cliente(id_cliente: str):
    with conn_controle() as conn:
        return conn.execute(
            "SELECT * FROM clientes WHERE id = ?", (id_cliente,)
        ).fetchone()


def atualizar_tokens(cliente_id: str, access_token: str, refresh_token: str, expires_at: float):
    with conn_controle() as conn:
        conn.execute("""
            UPDATE clientes SET
                access_token  = ?,
                refresh_token = ?,
                expires_at    = ?,
                atualizado_em = datetime('now')
            WHERE id = ?
        """, (access_token, refresh_token, expires_at, cliente_id))


def atualizar_ultima_sync(cliente_id: str, tipo: str, timestamp_iso: str):
    """
    tipo: 'pessoas' | 'receber' | 'pagar' | 'contas' | 'saldos' | 'saldo_ini'
    """
    col = f"ultima_sync_{tipo}"
    with conn_controle() as conn:
        conn.execute(
            f"UPDATE clientes SET {col}=?, atualizado_em=datetime('now') WHERE id=?",
            (timestamp_iso, cliente_id)
        )


def registrar_log(cliente_id: str, tipo: str, status: str,
                  registros: int = 0, mensagem: str = None):
    with conn_controle() as conn:
        conn.execute("""
            INSERT INTO sync_log (cliente_id, tipo, status, registros, mensagem, finalizado_em)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (cliente_id, tipo, status, registros, mensagem))


# ═══════════════════════════════════════════════════════════════════════════════
# BANCO DO CLIENTE  (no Google Drive — só dados financeiros)
# ═══════════════════════════════════════════════════════════════════════════════

def caminho_db_cliente(cliente_id: str) -> str:
    pasta = os.path.join(DRIVE_ROOT, cliente_id)
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, "dados.db")


def conn_cliente(cliente_id: str) -> sqlite3.Connection:
    return _conectar(caminho_db_cliente(cliente_id))


def init_db_cliente(cliente_id: str):
    with conn_cliente(cliente_id) as conn:
        conn.executescript("""
            -- Clientes e fornecedores da empresa
            CREATE TABLE IF NOT EXISTS pessoas (
                id              TEXT PRIMARY KEY,
                nome            TEXT,
                documento       TEXT,
                tipo_pessoa     TEXT,
                perfis          TEXT,   -- JSON: ["CLIENTE","FORNECEDOR"]
                email           TEXT,
                telefone        TEXT,
                ativo           INTEGER,
                data_criacao    TEXT,
                data_alteracao  TEXT,
                payload_raw     TEXT,
                sincronizado_em TEXT DEFAULT (datetime('now'))
            );

            -- Contas a receber (parcelas)
            CREATE TABLE IF NOT EXISTS contas_receber (
                id               TEXT PRIMARY KEY,
                descricao        TEXT,
                data_vencimento  TEXT,
                data_competencia TEXT,
                data_criacao     TEXT,
                data_alteracao   TEXT,
                status           TEXT,
                total            REAL,
                pago             REAL,
                nao_pago         REAL,
                cliente_id       TEXT,
                cliente_nome     TEXT,
                categorias       TEXT,   -- JSON
                centros_custo    TEXT,   -- JSON
                payload_raw      TEXT,
                sincronizado_em  TEXT DEFAULT (datetime('now'))
            );

            -- Contas a pagar (parcelas)
            CREATE TABLE IF NOT EXISTS contas_pagar (
                id               TEXT PRIMARY KEY,
                descricao        TEXT,
                data_vencimento  TEXT,
                data_competencia TEXT,
                data_criacao     TEXT,
                data_alteracao   TEXT,
                status           TEXT,
                total            REAL,
                pago             REAL,
                nao_pago         REAL,
                fornecedor_id    TEXT,
                fornecedor_nome  TEXT,
                categorias       TEXT,   -- JSON
                centros_custo    TEXT,   -- JSON
                payload_raw      TEXT,
                sincronizado_em  TEXT DEFAULT (datetime('now'))
            );

            -- Contas financeiras (bancos, caixas, cartões)
            CREATE TABLE IF NOT EXISTS contas_financeiras (
                id              TEXT PRIMARY KEY,
                nome            TEXT,
                banco           TEXT,
                tipo            TEXT,
                agencia         TEXT,
                numero          TEXT,
                ativo           INTEGER,
                conta_padrao    INTEGER,
                payload_raw     TEXT,
                sincronizado_em TEXT DEFAULT (datetime('now'))
            );

            -- Saldo atual capturado a cada sync (histórico por snapshot)
            CREATE TABLE IF NOT EXISTS saldos_snapshot (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conta_id        TEXT NOT NULL,
                conta_nome      TEXT,
                saldo_atual     REAL,
                capturado_em    TEXT DEFAULT (datetime('now'))
            );

            -- Saldo inicial configurado no ERP por período
            CREATE TABLE IF NOT EXISTS saldos_iniciais (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                id_conta_financeira TEXT NOT NULL,
                data_competencia    TEXT NOT NULL,
                saldo_inicial       REAL,
                tipo                TEXT,   -- RECEITA | DESPESA
                sincronizado_em     TEXT DEFAULT (datetime('now')),
                UNIQUE(id_conta_financeira, data_competencia)
            );
            
            CREATE TABLE IF NOT EXISTS categorias (
                id              TEXT PRIMARY KEY,
                nome            TEXT,
                tipo            TEXT,       -- RECEITA | DESPESA
                categoria_pai   TEXT,
                entrada_dre     TEXT,
                considera_custo_dre INTEGER,
                sincronizado_em TEXT DEFAULT (datetime('now'))
            );
                           
            CREATE VIEW IF NOT EXISTS categorias_completas AS
            SELECT
                c.id,
                c.nome,
                c.tipo,
                c.categoria_pai       AS categoria_pai_id,
                p.nome                AS categoria_pai_nome,
                c.entrada_dre,
                c.considera_custo_dre,
                c.sincronizado_em
            FROM categorias c
            LEFT JOIN categorias p ON p.id = c.categoria_pai;

            -- Índices para filtros comuns no Power BI
            CREATE INDEX IF NOT EXISTS idx_receber_vencimento  ON contas_receber(data_vencimento);
            CREATE INDEX IF NOT EXISTS idx_receber_status      ON contas_receber(status);
            CREATE INDEX IF NOT EXISTS idx_receber_cliente     ON contas_receber(cliente_id);
            CREATE INDEX IF NOT EXISTS idx_pagar_vencimento    ON contas_pagar(data_vencimento);
            CREATE INDEX IF NOT EXISTS idx_pagar_status        ON contas_pagar(status);
            CREATE INDEX IF NOT EXISTS idx_pagar_fornecedor    ON contas_pagar(fornecedor_id);
            CREATE INDEX IF NOT EXISTS idx_pessoas_perfis      ON pessoas(perfis);
            CREATE INDEX IF NOT EXISTS idx_saldo_conta         ON saldos_snapshot(conta_id);
        """)


def checkpoint_wal(cliente_id: str):
    """Consolida WAL antes do Drive sincronizar — evita arquivos incompletos."""
    with conn_cliente(cliente_id) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
