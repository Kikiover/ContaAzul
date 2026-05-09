# main.py
import sys
import time
import traceback
from datetime import datetime, timedelta

from config import DELAY_ENTRE_CLIENTES, ANOS_HISTORICO
from database import (
    init_controle, init_db_cliente,
    get_clientes_ativos, get_cliente,
    atualizar_ultima_sync, registrar_log,
)
from auth import get_token_valido
from api_client import ContaAzulAPI
from sync import (
    salvar_pessoas,
    salvar_contas_receber,
    salvar_contas_pagar,
    salvar_categorias,
    salvar_contas_financeiras,
    salvar_saldo_snapshot,
    salvar_saldos_iniciais,
    finalizar_db_cliente,
)


def _data_alteracao_incremental(ultima_sync: str, recuo_dias: int = 3) -> str | None:
    """
    Retorna timestamp para filtro incremental.
    Recua `recuo_dias` para capturar alterações retroativas.
    Se nunca sincronizou, retorna None (sync completa).
    """
    if not ultima_sync:
        return None
    dt = datetime.fromisoformat(ultima_sync) - timedelta(days=recuo_dias)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _sync_pessoas(api: ContaAzulAPI, cliente_id: str, ultima_sync: str) -> int:
    data_alt = _data_alteracao_incremental(ultima_sync)
    # Puxar clientes e fornecedores em uma chamada só (sem filtro de tipo)
    registros = api.get_pessoas(data_alteracao_de=data_alt)
    return salvar_pessoas(cliente_id, registros)


def _sync_contas_receber(api: ContaAzulAPI, cliente_id: str, ultima_sync: str) -> int:
    data_alt = _data_alteracao_incremental(ultima_sync)
    registros = api.get_contas_receber(data_alteracao_de=data_alt)
    return salvar_contas_receber(cliente_id, registros)


def _sync_contas_pagar(api: ContaAzulAPI, cliente_id: str, ultima_sync: str) -> int:
    data_alt = _data_alteracao_incremental(ultima_sync)
    registros = api.get_contas_pagar(data_alteracao_de=data_alt)
    return salvar_contas_pagar(cliente_id, registros)


def _sync_contas_financeiras(api: ContaAzulAPI, cliente_id: str) -> tuple[int, list]:
    registros = api.get_contas_financeiras()
    total = salvar_contas_financeiras(cliente_id, registros)
    return total, registros


def _sync_saldos_atuais(api: ContaAzulAPI, cliente_id: str, contas: list) -> int:
    count = 0
    for conta in contas:
        try:
            saldo = api.get_saldo_atual(conta["id"])
            salvar_saldo_snapshot(cliente_id, conta["id"], conta.get("nome"), saldo)
            count += 1
        except Exception as e:
            print(f"  [aviso] saldo da conta {conta.get('nome')}: {e}")
    return count


def _sync_categorias(api: ContaAzulAPI, cliente_id: str) -> int:
    registros = api.get_categorias()
    return salvar_categorias(cliente_id, registros)

# ═══════════════════════════════════════════════════════════════════════════════
# SYNC DE UM CLIENTE
# ═══════════════════════════════════════════════════════════════════════════════

ETAPAS = [
    ("pessoas",    "Pessoas (clientes/fornecedores)"),
    ("receber",    "Contas a Receber"),
    ("pagar",      "Contas a Pagar"),
    ("contas",     "Contas Financeiras + Saldos Atuais"),
    ("saldo_ini",  "Saldos Iniciais"),
]


