# excel_export.py
"""
Exporta cada tabela do banco do cliente para um arquivo .xlsx separado.
Chamado automaticamente após cada salvar_* no sync.py.

Arquivos gerados em: DRIVE_ROOT/<cliente_id>/
    pessoas.xlsx
    contas_receber.xlsx
    contas_pagar.xlsx
    contas_financeiras.xlsx
    categorias.xlsx
    saldos_snapshot.xlsx
"""

import os
import json
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

import config

# ─── Estilos ──────────────────────────────────────────────────────────────────

_FONTE_DADOS    = Font(name="Arial", size=10)
_FONTE_RODAPE   = Font(name="Arial", italic=True, size=9, color="888888")
_ALIGN_LEFT     = Alignment(horizontal="left", vertical="center")
_BORDA_FINA     = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"),  bottom=Side(style="thin"),
)
_ESTILO_TABELA  = TableStyleInfo(
    name="TableStyleMedium9",   # azul — igual ao padrão das outras abas
    showFirstColumn=False,
    showLastColumn=False,
    showRowStripes=True,
    showColumnStripes=False,
)

_tabela_counter: dict[str, int] = {}   # garante nomes únicos por sessão


def _pasta_cliente(cliente_id: str) -> str:
    pasta = os.path.join(config.DRIVE_ROOT, cliente_id)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _nome_tabela(prefixo: str) -> str:
    """Gera nome único de tabela Excel (sem espaços, sem colisões)."""
    _tabela_counter[prefixo] = _tabela_counter.get(prefixo, 0) + 1
    return f"Tbl_{prefixo}"


