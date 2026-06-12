# sync.py
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from database import conn_cliente, checkpoint_wal
from excel_export import (
    exportar_pessoas,
    exportar_contas_receber,
    exportar_contas_pagar,
    exportar_contas_financeiras,
    exportar_categorias,
    exportar_saldos_snapshot,
    exportar_saldos_mensais,
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


# ─── Pessoas ──────────────────────────────────────────────────────────────────

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
                nome            = excluded.nome,
                documento       = excluded.documento,
                tipo_pessoa     = excluded.tipo_pessoa,
                perfis          = excluded.perfis,
                email           = excluded.email,
                telefone        = excluded.telefone,
                ativo           = excluded.ativo,
                data_alteracao  = excluded.data_alteracao,
                payload_raw     = excluded.payload_raw,
                sincronizado_em = datetime('now')
        """, rows)

    exportar_pessoas(cliente_id, registros)
    return len(rows)


# ─── Contas a Receber ─────────────────────────────────────────────────────────

def salvar_contas_receber(cliente_id: str, registros: list,
                          conta_financeira_id: str = None,
                          conta_financeira_nome: str = None) -> int:
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
        _json(r.get("centros_de_custo") or r.get("centros_custo")),
        conta_financeira_id,
        conta_financeira_nome,
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contas_receber (
                id                    TEXT PRIMARY KEY,
                descricao             TEXT,
                data_vencimento       TEXT,
                data_competencia      TEXT,
                data_criacao          TEXT,
                data_alteracao        TEXT,
                status                TEXT,
                total                 REAL,
                pago                  REAL,
                nao_pago              REAL,
                cliente_id            TEXT,
                cliente_nome          TEXT,
                categoria_id          TEXT,
                categoria_nome        TEXT,
                centros_custo         TEXT,
                conta_financeira_id   TEXT,
                conta_financeira_nome TEXT,
                payload_raw           TEXT,
                sincronizado_em       TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.executemany("""
            INSERT INTO contas_receber (
                id, descricao, data_vencimento, data_competencia,
                data_criacao, data_alteracao, status,
                total, pago, nao_pago,
                cliente_id, cliente_nome,
                categoria_id, categoria_nome,
                centros_custo,
                conta_financeira_id, conta_financeira_nome,
                payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                status                = excluded.status,
                total                 = excluded.total,
                pago                  = excluded.pago,
                nao_pago              = excluded.nao_pago,
                data_alteracao        = excluded.data_alteracao,
                categoria_id          = excluded.categoria_id,
                categoria_nome        = excluded.categoria_nome,
                centros_custo         = excluded.centros_custo,
                conta_financeira_id   = COALESCE(excluded.conta_financeira_id, conta_financeira_id),
                conta_financeira_nome = COALESCE(excluded.conta_financeira_nome, conta_financeira_nome),
                payload_raw           = excluded.payload_raw,
                sincronizado_em       = datetime('now')
        """, rows)

    _receber_ciclo.setdefault(cliente_id, []).extend(
        {**r, "_cfi": conta_financeira_id, "_cfn": conta_financeira_nome}
        for r in registros
    )
    return len(rows)


# ─── Contas a Pagar ───────────────────────────────────────────────────────────

def salvar_contas_pagar(cliente_id: str, registros: list,
                        conta_financeira_id: str = None,
                        conta_financeira_nome: str = None) -> int:
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
        _json(r.get("centros_de_custo") or r.get("centros_custo")),
        conta_financeira_id,
        conta_financeira_nome,
        _json(r),
    ) for r in registros]

    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contas_pagar (
                id                    TEXT PRIMARY KEY,
                descricao             TEXT,
                data_vencimento       TEXT,
                data_competencia      TEXT,
                data_criacao          TEXT,
                data_alteracao        TEXT,
                status                TEXT,
                total                 REAL,
                pago                  REAL,
                nao_pago              REAL,
                fornecedor_id         TEXT,
                fornecedor_nome       TEXT,
                categoria_id          TEXT,
                categoria_nome        TEXT,
                centros_custo         TEXT,
                conta_financeira_id   TEXT,
                conta_financeira_nome TEXT,
                payload_raw           TEXT,
                sincronizado_em       TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.executemany("""
            INSERT INTO contas_pagar (
                id, descricao, data_vencimento, data_competencia,
                data_criacao, data_alteracao, status,
                total, pago, nao_pago,
                fornecedor_id, fornecedor_nome,
                categoria_id, categoria_nome,
                centros_custo,
                conta_financeira_id, conta_financeira_nome,
                payload_raw, sincronizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                status                = excluded.status,
                total                 = excluded.total,
                pago                  = excluded.pago,
                nao_pago              = excluded.nao_pago,
                data_alteracao        = excluded.data_alteracao,
                categoria_id          = excluded.categoria_id,
                categoria_nome        = excluded.categoria_nome,
                centros_custo         = excluded.centros_custo,
                conta_financeira_id   = COALESCE(excluded.conta_financeira_id, conta_financeira_id),
                conta_financeira_nome = COALESCE(excluded.conta_financeira_nome, conta_financeira_nome),
                payload_raw           = excluded.payload_raw,
                sincronizado_em       = datetime('now')
        """, rows)

    _pagar_ciclo.setdefault(cliente_id, []).extend(
        {**r, "_cfi": conta_financeira_id, "_cfn": conta_financeira_nome}
        for r in registros
    )
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

_saldos_ciclo:   dict[str, list] = {}
_receber_ciclo:  dict[str, list] = {}
_pagar_ciclo:    dict[str, list] = {}


def salvar_saldo_snapshot(cliente_id: str, conta_id: str, conta_nome: str, saldo: float):
    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            INSERT INTO saldos_snapshot (conta_id, conta_nome, saldo_atual, capturado_em)
            VALUES (?, ?, ?, datetime('now'))
        """, (conta_id, conta_nome, saldo))

    _saldos_ciclo.setdefault(cliente_id, []).append({
        "conta_id":    conta_id,
        "conta_nome":  conta_nome,
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


# ─── Categorias ───────────────────────────────────────────────────────────────

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
                SELECT p.nome FROM categorias p WHERE p.id = categorias.categoria_pai
            )
            WHERE categoria_pai IS NOT NULL
        """)

    exportar_categorias(cliente_id, registros)
    return len(rows)


# ─── Saldos Mensais por Conta ─────────────────────────────────────────────────

def _mes_seguinte(mes: str) -> str:
    ano, m = int(mes[:4]), int(mes[5:7])
    m += 1
    if m > 12:
        m, ano = 1, ano + 1
    return f"{ano:04d}-{m:02d}"


def calcular_saldos_mensais(cliente_id: str):
    """
    Gera saldos_mensais com saldo final por conta e por mês.
    Parte do saldo atual de cada conta e anda para trás usando
    entradas (contas_receber) e saídas (contas_pagar) filtradas
    por conta_financeira_id e status RECEBIDO/RECEBIDO_PARCIAL.
    """
    with conn_cliente(cliente_id) as conn:
        conn.row_factory = sqlite3.Row

        # Saldo atual por conta (snapshot mais recente)
        snapshots = conn.execute("""
            SELECT s.conta_id, s.conta_nome, s.saldo_atual
            FROM saldos_snapshot s
            INNER JOIN (
                SELECT conta_id, MAX(capturado_em) as ult
                FROM saldos_snapshot GROUP BY conta_id
            ) u ON s.conta_id = u.conta_id AND s.capturado_em = u.ult
        """).fetchall()

        if not snapshots:
            print("  [saldos_mensais] sem snapshots, pulando")
            return

        data_snapshot = conn.execute(
            "SELECT MAX(capturado_em) as ult FROM saldos_snapshot"
        ).fetchone()["ult"]
        mes_atual = data_snapshot[:7]

        # Entradas por conta e mês
        entradas_rows = conn.execute("""
            SELECT conta_financeira_id, strftime('%Y-%m', data_vencimento) as mes,
                   SUM(pago) as valor
            FROM contas_receber
            WHERE status IN ('RECEBIDO', 'RECEBIDO_PARCIAL')
              AND pago > 0 AND data_vencimento IS NOT NULL
              AND conta_financeira_id IS NOT NULL
            GROUP BY conta_financeira_id, mes
        """).fetchall()

        # Saídas por conta e mês
        saidas_rows = conn.execute("""
            SELECT conta_financeira_id, strftime('%Y-%m', data_vencimento) as mes,
                   SUM(pago) as valor
            FROM contas_pagar
            WHERE status IN ('RECEBIDO', 'RECEBIDO_PARCIAL')
              AND pago > 0 AND data_vencimento IS NOT NULL
              AND conta_financeira_id IS NOT NULL
            GROUP BY conta_financeira_id, mes
        """).fetchall()

    # Indexa por conta → mes → valor
    entradas = defaultdict(lambda: defaultdict(float))
    saidas   = defaultdict(lambda: defaultdict(float))

    for r in entradas_rows:
        entradas[r["conta_financeira_id"]][r["mes"]] = round(r["valor"] or 0, 2)
    for r in saidas_rows:
        saidas[r["conta_financeira_id"]][r["mes"]] = round(r["valor"] or 0, 2)

    todas_contas = {s["conta_id"]: s["conta_nome"] for s in snapshots}
    saldo_atual  = {s["conta_id"]: round(s["saldo_atual"], 2) for s in snapshots}

    todos_meses_por_conta = {}
    for cid in todas_contas:
        meses = sorted(
            set(list(entradas[cid].keys()) + list(saidas[cid].keys())),
            reverse=True
        )
        todos_meses_por_conta[cid] = meses

    # Calcula saldo para trás por conta
    resultado = []
    for cid, cnome in todas_contas.items():
        saldo = saldo_atual.get(cid, 0.0)
        meses = todos_meses_por_conta.get(cid, [])
        saldos_conta = {}

        for mes in meses:
            if mes > mes_atual:
                continue
            if mes == mes_atual:
                saldos_conta[mes] = saldo
            else:
                prox = _mes_seguinte(mes)
                saldo_prox = saldos_conta.get(prox, saldo)
                saldo = round(saldo_prox - entradas[cid].get(prox, 0) + saidas[cid].get(prox, 0), 2)
                saldos_conta[mes] = saldo

        for mes, sf in saldos_conta.items():
            resultado.append((
                cid, cnome, mes,
                entradas[cid].get(mes, 0.0),
                saidas[cid].get(mes, 0.0),
                sf,
            ))

    if not resultado:
        print("  [saldos_mensais] sem movimentos por conta, pulando")
        return

    with conn_cliente(cliente_id) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saldos_mensais (
                conta_id            TEXT NOT NULL,
                conta_nome          TEXT,
                mes                 TEXT NOT NULL,
                entradas            REAL DEFAULT 0,
                saidas              REAL DEFAULT 0,
                saldo_final         REAL,
                calculado_em        TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (conta_id, mes)
            )
        """)
        conn.execute("DELETE FROM saldos_mensais")
        conn.executemany("""
            INSERT INTO saldos_mensais
                (conta_id, conta_nome, mes, entradas, saidas, saldo_final, calculado_em)
            VALUES (?,?,?,?,?,?,datetime('now'))
        """, resultado)

    print(f"  [saldos_mensais] {len(resultado)} linhas ({len(todas_contas)} contas)")

    exportar_saldos_mensais(cliente_id, [
        {"conta_id": r[0], "conta_nome": r[1], "mes": r[2],
         "entradas": r[3], "saidas": r[4], "saldo_final": r[5]}
        for r in resultado
    ])


# ─── Finalização ──────────────────────────────────────────────────────────────

def finalizar_db_cliente(cliente_id: str):
    checkpoint_wal(cliente_id)

    saldos = _saldos_ciclo.pop(cliente_id, [])
    if saldos:
        exportar_saldos_snapshot(cliente_id, saldos)

    receber = _receber_ciclo.pop(cliente_id, [])
    if receber:
        exportar_contas_receber(cliente_id, receber)

    pagar = _pagar_ciclo.pop(cliente_id, [])
    if pagar:
        exportar_contas_pagar(cliente_id, pagar)

    calcular_saldos_mensais(cliente_id)
