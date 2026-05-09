# sync.py
import json
from datetime import datetime, timedelta
from database import conn_cliente, checkpoint_wal


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _nested(obj: dict, *keys, default=None):
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
    return obj

def _json(val) -> str | None:
    return json.dumps(val, ensure_ascii=False) if val else None

def _agora() -> str:
    return datetime.now().isoformat()


# ─── Pessoas (clientes e fornecedores) ───────────────────────────────────────

def salvar_pessoas(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0

    rows = [(
        r.get("id"),
        r.get("nome"),
        r.get("documento"),
        r.get("tipo_pessoa"),
        _json(r.get("perfis")),
        r.get("email"),
        r.get("telefone"),
        1 if r.get("ativo") else 0,
        r.get("data_criacao"),
        r.get("data_alteracao"),
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO pessoas (
                id, nome, documento, tipo_pessoa, perfis,
                email, telefone, ativo, data_criacao, data_alteracao,
                payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                nome           = excluded.nome,
                documento      = excluded.documento,
                tipo_pessoa    = excluded.tipo_pessoa,
                perfis         = excluded.perfis,
                email          = excluded.email,
                telefone       = excluded.telefone,
                ativo          = excluded.ativo,
                data_alteracao = excluded.data_alteracao,
                payload_raw    = excluded.payload_raw,
                sincronizado_em = datetime('now')
        """, rows)
    return len(rows)


# ─── Contas a Receber ─────────────────────────────────────────────────────────

def salvar_contas_receber(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0

    rows = [(
        r.get("id"),
        r.get("descricao"),
        r.get("data_vencimento"),
        r.get("data_competencia"),
        r.get("data_criacao"),
        r.get("data_alteracao"),
        r.get("status_traduzido") or r.get("status"),
        r.get("total"),
        r.get("pago"),
        r.get("nao_pago"),
        _nested(r, "cliente", "id"),
        _nested(r, "cliente", "nome"),
        _json(r.get("categorias")),
        _json(r.get("centros_custo")),
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO contas_receber (
                id, descricao, data_vencimento, data_competencia,
                data_criacao, data_alteracao, status,
                total, pago, nao_pago,
                cliente_id, cliente_nome,
                categorias, centros_custo, payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                status          = excluded.status,
                total           = excluded.total,
                pago            = excluded.pago,
                nao_pago        = excluded.nao_pago,
                data_alteracao  = excluded.data_alteracao,
                categorias      = excluded.categorias,
                centros_custo   = excluded.centros_custo,
                payload_raw     = excluded.payload_raw,
                sincronizado_em = datetime('now')
        """, rows)
    return len(rows)


# ─── Contas a Pagar ───────────────────────────────────────────────────────────

def salvar_contas_pagar(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0

    rows = [(
        r.get("id"),
        r.get("descricao"),
        r.get("data_vencimento"),
        r.get("data_competencia"),
        r.get("data_criacao"),
        r.get("data_alteracao"),
        r.get("status_traduzido") or r.get("status"),
        r.get("total"),
        r.get("pago"),
        r.get("nao_pago"),
        _nested(r, "fornecedor", "id"),
        _nested(r, "fornecedor", "nome"),
        _json(r.get("categorias")),
        _json(r.get("centros_custo")),
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO contas_pagar (
                id, descricao, data_vencimento, data_competencia,
                data_criacao, data_alteracao, status,
                total, pago, nao_pago,
                fornecedor_id, fornecedor_nome,
                categorias, centros_custo, payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                status          = excluded.status,
                total           = excluded.total,
                pago            = excluded.pago,
                nao_pago        = excluded.nao_pago,
                data_alteracao  = excluded.data_alteracao,
                categorias      = excluded.categorias,
                centros_custo   = excluded.centros_custo,
                payload_raw     = excluded.payload_raw,
                sincronizado_em = datetime('now')
        """, rows)
    return len(rows)


# ─── Contas Financeiras ───────────────────────────────────────────────────────

def salvar_contas_financeiras(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0

    rows = [(
        r.get("id"),
        r.get("nome"),
        r.get("banco"),
        r.get("tipo"),
        r.get("agencia"),
        r.get("numero"),
        1 if r.get("ativo") else 0,
        1 if r.get("conta_padrao") else 0,
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO contas_financeiras (
                id, nome, banco, tipo, agencia, numero,
                ativo, conta_padrao, payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                nome            = excluded.nome,
                ativo           = excluded.ativo,
                conta_padrao    = excluded.conta_padrao,
                payload_raw     = excluded.payload_raw,
                sincronizado_em = datetime('now')
        """, rows)
    return len(rows)


# ─── Saldos ───────────────────────────────────────────────────────────────────

def salvar_saldo_snapshot(cliente_id: str, conta_id: str, conta_nome: str, saldo: float):
    """Registra saldo atual com timestamp — constrói histórico ao longo do tempo."""
    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            INSERT INTO saldos_snapshot (conta_id, conta_nome, saldo_atual, capturado_em)
            VALUES (?, ?, ?, datetime('now'))
        """, (conta_id, conta_nome, saldo))


def salvar_saldos_iniciais(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0

    rows = [(
        r.get("id_conta_financeira"),
        r.get("data_competencia"),
        r.get("saldo_inicial"),
        r.get("tipo"),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO saldos_iniciais (
                id_conta_financeira, data_competencia, saldo_inicial, tipo, sincronizado_em
            ) VALUES (?,?,?,?,datetime('now'))
            ON CONFLICT(id_conta_financeira, data_competencia) DO UPDATE SET
                saldo_inicial   = excluded.saldo_inicial,
                tipo            = excluded.tipo,
                sincronizado_em = datetime('now')
        """, rows)
    return len(rows)


# ─── Finalização ──────────────────────────────────────────────────────────────

def finalizar_db_cliente(cliente_id: str):
    """Consolida WAL antes do Drive sincronizar o arquivo."""
    checkpoint_wal(cliente_id)


def salvar_categorias(cliente_id: str, registros: list) -> int:
    if not registros:
        return 0
    rows = [(
        r.get("id"),
        r.get("nome"),
        r.get("tipo"),
        r.get("categoria_pai"),
        r.get("entrada_dre"),
        1 if r.get("considera_custo_dre") else 0,
    ) for r in registros]
    with conn_cliente(cliente_id) as conn:
        conn.executemany("""
            INSERT INTO categorias (
                id, nome, tipo, categoria_pai,
                entrada_dre, considera_custo_dre, sincronizado_em
            ) VALUES (?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                nome                = excluded.nome,
                tipo                = excluded.tipo,
                categoria_pai       = excluded.categoria_pai,
                entrada_dre         = excluded.entrada_dre,
                considera_custo_dre = excluded.considera_custo_dre,
                sincronizado_em     = datetime('now')
        """, rows)
    return len(rows)