def sincronizar_cliente(cliente, callback=None) -> dict:
    """
    Executa sync completa de um cliente.
    callback(etapa, status, detalhe): função opcional para atualizar UI (Tkinter).
    """
    cid  = cliente["id"]
    nome = cliente["nome"]
    res  = {e[0]: 0 for e in ETAPAS}
    res["erros"] = []

    def log(msg):
        print(f"  {msg}")
        if callback:
            callback(msg)

    print(f"\n{'─'*56}")
    print(f"  {nome}  ({cid})")
    print(f"{'─'*56}")

    init_db_cliente(cid)

    try:
        token = get_token_valido(cliente)
    except Exception as e:
        msg = f"Falha de autenticação: {e}"
        log(f"[ERRO] {msg}")
        registrar_log(cid, "auth", "erro", mensagem=msg)
        res["erros"].append(msg)
        return res

    api = ContaAzulAPI(token, cid)

    # ── Pessoas ───────────────────────────────────────────────────────────────
    try:
        log("[→] Pessoas...")
        total = _sync_pessoas(api, cid, cliente["ultima_sync_pessoas"])
        atualizar_ultima_sync(cid, "pessoas", datetime.now().isoformat())
        registrar_log(cid, "pessoas", "ok", registros=total)
        res["pessoas"] = total
        log(f"[✓] Pessoas: {total}")
    except Exception as e:
        log(f"[✗] Pessoas: {e}")
        registrar_log(cid, "pessoas", "erro", mensagem=traceback.format_exc())
        res["erros"].append(f"pessoas: {e}")

    # ── Contas a Receber ──────────────────────────────────────────────────────
    try:
        log("[→] Contas a Receber...")
        total = _sync_contas_receber(api, cid, cliente["ultima_sync_receber"])
        atualizar_ultima_sync(cid, "receber", datetime.now().isoformat())
        registrar_log(cid, "receber", "ok", registros=total)
        res["receber"] = total
        log(f"[✓] Contas a Receber: {total}")
    except Exception as e:
        log(f"[✗] Contas a Receber: {e}")
        registrar_log(cid, "receber", "erro", mensagem=traceback.format_exc())
        res["erros"].append(f"receber: {e}")

    # ── Contas a Pagar ────────────────────────────────────────────────────────
    try:
        log("[→] Contas a Pagar...")
        total = _sync_contas_pagar(api, cid, cliente["ultima_sync_pagar"])
        atualizar_ultima_sync(cid, "pagar", datetime.now().isoformat())
        registrar_log(cid, "pagar", "ok", registros=total)
        res["pagar"] = total
        log(f"[✓] Contas a Pagar: {total}")
    except Exception as e:
        log(f"[✗] Contas a Pagar: {e}")
        registrar_log(cid, "pagar", "erro", mensagem=traceback.format_exc())
        res["erros"].append(f"pagar: {e}")

    # ── Contas Financeiras + Saldos Atuais ────────────────────────────────────
    try:
        log("[→] Contas Financeiras...")
        total_contas, contas = _sync_contas_financeiras(api, cid)
        atualizar_ultima_sync(cid, "contas", datetime.now().isoformat())
        registrar_log(cid, "contas", "ok", registros=total_contas)
        res["contas"] = total_contas
        log(f"[✓] Contas Financeiras: {total_contas}")

        log("[→] Saldos Atuais...")
        total_saldos = _sync_saldos_atuais(api, cid, contas)
        atualizar_ultima_sync(cid, "saldos", datetime.now().isoformat())
        registrar_log(cid, "saldos", "ok", registros=total_saldos)
        res["saldos"] = total_saldos
        log(f"[✓] Saldos Atuais: {total_saldos} contas")
    except Exception as e:
        log(f"[✗] Contas/Saldos: {e}")
        registrar_log(cid, "contas", "erro", mensagem=traceback.format_exc())
        res["erros"].append(f"contas: {e}")


        # ── Categorias ────────────────────────────────────────────────────────────
    try:
        log("[→] Categorias...")
        total = _sync_categorias(api, cid)
        atualizar_ultima_sync(cid, "categorias", datetime.now().isoformat())
        registrar_log(cid, "categorias", "ok", registros=total)
        res["categorias"] = total
        log(f"[✓] Categorias: {total}")
    except Exception as e:
        log(f"[✗] Categorias: {e}")
        registrar_log(cid, "categorias", "erro", mensagem=traceback.format_exc())
        res["erros"].append(f"categorias: {e}")



    # Consolida WAL antes do Drive sincronizar
    finalizar_db_cliente(cid)
    return res


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(cliente_id: str = None):
    init_controle()

    if cliente_id:
        c = get_cliente(cliente_id)
        clientes = [c] if c else []
    else:
        clientes = get_clientes_ativos()

    if not clientes:
        print("[MAIN] Nenhum cliente encontrado.")
        return

    print(f"\n[MAIN] {len(clientes)} cliente(s) para sincronizar")
    inicio = datetime.now()
    resumo = []

    for i, cliente in enumerate(clientes, 1):
        print(f"\n[MAIN] {i}/{len(clientes)}")
        res = sincronizar_cliente(cliente)
        resumo.append({"nome": cliente["nome"], **res})
        if i < len(clientes):
            time.sleep(DELAY_ENTRE_CLIENTES)

    dur = int((datetime.now() - inicio).total_seconds())
    print(f"\n{'═'*56}")
    print(f"  Sync concluída em {dur}s")
    print(f"{'═'*56}")
    for r in resumo:
        ok = "✓" if not r["erros"] else "✗"
        print(
            f"  {ok} {r['nome']:<25} "
            f"pessoas:{r.get('pessoas',0):>4} "
            f"receber:{r.get('receber',0):>5} "
            f"pagar:{r.get('pagar',0):>5} "
            f"erros:{len(r['erros'])}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
