# sync.py
import json
from datetime import datetime, timedelta
from database import conn_cliente, checkpoint_wal
from excel_export import (
    exportar_saldos_mensais,
    exportar_pessoas,
    exportar_contas_receber,
    exportar_contas_pagar,
    exportar_contas_financeiras,
    exportar_categorias,
    exportar_saldos_snapshot,
)


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

    exportar_pessoas(cliente_id, registros)
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
        (r.get("categorias") or [{}])[0].get("id"),
        (r.get("categorias") or [{}])[0].get("nome"),
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
            categoria_id, categoria_nome,
            centros_custo, payload_raw, sincronizado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            status          = excluded.status,
            total           = excluded.total,
            pago            = excluded.pago,
            nao_pago        = excluded.nao_pago,
            data_alteracao  = excluded.data_alteracao,
            categoria_id    = excluded.categoria_id,
            categoria_nome  = excluded.categoria_nome,
            centros_custo   = excluded.centros_custo,
            payload_raw     = excluded.payload_raw,
            sincronizado_em = datetime('now')
        """, rows)

    exportar_contas_receber(cliente_id, registros)
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
        (r.get("categorias") or [{}])[0].get("id"),
        (r.get("categorias") or [{}])[0].get("nome"),
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
            categoria_id, categoria_nome,
            centros_custo, payload_raw, sincronizado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            status          = excluded.status,
            total           = excluded.total,
            pago            = excluded.pago,
            nao_pago        = excluded.nao_pago,
            data_alteracao  = excluded.data_alteracao,
            categoria_id    = excluded.categoria_id,
            categoria_nome  = excluded.categoria_nome,
            centros_custo   = excluded.centros_custo,
            payload_raw     = excluded.payload_raw,
            sincronizado_em = datetime('now')
        """, rows)

    exportar_contas_pagar(cliente_id, registros)
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

    exportar_contas_financeiras(cliente_id, registros)
    return len(rows)


# ─── Saldos ───────────────────────────────────────────────────────────────────

# Buffer temporário para acumular saldos do ciclo atual antes de exportar
_saldos_ciclo: dict[str, list] = {}


