# app.py
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
from datetime import datetime

import config
from config import AUTH_URL
from database import init_controle, get_clientes_ativos, get_cliente, cadastrar_cliente, conn_controle
from auth import gerar_url_autorizacao, extrair_code_da_url, trocar_code_por_tokens
from main import sincronizar_cliente

# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS (drive_root persistido em settings.json)
# ═══════════════════════════════════════════════════════════════════════════════

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def carregar_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def salvar_settings(data: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def aplicar_drive_root(novo_path: str):
    """Atualiza DRIVE_ROOT em tempo de execução e cria a pasta."""
    config.DRIVE_ROOT = novo_path
    os.makedirs(novo_path, exist_ok=True)
    s = carregar_settings()
    s["drive_root"] = novo_path
    salvar_settings(s)

# Aplica DRIVE_ROOT salvo ao iniciar
_settings_iniciais = carregar_settings()
if "drive_root" in _settings_iniciais:
    config.DRIVE_ROOT = _settings_iniciais["drive_root"]
    os.makedirs(config.DRIVE_ROOT, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ═══════════════════════════════════════════════════════════════════════════════

CORES = {
    "bg":           "#1e1e2e",
    "surface":      "#2a2a3e",
    "surface2":     "#313145",
    "accent":       "#7c6af7",
    "accent_hover": "#6a58e0",
    "verde":        "#4ade80",
    "vermelho":     "#f87171",
    "amarelo":      "#fbbf24",
    "cinza":        "#6b7280",
    "texto":        "#e2e8f0",
    "texto2":       "#94a3b8",
    "borda":        "#3f3f5a",
    "danger":       "#ef4444",
    "danger_hover": "#dc2626",
}

FONTE       = ("Segoe UI", 10)
FONTE_BOLD  = ("Segoe UI", 10, "bold")
FONTE_TITULO= ("Segoe UI", 13, "bold")
FONTE_SMALL = ("Segoe UI", 9)
FONTE_MONO  = ("Consolas", 9)


def formatar_data(iso: str | None) -> str:
    if not iso:
        return "Nunca"
    try:
        dt = datetime.fromisoformat(iso)
        hoje = datetime.now().date()
        if dt.date() == hoje:
            return f"Hoje {dt.strftime('%H:%M')}"
        if (hoje - dt.date()).days == 1:
            return f"Ontem {dt.strftime('%H:%M')}"
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso[:16]


def ultima_sync_cliente(cliente) -> str | None:
    datas = [
        cliente["ultima_sync_pessoas"],
        cliente["ultima_sync_receber"],
        cliente["ultima_sync_pagar"],
        cliente["ultima_sync_contas"],
        cliente["ultima_sync_saldos"],
    ]
    datas = [d for d in datas if d]
    return max(datas) if datas else None


def status_cliente(cliente) -> tuple[str, str]:
    with conn_controle() as conn:
        ultimo_log = conn.execute("""
            SELECT status FROM sync_log
            WHERE cliente_id = ?
            ORDER BY id DESC LIMIT 1
        """, (cliente["id"],)).fetchone()
    if not ultimo_log:
        return "Não sincronizado", CORES["cinza"]
    if ultimo_log["status"] == "ok":
        return "✓  OK", CORES["verde"]
    if ultimo_log["status"] == "erro":
        return "✗  Erro", CORES["vermelho"]
    return "—", CORES["cinza"]


def _make_btn(parent, texto, comando, bg=None, fg="white", pady=8, padx=16) -> tk.Button:
    return tk.Button(
        parent, text=texto, command=comando,
        font=FONTE_BOLD,
        bg=bg or CORES["accent"], fg=fg,
        activebackground=CORES["accent_hover"], activeforeground="white",
        relief="flat", cursor="hand2",
        pady=pady, padx=padx,
    )


def _make_input(parent, fonte=None) -> tk.Entry:
    e = tk.Entry(
        parent,
        font=fonte or FONTE,
        bg=CORES["surface2"], fg=CORES["texto"],
        insertbackground=CORES["texto"],
        relief="flat", bd=0,
    )
    e.configure(highlightthickness=1,
                highlightbackground=CORES["borda"],
                highlightcolor=CORES["accent"])
    return e


def _centralizar(janela, parent):
    janela.update_idletasks()
    pw = parent.winfo_x() + parent.winfo_width() // 2
    ph = parent.winfo_y() + parent.winfo_height() // 2
    w, h = janela.winfo_width(), janela.winfo_height()
    janela.geometry(f"+{pw - w//2}+{ph - h//2}")


# ═══════════════════════════════════════════════════════════════════════════════
# JANELA: ADICIONAR / RE-AUTENTICAR CLIENTE
# ═══════════════════════════════════════════════════════════════════════════════

class JanelaOAuth(tk.Toplevel):
    """
    Reutilizável para cadastro novo e para re-autenticação.
    modo='novo'   → mostra etapa 1 (nome + id) + etapa 2 (OAuth2)
    modo='reauth' → vai direto para etapa 2, id e nome já fixos
    """
    def __init__(self, parent, on_sucesso=None, modo="novo",
                 id_fixo=None, nome_fixo=None):
        super().__init__(parent)
        self.parent     = parent
        self.on_sucesso = on_sucesso
        self.modo       = modo
        self._id_fixo   = id_fixo
        self._nome_fixo = nome_fixo

        titulo = "Adicionar Cliente" if modo == "novo" else f"Re-autenticar — {nome_fixo}"
        self.title(titulo)
        self.resizable(False, False)
        self.configure(bg=CORES["bg"])
        self.grab_set()

        self.corpo = tk.Frame(self, bg=CORES["bg"], padx=30, pady=24)

        # Header
        header = tk.Frame(self, bg=CORES["accent"], pady=16)
        header.pack(fill="x")
        tk.Label(header, text=titulo, font=FONTE_TITULO,
                 bg=CORES["accent"], fg="white").pack()
        self.corpo.pack(fill="both", expand=True)

        if modo == "novo":
            self._build_etapa1()
        else:
            self._nome_pendente = nome_fixo
            self._id_pendente   = id_fixo
            self._build_etapa2()

        _centralizar(self, parent)

    def _limpar(self):
        for w in self.corpo.winfo_children():
            w.destroy()

    # ── Etapa 1 ───────────────────────────────────────────────────────────────

    def _build_etapa1(self):
        self._limpar()
        tk.Label(self.corpo, text="Etapa 1 de 2 — Dados do cliente",
                 font=FONTE_SMALL, bg=CORES["bg"], fg=CORES["texto2"]
                 ).pack(anchor="w", pady=(0, 16))

        tk.Label(self.corpo, text="Nome do cliente *",
                 font=FONTE_BOLD, bg=CORES["bg"], fg=CORES["texto"]).pack(anchor="w")
        self.entrada_nome = _make_input(self.corpo)
        self.entrada_nome.pack(fill="x", ipady=6, pady=(4, 16))

        tk.Label(self.corpo, text="ID interno (slug único, sem espaços) *",
                 font=FONTE_BOLD, bg=CORES["bg"], fg=CORES["texto"]).pack(anchor="w")
        tk.Label(self.corpo, text="Ex: empresa_xpto  |  Use letras, números e _",
                 font=FONTE_SMALL, bg=CORES["bg"], fg=CORES["texto2"]).pack(anchor="w")
        self.entrada_id = _make_input(self.corpo)
        self.entrada_id.pack(fill="x", ipady=6, pady=(4, 24))

        self.entrada_nome.bind("<KeyRelease>", self._auto_id)
        _make_btn(self.corpo, "Próximo → Autenticação", self._ir_etapa2).pack(fill="x")

    def _auto_id(self, _):
        nome = self.entrada_nome.get()
        slug = nome.lower().strip()
        slug = "".join(c if c.isalnum() else "_" for c in slug)
        slug = "_".join(filter(None, slug.split("_")))
        self.entrada_id.delete(0, tk.END)
        self.entrada_id.insert(0, slug)

    def _ir_etapa2(self):
        nome = self.entrada_nome.get().strip()
        cid  = self.entrada_id.get().strip()
        if not nome:
            messagebox.showwarning("Campo obrigatório", "Informe o nome.", parent=self)
            return
        if not cid or " " in cid:
            messagebox.showwarning("ID inválido", "ID obrigatório e sem espaços.", parent=self)
            return
        self._nome_pendente = nome
        self._id_pendente   = cid
        self._build_etapa2()

    # ── Etapa 2 ───────────────────────────────────────────────────────────────

    def _build_etapa2(self):
        self._limpar()
        etapa = "Etapa 2 de 2 — " if self.modo == "novo" else ""
        tk.Label(self.corpo, text=f"{etapa}Autenticação OAuth2",
                 font=FONTE_SMALL, bg=CORES["bg"], fg=CORES["texto2"]
                 ).pack(anchor="w", pady=(0, 8))
        tk.Label(self.corpo, text=f"Cliente: {self._nome_pendente}",
                 font=FONTE_BOLD, bg=CORES["bg"], fg=CORES["texto"]
                 ).pack(anchor="w", pady=(0, 16))

        instrucoes = (
            "1. Clique em 'Abrir login Conta Azul'\n"
            "2. Faça login com a conta do cliente\n"
            "3. Copie a URL completa de retorno\n"
            "4. Cole no campo abaixo e clique em Salvar"
        )
        frame_inst = tk.Frame(self.corpo, bg=CORES["surface"], padx=14, pady=12)
        frame_inst.pack(fill="x", pady=(0, 16))
        tk.Label(frame_inst, text=instrucoes, font=FONTE_SMALL,
                 bg=CORES["surface"], fg=CORES["texto2"], justify="left").pack(anchor="w")

        _make_btn(self.corpo, "🌐  Abrir login Conta Azul", self._abrir_login,
                  bg=CORES["surface2"]).pack(fill="x", pady=(0, 16))

        tk.Label(self.corpo, text="URL de retorno *",
                 font=FONTE_BOLD, bg=CORES["bg"], fg=CORES["texto"]).pack(anchor="w")
        tk.Label(self.corpo, text="Ex: https://contaazul.com/?code=xxx&state=ESTADO",
                 font=FONTE_SMALL, bg=CORES["bg"], fg=CORES["texto2"]).pack(anchor="w")
        self.entrada_url = _make_input(self.corpo, fonte=FONTE_MONO)
        self.entrada_url.pack(fill="x", ipady=6, pady=(4, 24))

        frame_btns = tk.Frame(self.corpo, bg=CORES["bg"])
        frame_btns.pack(fill="x")

        if self.modo == "novo":
            _make_btn(frame_btns, "← Voltar", self._build_etapa1,
                      bg=CORES["surface2"], fg=CORES["texto"]
                      ).pack(side="left", padx=(0, 8))

        _make_btn(frame_btns, "Salvar", self._salvar
                  ).pack(side="left", expand=True, fill="x")

    def _abrir_login(self):
        webbrowser.open(gerar_url_autorizacao())

    def _salvar(self):
        url = self.entrada_url.get().strip()
        if not url:
            messagebox.showwarning("Campo obrigatório", "Cole a URL de retorno.", parent=self)
            return
        try:
            code = extrair_code_da_url(url)
        except ValueError as e:
            messagebox.showerror("URL inválida", str(e), parent=self)
            return
        try:
            cadastrar_cliente(self._id_pendente, self._nome_pendente)
            trocar_code_por_tokens(self._id_pendente, code)
        except Exception as e:
            messagebox.showerror("Erro de autenticação", str(e), parent=self)
            return

        acao = "cadastrado" if self.modo == "novo" else "re-autenticado"
        messagebox.showinfo("Sucesso", f"'{self._nome_pendente}' {acao} com sucesso!", parent=self)
        self.destroy()
        if self.on_sucesso:
            self.on_sucesso()


# ═══════════════════════════════════════════════════════════════════════════════
# JANELA: CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════

class JanelaConfiguracoes(tk.Toplevel):
    def __init__(self, parent, on_salvar=None):
        super().__init__(parent)
        self.parent    = parent
        self.on_salvar = on_salvar
        self.title("Configurações")
        self.resizable(False, False)
        self.configure(bg=CORES["bg"])
        self.grab_set()

        header = tk.Frame(self, bg=CORES["surface2"], pady=14, padx=20)
        header.pack(fill="x")
        tk.Label(header, text="⚙  Configurações", font=FONTE_TITULO,
                 bg=CORES["surface2"], fg=CORES["texto"]).pack(anchor="w")

        corpo = tk.Frame(self, bg=CORES["bg"], padx=30, pady=24)
        corpo.pack(fill="both", expand=True)

        # Drive Root
        tk.Label(corpo, text="Pasta dos bancos dos clientes (Drive Root)",
                 font=FONTE_BOLD, bg=CORES["bg"], fg=CORES["texto"]).pack(anchor="w")
        tk.Label(corpo,
                 text="Pasta onde cada cliente terá seu dados.db\n"
                      "Ex: G:\\Meu Drive\\database  ou  C:\\Users\\Você\\ContaAzul",
                 font=FONTE_SMALL, bg=CORES["bg"], fg=CORES["texto2"],
                 justify="left").pack(anchor="w", pady=(2, 8))

        frame_path = tk.Frame(corpo, bg=CORES["bg"])
        frame_path.pack(fill="x", pady=(0, 24))

        self.entrada_path = _make_input(frame_path)
        self.entrada_path.insert(0, config.DRIVE_ROOT)
        self.entrada_path.pack(side="left", fill="x", expand=True, ipady=6)

        _make_btn(frame_path, "📁", self._escolher_pasta,
                  bg=CORES["surface2"], fg=CORES["texto"],
                  padx=10, pady=6).pack(side="left", padx=(8, 0))

        # Botões
        frame_btns = tk.Frame(corpo, bg=CORES["bg"])
        frame_btns.pack(fill="x")
        _make_btn(frame_btns, "Cancelar", self.destroy,
                  bg=CORES["surface2"], fg=CORES["texto"]
                  ).pack(side="left", padx=(0, 8))
        _make_btn(frame_btns, "Salvar", self._salvar
                  ).pack(side="left", expand=True, fill="x")

        _centralizar(self, parent)

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(
            title="Selecione a pasta dos bancos",
            initialdir=config.DRIVE_ROOT,
        )
        if pasta:
            self.entrada_path.delete(0, tk.END)
            self.entrada_path.insert(0, pasta)

    def _salvar(self):
        novo = self.entrada_path.get().strip()
        if not novo:
            messagebox.showwarning("Campo obrigatório", "Informe o caminho.", parent=self)
            return
        aplicar_drive_root(novo)
        messagebox.showinfo("Salvo", f"Pasta atualizada:\n{novo}", parent=self)
        self.destroy()
        if self.on_salvar:
            self.on_salvar()


# ═══════════════════════════════════════════════════════════════════════════════
# MENU DE CONTEXTO (botão direito na linha do cliente)
# ═══════════════════════════════════════════════════════════════════════════════

class MenuCliente(tk.Menu):
    def __init__(self, parent_app, cliente, on_atualizar):
        super().__init__(parent_app, tearoff=0,
                         bg=CORES["surface2"], fg=CORES["texto"],
                         activebackground=CORES["accent"],
                         activeforeground="white",
                         relief="flat", bd=0)
        self._app        = parent_app
        self._cliente    = cliente
        self._atualizar  = on_atualizar

        self.add_command(label="▶  Sincronizar",
                         command=self._sync)
        self.add_separator()
        self.add_command(label="🔑  Re-autenticar",
                         command=self._reauth)
        self.add_separator()
        self.add_command(label="⊘  Desativar cliente",
                         command=self._desativar,
                         foreground=CORES["vermelho"])

    def _sync(self):
        self._app._executar_sync([self._cliente])

    def _reauth(self):
        JanelaOAuth(
            self._app,
            on_sucesso=self._atualizar,
            modo="reauth",
            id_fixo=self._cliente["id"],
            nome_fixo=self._cliente["nome"],
        )

    def _desativar(self):
        nome = self._cliente["nome"]
        ok = messagebox.askyesno(
            "Desativar cliente",
            f"Desativar '{nome}'?\n\nO cliente sumirá da lista mas seus dados não serão apagados.",
            parent=self._app,
        )
        if not ok:
            return
        with conn_controle() as conn:
            conn.execute(
                "UPDATE clientes SET ativo=0, atualizado_em=datetime('now') WHERE id=?",
                (self._cliente["id"],)
            )
        self._atualizar()


# ═══════════════════════════════════════════════════════════════════════════════
# JANELA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conta Azul Sync")
        self.geometry("860x580")
        self.minsize(700, 440)
        self.configure(bg=CORES["bg"])

        init_controle()
        self._sync_ativa       = False
        self._linha_selecionada = None
        self._clientes         = []
        self._frames_linhas    = []

        self._build()
        self._carregar_clientes()

    # ─── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        # Topo
        topo = tk.Frame(self, bg=CORES["surface"], pady=14, padx=20)
        topo.pack(fill="x")

        tk.Label(topo, text="Conta Azul Sync", font=FONTE_TITULO,
                 bg=CORES["surface"], fg=CORES["texto"]).pack(side="left")

        _make_btn(topo, "⚙", self._abrir_config,
                  bg=CORES["surface2"], fg=CORES["texto2"],
                  padx=10, pady=5).pack(side="right", padx=(8, 0))

        _make_btn(topo, "+ Adicionar cliente", self._abrir_adicionar,
                  padx=16, pady=6).pack(side="right")

        # Centro
        centro = tk.Frame(self, bg=CORES["bg"])
        centro.pack(fill="both", expand=True)

        esq = tk.Frame(centro, bg=CORES["bg"], width=500)
        esq.pack(side="left", fill="both", expand=True)
        esq.pack_propagate(False)
        self._build_lista(esq)

        tk.Frame(centro, bg=CORES["borda"], width=1).pack(side="left", fill="y")

        dir_ = tk.Frame(centro, bg=CORES["bg"], width=320)
        dir_.pack(side="left", fill="both", expand=False)
        dir_.pack_propagate(False)
        self._build_log(dir_)

        # Rodapé
        rodape = tk.Frame(self, bg=CORES["surface"], pady=12, padx=20)
        rodape.pack(fill="x", side="bottom")

        self.btn_sync_todos = _make_btn(rodape, "▶  Sincronizar todos",
                                        self._sync_todos, padx=20, pady=8)
        self.btn_sync_todos.pack(side="left")

        self.btn_sync_sel = _make_btn(rodape, "▶  Sincronizar selecionado",
                                      self._sync_selecionado,
                                      bg=CORES["surface2"], fg=CORES["texto"],
                                      padx=20, pady=8)
        self.btn_sync_sel.pack(side="left", padx=(10, 0))

        self.label_status = tk.Label(rodape, text="", font=FONTE_SMALL,
                                     bg=CORES["surface"], fg=CORES["texto2"])
        self.label_status.pack(side="right")

    def _build_lista(self, parent):
        cab = tk.Frame(parent, bg=CORES["surface2"], pady=8, padx=16)
        cab.pack(fill="x")
        for texto, w in [("Cliente", 26), ("Última sync", 16), ("Status", 14)]:
            tk.Label(cab, text=texto, font=FONTE_BOLD,
                     bg=CORES["surface2"], fg=CORES["texto2"],
                     width=w, anchor="w").pack(side="left")

        container = tk.Frame(parent, bg=CORES["bg"])
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg=CORES["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas, bg=CORES["bg"])

        self.frame_lista.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _build_log(self, parent):
        tk.Label(parent, text="Log de sync", font=FONTE_BOLD,
                 bg=CORES["bg"], fg=CORES["texto2"], pady=10
                 ).pack(anchor="w", padx=14)

        self.txt_log = tk.Text(
            parent, font=FONTE_MONO,
            bg=CORES["surface"], fg=CORES["texto"],
            insertbackground=CORES["texto"],
            relief="flat", bd=0, wrap="word",
            state="disabled", padx=10, pady=8,
        )
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.txt_log.tag_config("ok",    foreground=CORES["verde"])
        self.txt_log.tag_config("erro",  foreground=CORES["vermelho"])
        self.txt_log.tag_config("info",  foreground=CORES["texto2"])
        self.txt_log.tag_config("titulo",foreground=CORES["accent"], font=FONTE_BOLD)

        _make_btn(parent, "Limpar log", self._limpar_log,
                  bg=CORES["surface2"], fg=CORES["texto2"],
                  padx=10, pady=4).pack(padx=8, pady=(0, 8), anchor="e")

    # ─── Lista de clientes ────────────────────────────────────────────────────

    def _carregar_clientes(self):
        for w in self.frame_lista.winfo_children():
            w.destroy()
        self._clientes          = get_clientes_ativos()
        self._linha_selecionada = None
        self._frames_linhas     = []

        if not self._clientes:
            tk.Label(self.frame_lista,
                     text="Nenhum cliente cadastrado.\nClique em '+ Adicionar cliente'.",
                     font=FONTE, bg=CORES["bg"], fg=CORES["cinza"],
                     justify="center", pady=40).pack()
            return

        for i, cliente in enumerate(self._clientes):
            self._criar_linha(cliente, i)

    def _criar_linha(self, cliente, indice: int):
        bg_base = CORES["bg"] if indice % 2 == 0 else CORES["surface"]

        linha = tk.Frame(self.frame_lista, bg=bg_base, cursor="hand2")
        linha.pack(fill="x")
        self._frames_linhas.append((linha, bg_base))

        status_txt, status_cor = status_cliente(cliente)
        ultima = formatar_data(ultima_sync_cliente(cliente))

        def selecionar(e, idx=indice, frame=linha, bg=bg_base):
            self._selecionar_linha(idx, frame, bg)

        def ctx_menu(e, c=cliente):
            menu = MenuCliente(self, c, self._carregar_clientes)
            menu.tk_popup(e.x_root, e.y_root)

        for texto, cor, w in [
            (cliente["nome"],  None,        26),
            (ultima,           CORES["texto2"], 16),
            (status_txt,       status_cor,  14),
        ]:
            lbl = tk.Label(linha, text=texto, font=FONTE,
                           bg=bg_base, fg=cor or CORES["texto"],
                           anchor="w", padx=16, pady=12, width=w)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", selecionar)
            lbl.bind("<Button-3>", ctx_menu)

        linha.bind("<Button-1>", selecionar)
        linha.bind("<Button-3>", ctx_menu)

        tk.Frame(self.frame_lista, bg=CORES["borda"], height=1).pack(fill="x")

    def _selecionar_linha(self, indice, frame, bg_original):
        # Restaura todas as linhas
        for f, bg in self._frames_linhas:
            f.configure(bg=bg)
            for w in f.winfo_children():
                try:
                    w.configure(bg=bg)
                except Exception:
                    pass
        # Destaca selecionada
        frame.configure(bg=CORES["accent"])
        for w in frame.winfo_children():
            try:
                w.configure(bg=CORES["accent"])
            except Exception:
                pass
        self._linha_selecionada = indice

    # ─── Log ──────────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "info"):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _limpar_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    # ─── Sync ─────────────────────────────────────────────────────────────────

    def _travar_botoes(self, travado: bool):
        estado = "disabled" if travado else "normal"
        self.btn_sync_todos.configure(state=estado)
        self.btn_sync_sel.configure(state=estado)
        self._sync_ativa = travado

    def _sync_todos(self):
        if self._sync_ativa:
            return
        clientes = get_clientes_ativos()
        if not clientes:
            messagebox.showinfo("Sem clientes", "Nenhum cliente cadastrado.")
            return
        self._executar_sync(clientes)

    def _sync_selecionado(self):
        if self._sync_ativa:
            return
        if self._linha_selecionada is None:
            messagebox.showinfo("Selecione", "Clique em um cliente na lista.")
            return
        self._executar_sync([self._clientes[self._linha_selecionada]])

    def _executar_sync(self, clientes: list):
        self._travar_botoes(True)
        self._limpar_log()
        self.label_status.configure(text="Sincronizando...", fg=CORES["amarelo"])

        def worker():
            total = len(clientes)
            for i, cliente in enumerate(clientes, 1):
                self.after(0, self._log, f"\n── {cliente['nome']} ({i}/{total}) ──", "titulo")

                def callback(msg):
                    tag = "ok" if msg.startswith("[✓]") else \
                          "erro" if msg.startswith("[✗]") else "info"
                    self.after(0, self._log, f"  {msg}", tag)

                res = sincronizar_cliente(dict(cliente), callback=callback)

                if res["erros"]:
                    self.after(0, self._log, f"  ✗ {len(res['erros'])} erro(s)", "erro")
                else:
                    self.after(0, self._log, "  ✓ Concluído", "ok")

            self.after(0, self._pos_sync)

        threading.Thread(target=worker, daemon=True).start()

    def _pos_sync(self):
        self._travar_botoes(False)
        self.label_status.configure(
            text=f"Última sync: {datetime.now().strftime('%H:%M:%S')}",
            fg=CORES["verde"],
        )
        self._carregar_clientes()

    # ─── Ações ────────────────────────────────────────────────────────────────

    def _abrir_adicionar(self):
        JanelaOAuth(self, on_sucesso=self._carregar_clientes, modo="novo")

    def _abrir_config(self):
        JanelaConfiguracoes(self, on_salvar=self._carregar_clientes)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
