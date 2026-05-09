# Conta Azul Sync

## Arquivos

| Arquivo | Função |
|---|---|
| `config.py` | Configurações: CLIENT_ID, CLIENT_SECRET, caminhos |
| `database.py` | controle.db (tokens) + dados.db por cliente (Drive) |
| `auth.py` | OAuth2: geração de URL, troca de code, renovação de token |
| `api_client.py` | HTTP com paginação, retry e rate limit |
| `sync.py` | Mapeamento dos dados da API → SQLite |
| `main.py` | Orquestrador: chama API + salva + registra logs |
| `app.py` | Interface Tkinter (lista de clientes + sync + cadastro) |

## Configuração inicial

### 1. `config.py`

```python
CLIENT_ID     = "seu_client_id"
CLIENT_SECRET = "seu_client_secret"
REDIRECT_URI  = "https://contaazul.com/"   # URI cadastrada no app

# Caminho do Google Drive Desktop
# Windows: r"C:\Users\Você\Google Drive\My Drive\ContaAzul"
DRIVE_ROOT = r"C:\..."
```

### 2. Instalar dependências

```bash
pip install requests
```

### 3. Rodar

```bash
python app.py          # Interface gráfica (recomendado)
python main.py         # Terminal — todos os clientes
python main.py id_xyz  # Terminal — cliente específico
```

## Estrutura de arquivos gerada

```
projeto/
└── controle.db          ← Tokens e logs. NUNCA compartilhe.

Google Drive/ContaAzul/
├── empresa_xpto/
│   └── dados.db         ← Power BI do cliente aponta aqui
└── empresa_abc/
    └── dados.db
```

## Tabelas em cada dados.db (Power BI)

| Tabela | Conteúdo |
|---|---|
| `pessoas` | Clientes e fornecedores (campo `perfis` indica qual é qual) |
| `contas_receber` | Parcelas de receita |
| `contas_pagar` | Parcelas de despesa |
| `contas_financeiras` | Bancos, caixas e cartões |
| `saldos_snapshot` | Saldo capturado a cada sync (histórico) |
| `saldos_iniciais` | Saldo inicial por período configurado no ERP |

## Fluxo de cadastro de cliente (pela interface)

1. Clique em **+ Adicionar cliente**
2. Informe nome e ID (o ID é gerado automaticamente)
3. Clique em **Abrir login Conta Azul** — faz login na conta do cliente
4. Copie a URL de retorno (ex: `https://contaazul.com/?code=xxx&state=yyy`)
5. Cole no campo e clique em **Salvar cliente**

## Sync incremental

- **Primeira sync:** puxa os últimos 5 anos + próximos 2 anos
- **Syncs seguintes:** usa `data_alteracao_de` com recuo de 3 dias
- Saldos atuais: sempre capturados com timestamp (histórico acumulativo)
