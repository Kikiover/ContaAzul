# api_client.py
import time
import requests
from datetime import datetime, timedelta
from config import API_BASE, PAGE_SIZE, MAX_RETRIES, RETRY_DELAY, ANOS_HISTORICO, ANOS_FUTURO

CHUNK_DIAS = 364  # máximo aceito pela API por requisição


class ContaAzulAPI:

    def __init__(self, access_token: str, cliente_id: str):
        self.cliente_id = cliente_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        })

    # ─── Core HTTP ────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        url = f"{API_BASE}{path}"

        for tentativa in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)

                if resp.status_code == 429:
                    espera = int(resp.headers.get("Retry-After", RETRY_DELAY * tentativa))
                    print(f"  [rate limit] aguardando {espera}s...")
                    time.sleep(espera)
                    continue

                if resp.status_code >= 500:
                    espera = RETRY_DELAY * tentativa
                    print(f"  [erro {resp.status_code}] tentativa {tentativa}/{MAX_RETRIES}, aguardando {espera}s...")
                    time.sleep(espera)
                    continue

                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Erro {resp.status_code} em {path}: {resp.text[:300]}"
                    )

                return resp.json()

            except requests.exceptions.ConnectionError as e:
                if tentativa == MAX_RETRIES:
                    raise RuntimeError(f"Falha de conexão após {MAX_RETRIES} tentativas: {e}")
                time.sleep(RETRY_DELAY * tentativa)

        raise RuntimeError(f"Máximo de tentativas atingido: {path}")

    def _paginar(self, path: str, params: dict = None, page_size: int = None) -> list:
        """Itera todas as páginas de um endpoint e retorna lista completa."""
        tam = page_size or PAGE_SIZE
        params = {**(params or {}), "tamanho_pagina": tam, "pagina": 1}
        todos = []

        while True:
            data = self._request("GET", path, params=params)

            itens = data.get("itens") or data.get("items") or []
            if itens is None:
                itens = []
            total = data.get("itens_totais") or data.get("totalItems") or 0

            todos.extend(itens)
            if itens and params.get("pagina") == 1:
                import json
                print("=== EXEMPLO REGISTRO ===")
                print(json.dumps(itens[0], indent=2, ensure_ascii=False))
                print("========================")
            print(f"  p.{params['pagina']} | +{len(itens)} | acumulado: {len(todos)}/{total}")

            # Para se nao veio nada, ou veio menos que o tamanho pedido (ultima pag),
            # ou atingiu o total informado pela API (quando confiavel)
            if not itens or len(itens) < tam or (total > 0 and len(todos) >= total):
                break

            params["pagina"] += 1
            time.sleep(0.2)

        return todos

    def _paginar_por_chunks(self, path: str, campo_inicio: str, campo_fim: str,
                            dt_inicio: datetime, dt_fim: datetime,
                            params_extras: dict = None) -> list:
        """
        Quebra o período em chunks de CHUNK_DIAS e agrega os resultados.
        Necessário para endpoints que rejeitam intervalos > 365 dias.
        """
        todos = []
        cursor = dt_inicio

        while cursor <= dt_fim:
            fim_chunk = min(cursor + timedelta(days=CHUNK_DIAS), dt_fim)
            params = {
                **(params_extras or {}),
                campo_inicio: cursor.strftime("%Y-%m-%d"),
                campo_fim:    fim_chunk.strftime("%Y-%m-%d"),
            }
            print(f"  chunk: {params[campo_inicio]} → {params[campo_fim]}")
            registros = self._paginar(path, params)
            todos.extend(registros)
            cursor = fim_chunk + timedelta(days=1)
            time.sleep(0.3)

        return todos

    # ─── Ranges padrão ────────────────────────────────────────────────────────

    @staticmethod
    def _range_padrao() -> tuple[datetime, datetime]:
        hoje = datetime.now()
        return (
            hoje - timedelta(days=365 * ANOS_HISTORICO),
            hoje + timedelta(days=365 * ANOS_FUTURO),
        )

    # ─── Endpoints ────────────────────────────────────────────────────────────

    def get_pessoas(self, data_alteracao_de: str = None) -> list:
        params = {"tamanho_pagina": 10, "pagina": 1, "com_endereco": "true"}
        if data_alteracao_de:
            params["data_alteracao_de"]  = data_alteracao_de
            params["data_alteracao_ate"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        todos = []
        while True:
            data = self._request("GET", "/v1/pessoas", params=params)
            itens = data.get("items") or []
            total = data.get("totalItems") or 0
            todos.extend(itens)
            print(f"  [pessoas] p.{params['pagina']} | +{len(itens)} | acumulado: {len(todos)}/{total}")
            if not itens or len(todos) >= total:
                break
            params["pagina"] += 1
            time.sleep(0.2)
        return todos

    def get_contas_receber(self, data_alteracao_de: str = None) -> list:
        inicio, fim = self._range_padrao()
        params_extras = {}
        if data_alteracao_de:
            params_extras["data_alteracao_de"]  = data_alteracao_de
            params_extras["data_alteracao_ate"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        return self._paginar_por_chunks(
            path="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
            campo_inicio="data_vencimento_de",
            campo_fim="data_vencimento_ate",
            dt_inicio=inicio,
            dt_fim=fim,
            #params_extras=params_extras,
        )

    def get_contas_pagar(self, data_alteracao_de: str = None) -> list:
        inicio, fim = self._range_padrao()
        params_extras = {}
        if data_alteracao_de:
            params_extras["data_alteracao_de"]  = data_alteracao_de
            params_extras["data_alteracao_ate"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        return self._paginar_por_chunks(
            path="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
            campo_inicio="data_vencimento_de",
            campo_fim="data_vencimento_ate",
            dt_inicio=inicio,
            dt_fim=fim,
            #params_extras=params_extras,
        )

    def get_contas_financeiras(self) -> list:
        return self._paginar("/v1/conta-financeira", {"apenas_ativo": "false"})

    def get_saldo_atual(self, id_conta: str) -> float:
        data = self._request("GET", f"/v1/conta-financeira/{id_conta}/saldo-atual")
        return data.get("saldo_atual", 0.0)

    def get_categorias(self) -> list:
        return self._paginar("/v1/categorias")