def salvar_saldo_snapshot(cliente_id: str, conta_id: str, conta_nome: str, saldo: float):
    """Registra saldo atual com timestamp — constrói histórico ao longo do tempo."""
    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            INSERT INTO saldos_snapshot (conta_id, conta_nome, saldo_atual, capturado_em)
            VALUES (?, ?, ?, datetime('now'))
        """, (conta_id, conta_nome, saldo))

    # Acumula para exportar tudo de uma vez no finalizar_db_cliente
    _saldos_ciclo.setdefault(cliente_id, []).append({
        "conta_id":   conta_id,
        "conta_nome": conta_nome,
        "saldo_atual": saldo,
    })


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




# ─── Saldos Mensais Calculados ────────────────────────────────────────────────

def calcular_saldos_mensais(cliente_id: str):
    """
    Gera tabela saldos_mensais com saldo final de cada mês.
    Parte do saldo atual e anda para trás subtraindo entradas e somando saídas.
    Usa data_vencimento para classificar o mês do movimento.
    Considera apenas status RECEBIDO e RECEBIDO_PARCIAL (campo pago).
    """
    from collections import defaultdict
    import sqlite3

    STATUS_VALIDOS = {"RECEBIDO", "RECEBIDO_PARCIAL"}

    with conn_cliente(cliente_id) as conn:
        conn.row_factory = sqlite3.Row

        # Pega o saldo atual mais recente de cada conta e soma tudo
        saldo_atual_total = conn.execute("""
            SELECT COALESCE(SUM(s.saldo_atual), 0) as total
            FROM saldos_snapshot s
            INNER JOIN (
                SELECT conta_id, MAX(capturado_em) as ult
                FROM saldos_snapshot
                GROUP BY conta_id
            ) u ON s.conta_id = u.conta_id AND s.capturado_em = u.ult
        """).fetchone()["total"]

        # Data do snapshot mais recente
        data_snapshot = conn.execute("""
            SELECT MAX(capturado_em) as ult FROM saldos_snapshot
        """).fetchone()["ult"]

        if not data_snapshot:
            print("  [saldos_mensais] sem snapshot de saldo, pulando")
            return

        # Mês do snapshot (YYYY-MM)
        mes_atual = data_snapshot[:7]

        # Entradas por mês (contas_receber pagas)
        entradas_rows = conn.execute("""
            SELECT strftime('%Y-%m', data_vencimento) as mes, SUM(pago) as valor
            FROM contas_receber
            WHERE status IN ('RECEBIDO', 'RECEBIDO_PARCIAL')
              AND pago > 0
              AND data_vencimento IS NOT NULL
            GROUP BY mes
        """).fetchall()

        # Saídas por mês (contas_pagar pagas)
        saidas_rows = conn.execute("""
            SELECT strftime('%Y-%m', data_vencimento) as mes, SUM(pago) as valor
            FROM contas_pagar
            WHERE status IN ('RECEBIDO', 'RECEBIDO_PARCIAL')
              AND pago > 0
              AND data_vencimento IS NOT NULL
            GROUP BY mes
        """).fetchall()

    entradas = defaultdict(float)
    saidas   = defaultdict(float)

    for r in entradas_rows:
        entradas[r["mes"]] = round(r["valor"] or 0, 2)
    for r in saidas_rows:
        saidas[r["mes"]] = round(r["valor"] or 0, 2)

    # Todos os meses presentes
    todos_meses = sorted(set(list(entradas.keys()) + list(saidas.keys())), reverse=True)

    if not todos_meses:
        print("  [saldos_mensais] sem movimentos, pulando")
        return

    # Calcula saldos andando para trás a partir do mês atual
    saldos = {}
    saldo = round(saldo_atual_total, 2)

    # Meses do mais recente para o mais antigo
    for mes in todos_meses:
        if mes > mes_atual:
            # Meses futuros: ignora (sem saldo real)
            continue
        if mes == mes_atual:
            saldos[mes] = saldo
        else:
            # Saldo do mês = saldo do mês seguinte - entradas do mês seguinte + saídas do mês seguinte
            prox = _mes_seguinte(mes)
            saldo_prox = saldos.get(prox)
            if saldo_prox is None:
                # Pula meses sem movimento entre o atual e este
                saldo_prox = saldo
            ent_prox = entradas.get(prox, 0)
            sai_prox = saidas.get(prox, 0)
            saldo = round(saldo_prox - ent_prox + sai_prox, 2)
            saldos[mes] = saldo

    # Salva na tabela
    rows = [
        (mes, entradas.get(mes, 0), saidas.get(mes, 0), saldos[mes])
        for mes in saldos
    ]

    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saldos_mensais (
                mes         TEXT PRIMARY KEY,
                entradas    REAL DEFAULT 0,
                saidas      REAL DEFAULT 0,
                saldo_final REAL,
                calculado_em TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("DELETE FROM saldos_mensais")
        conn.executemany("""
            INSERT INTO saldos_mensais (mes, entradas, saidas, saldo_final, calculado_em)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, rows)

    print(f"  [saldos_mensais] {len(rows)} meses calculados | saldo atual: R$ {saldo_atual_total:,.2f}")

    exportar_saldos_mensais(cliente_id, [{'mes': r[0], 'entradas': r[1], 'saidas': r[2], 'saldo_final': r[3]} for r in rows])


def _mes_seguinte(mes: str) -> str:
    """Retorna o mês seguinte no formato YYYY-MM."""
    ano, m = int(mes[:4]), int(mes[5:7])
    m += 1
    if m > 12:
        m = 1
        ano += 1
    return f"{ano:04d}-{m:02d}"

# ─── Finalização ──────────────────────────────────────────────────────────────

def finalizar_db_cliente(cliente_id: str):
    """Consolida WAL e exporta saldos snapshot acumulados do ciclo."""
    checkpoint_wal(cliente_id)

    saldos = _saldos_ciclo.pop(cliente_id, [])
    if saldos:
        exportar_saldos_snapshot(cliente_id, saldos)

    calcular_saldos_mensais(cliente_id)


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

        conn.execute("""
            UPDATE categorias 
            SET categoria_pai_nome = (
                SELECT p.nome 
                FROM categorias p 
                WHERE p.id = categorias.categoria_pai
            )
            WHERE categoria_pai IS NOT NULL
        """)

    exportar_categorias(cliente_id, registros)
    return len(rows)