def _criar_planilha(cliente_id: str, nome_aba: str, colunas: list[str],
                    linhas: list, nome_arquivo: str, prefixo_tabela: str):
    """
    Cria um .xlsx com:
      - aba renomeada
      - cabeçalho congelado
      - objeto Table do Excel (permite filtros, ordenação, formatação nativa)
      - largura automática das colunas
      - rodapé com timestamp
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nome_aba
    ws.freeze_panes = "A2"

    # Dados
    ws.append(colunas)
    for linha in linhas:
        ws.append(list(linha))

    # Estilo das células de dados
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.font      = _FONTE_DADOS
            cell.alignment = _ALIGN_LEFT

    # Objeto Table — isso é o que faz o Excel reconhecer como tabela de verdade
    ultima_col  = get_column_letter(len(colunas))
    ultima_linha = 1 + len(linhas)
    ref = f"A1:{ultima_col}{ultima_linha}"
    tabela = Table(displayName=_nome_tabela(prefixo_tabela), ref=ref)
    tabela.tableStyleInfo = _ESTILO_TABELA
    ws.add_table(tabela)

    # Largura automática
    for col in ws.columns:
        letra = get_column_letter(col[0].column)
        max_len = max(
            (len(str(c.value)) if c.value is not None else 0 for c in col),
            default=10,
        )
        ws.column_dimensions[letra].width = min(max(max_len + 2, 10), 55)

    # Rodapé fora da tabela
    rodape_row = ultima_linha + 2
    ws.cell(row=rodape_row, column=1).value = \
        f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws.cell(row=rodape_row, column=1).font = _FONTE_RODAPE

    caminho = os.path.join(_pasta_cliente(cliente_id), nome_arquivo)
    wb.save(caminho)
    print(f"  [xlsx] {nome_arquivo} → {len(linhas)} linhas")


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTAÇÕES POR TABELA
# ═══════════════════════════════════════════════════════════════════════════════

def exportar_pessoas(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["id", "nome", "documento", "tipo_pessoa", "perfis",
               "email", "telefone", "ativo", "data_criacao", "data_alteracao"]
    linhas = [(
        r.get("id"),
        r.get("nome"),
        r.get("documento"),
        r.get("tipo_pessoa"),
        ", ".join(r["perfis"]) if isinstance(r.get("perfis"), list) else r.get("perfis"),
        r.get("email"),
        r.get("telefone"),
        "Sim" if r.get("ativo") else "Não",
        r.get("data_criacao"),
        r.get("data_alteracao"),
    ) for r in registros]
    _criar_planilha(cliente_id, "Pessoas", colunas, linhas, "pessoas.xlsx", "Pessoas")


def exportar_contas_receber(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["id", "descricao", "data_vencimento", "data_competencia",
               "data_criacao", "data_alteracao", "status",
               "total", "pago", "nao_pago",
               "cliente_id", "cliente_nome",
               "categoria_id", "categoria_nome", "centros_custo"]

    def _n(obj, *keys):
        for k in keys:
            if not isinstance(obj, dict): return None
            obj = obj.get(k)
        return obj

    linhas = [(
        r.get("id"), r.get("descricao"),
        r.get("data_vencimento"), r.get("data_competencia"),
        r.get("data_criacao"), r.get("data_alteracao"),
        r.get("status_traduzido") or r.get("status"),
        r.get("total"), r.get("pago"), r.get("nao_pago"),
        _n(r, "cliente", "id"), _n(r, "cliente", "nome"),
        (r.get("categorias") or [{}])[0].get("id"),
        (r.get("categorias") or [{}])[0].get("nome"),
        json.dumps(r.get("centros_custo"), ensure_ascii=False) if r.get("centros_custo") else None,
    ) for r in registros]
    _criar_planilha(cliente_id, "Contas a Receber", colunas, linhas,
                    "contas_receber.xlsx", "ContasReceber")


def exportar_contas_pagar(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["id", "descricao", "data_vencimento", "data_competencia",
               "data_criacao", "data_alteracao", "status",
               "total", "pago", "nao_pago",
               "fornecedor_id", "fornecedor_nome",
               "categoria_id", "categoria_nome", "centros_custo"]

    def _n(obj, *keys):
        for k in keys:
            if not isinstance(obj, dict): return None
            obj = obj.get(k)
        return obj

    linhas = [(
        r.get("id"), r.get("descricao"),
        r.get("data_vencimento"), r.get("data_competencia"),
        r.get("data_criacao"), r.get("data_alteracao"),
        r.get("status_traduzido") or r.get("status"),
        r.get("total"), r.get("pago"), r.get("nao_pago"),
        _n(r, "fornecedor", "id"), _n(r, "fornecedor", "nome"),
        (r.get("categorias") or [{}])[0].get("id"),
        (r.get("categorias") or [{}])[0].get("nome"),
        json.dumps(r.get("centros_custo"), ensure_ascii=False) if r.get("centros_custo") else None,
    ) for r in registros]
    _criar_planilha(cliente_id, "Contas a Pagar", colunas, linhas,
                    "contas_pagar.xlsx", "ContasPagar")


def exportar_contas_financeiras(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["id", "nome", "banco", "tipo", "agencia", "numero", "ativo", "conta_padrao"]
    linhas = [(
        r.get("id"), r.get("nome"), r.get("banco"), r.get("tipo"),
        r.get("agencia"), r.get("numero"),
        "Sim" if r.get("ativo") else "Não",
        "Sim" if r.get("conta_padrao") else "Não",
    ) for r in registros]
    _criar_planilha(cliente_id, "Contas Financeiras", colunas, linhas,
                    "contas_financeiras.xlsx", "ContasFinanceiras")


def exportar_categorias(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["id", "nome", "tipo", "categoria_pai", "entrada_dre", "considera_custo_dre"]
    linhas = [(
        r.get("id"), r.get("nome"), r.get("tipo"),
        r.get("categoria_pai"), r.get("entrada_dre"),
        "Sim" if r.get("considera_custo_dre") else "Não",
    ) for r in registros]
    _criar_planilha(cliente_id, "Categorias", colunas, linhas,
                    "categorias.xlsx", "Categorias")


def exportar_saldos_snapshot(cliente_id: str, snapshots: list):
    """Acumulativo — cada sync adiciona linhas novas preservando o histórico."""
    if not snapshots:
        return

    colunas    = ["conta_id", "conta_nome", "saldo_atual", "capturado_em"]
    agora      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    novas_linhas = [(
        s.get("conta_id") or s.get("id"),
        s.get("conta_nome") or s.get("nome"),
        s.get("saldo_atual"),
        agora,
    ) for s in snapshots]

    caminho = os.path.join(_pasta_cliente(cliente_id), "saldos_snapshot.xlsx")

    if os.path.exists(caminho):
        # Lê linhas existentes, reconstrói tudo com a tabela atualizada
        wb_old = openpyxl.load_workbook(caminho, data_only=True)
        ws_old = wb_old.active
        linhas_existentes = []
        for row in ws_old.iter_rows(min_row=2, values_only=True):
            # Ignora linhas de rodapé (primeira célula começa com "Atualizado")
            if row[0] and str(row[0]).startswith("Atualizado"):
                break
            if any(v is not None for v in row):
                linhas_existentes.append(row)
        todas_linhas = linhas_existentes + novas_linhas
    else:
        todas_linhas = novas_linhas

    _criar_planilha(cliente_id, "Saldos Snapshot", colunas, todas_linhas,
                    "saldos_snapshot.xlsx", "SaldosSnapshot")
    print(f"  [xlsx] saldos_snapshot.xlsx → +{len(novas_linhas)} novas (total: {len(todas_linhas)})")


def exportar_saldos_mensais(cliente_id: str, registros: list):
    if not registros:
        return
    colunas = ["mes", "entradas", "saidas", "saldo_final"]
    linhas = [(r["mes"], r["entradas"], r["saidas"], r["saldo_final"]) for r in registros]
    _criar_planilha(cliente_id, "Saldos Mensais", colunas, linhas,
                    "saldos_mensais.xlsx", "SaldosMensais")
