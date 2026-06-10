import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import shutil

# Configuração da página para se adaptar ao celular
st.set_page_config(page_title="Controle de Vendas", layout="centered")

# Conexão com o banco de dados
conn = sqlite3.connect('sistema_vendas.db', check_same_thread=False)
c = conn.cursor()

# Criar tabelas se não existirem
c.execute('''CREATE TABLE IF NOT EXISTS clientes 
             (telefone TEXT PRIMARY KEY, nome TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS vendas 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, valor REAL, status TEXT, data TEXT, metodo_pagamento TEXT)''')
conn.commit()

# Migração de banco de dados para garantir que a coluna de método de pagamento exista
try:
    c.execute("ALTER TABLE vendas ADD COLUMN metodo_pagamento TEXT")
    conn.commit()
except sqlite3.OperationalError:
    # A coluna já existe, ignorar
    pass

# --- FUNÇÕES DE BACKUP AUTOMÁTICO ---
def realizar_backup():
    try:
        if not os.path.exists('backups'):
            os.makedirs('backups')
        hora_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
        if os.path.exists('sistema_vendas.db'):
            shutil.copyfile('sistema_vendas.db', f'backups/backup_{hora_atual}.db')
    except Exception:
        pass

# --- INTERFACE PRINCIPAL ---
st.title("📱 Bazar Casulo")

# Menu em formato de abas individuais no topo (fácil acesso no celular)
tab_venda, tab_baixa, tab_resumo = st.tabs([
    "🛒 Registrar Venda", 
    "💳 Contas Pendentes / Dar Baixa", 
    "📊 Registro Geral & Relatórios"
])

# --- TAB 1: REGISTRAR VENDA ---
with tab_venda:
    st.subheader("Registrar Nova Venda")
    
    telefone = st.text_input("Telefone do Cliente (com DDD):", key="venda_telefone")
    nome_cliente = ""
    
    if telefone:
        # Verifica se o cliente já existe no banco de dados
        c.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,))
        res = c.fetchone()
        if res:
            nome_cliente = res[0]
            st.success(f"Cliente cadastrado encontrado: **{nome_cliente}**")
            # Permite confirmar ou alterar o nome se necessário
            nome_cliente = st.text_input("Nome do Cliente:", value=nome_cliente, key="venda_nome")
        else:
            st.warning("Novo cliente detectado! Digite o nome para cadastrá-lo automaticamente ao salvar.")
            nome_cliente = st.text_input("Nome do Novo Cliente:", key="venda_nome_novo")

    valor = st.number_input("Valor da Compra (R$)", min_value=0.0, step=0.01, key="venda_valor")
    
    if st.button("Confirmar Venda", use_container_width=True):
        if telefone and nome_cliente and valor > 0:
            # Cadastra ou atualiza o cliente automaticamente
            c.execute("INSERT OR REPLACE INTO clientes (telefone, nome) VALUES (?, ?)", (telefone, nome_cliente))
            
            # Registra a venda como pendente
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO vendas (telefone, valor, status, data, metodo_pagamento) VALUES (?, ?, 'Pendente', ?, NULL)", 
                      (telefone, valor, data_atual))
            conn.commit()
            
            st.success(f"Venda de R$ {valor:.2f} registrada com sucesso para {nome_cliente}!")
            realizar_backup()
            st.rerun()
        else:
            st.error("Por favor, preencha todos os campos e certifique-se de que o valor é maior que zero.")

# --- TAB 2: DAR BAIXA EM PAGAMENTOS ---
with tab_baixa:
    st.subheader("Contas a Receber")
    
    # Busca usando LEFT JOIN para evitar que vendas sumam se o cliente não estiver associado
    query_pendentes = '''SELECT vendas.id, COALESCE(clientes.nome, 'Sem Nome (' || vendas.telefone || ')') as nome, vendas.valor, vendas.data 
                         FROM vendas 
                         LEFT JOIN clientes ON vendas.telefone = clientes.telefone 
                         WHERE vendas.status = 'Pendente' '''
    
    try:
        df_pendentes = pd.read_sql_query(query_pendentes, conn)
        
        if not df_pendentes.empty:
            df_exibir = df_pendentes.rename(columns={
                'id': 'Código',
                'nome': 'Nome do Cliente',
                'valor': 'Valor Pendente (R$)',
                'data': 'Data/Hora'
            })
            
            # Mostra a tabela das contas que estão devendo
            st.dataframe(df_exibir, use_container_width=True, hide_index=True)
            
            st.write("---")
            st.subheader("Dar Baixa de Pagamento")
            
            # Criação de uma lista de seleção amigável para celular
            opcoes_vendas = []
            venda_map = {}
            for _, row in df_pendentes.iterrows():
                label = f"Cod: {row['id']} | {row['nome']} - R$ {row['valor']:.2f}"
                opcoes_vendas.append(label)
                venda_map[label] = row['id']
                
            venda_selecionada = st.selectbox("Selecione a conta que está sendo paga:", opcoes_vendas)
            id_para_baixa = venda_map[venda_selecionada]
            
            # Seleção da forma de pagamento
            forma_pagamento = st.radio("Forma de recebimento:", ["Pix", "Dinheiro"], horizontal=True)
            
            if st.button("Confirmar Recebimento (Dar Baixa)", use_container_width=True):
                c.execute("UPDATE vendas SET status = 'Pago', metodo_pagamento = ? WHERE id = ?", (forma_pagamento, id_para_baixa))
                conn.commit()
                st.success(f"Baixa realizada com sucesso via {forma_pagamento}!")
                realizar_backup()
                st.rerun()
        else:
            st.info("Não existem contas pendentes de pagamento no momento!")
            
    except Exception as e:
        st.error("Ocorreu um erro ao carregar os dados das baixas.")
        if st.button("Limpar e Sincronizar Banco de Dados"):
            c.execute('''CREATE TABLE IF NOT EXISTS vendas 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, valor REAL, status TEXT, data TEXT, metodo_pagamento TEXT)''')
            conn.commit()
            st.rerun()

# --- TAB 3: REGISTRO GERAL E RELATÓRIOS ---
with tab_resumo:
    st.subheader("Resumo Geral de Caixa")
    
    try:
        df_vendas = pd.read_sql_query('''
            SELECT vendas.id, COALESCE(clientes.nome, 'Sem Nome (' || vendas.telefone || ')') as nome, 
                   vendas.valor, vendas.status, vendas.data, vendas.metodo_pagamento 
            FROM vendas
            LEFT JOIN clientes ON vendas.telefone = clientes.telefone
        ''', conn)
    except Exception:
        df_vendas = pd.DataFrame()

    if not df_vendas.empty:
        total_vendido = df_vendas['valor'].sum()
        total_recebido = df_vendas[df_vendas['status'] == 'Pago']['valor'].sum()
        total_a_receber = df_vendas[df_vendas['status'] == 'Pendente']['valor'].sum()
        
        # Divisão por métodos de recebimento
        total_pix = df_vendas[df_vendas['metodo_pagamento'] == 'Pix']['valor'].sum()
        total_dinheiro = df_vendas[df_vendas['metodo_pagamento'] == 'Dinheiro']['valor'].sum()
        
        # Exibição de cards financeiros rápidos
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Vendido (Geral)", f"R$ {total_vendido:.2f}")
        col2.metric("Total Recebido (Caixa)", f"R$ {total_recebido:.2f}")
        col3.metric("A Receber (Dívidas)", f"R$ {total_a_receber:.2f}")
        
        st.write("---")
        st.subheader("📊 Distribuição dos Recebimentos")
        col_pix, col_din = st.columns(2)
        col_pix.metric("Recebido via Pix", f"R$ {total_pix:.2f}")
        col_din.metric("Recebido via Dinheiro", f"R$ {total_dinheiro:.2f}")
        
        st.write("---")
        st.subheader("🕒 Fechamento Diário (Relatório das 17:00h)")
        
        data_hj = datetime.now().strftime("%Y-%m-%d")
        df_hoje = df_vendas[df_vendas['data'].fillna('').str.contains(data_hj)]
        
        if not df_hoje.empty:
            st.write("Vendas realizadas hoje:")
            df_hoje_exibir = df_hoje.rename(columns={
                'id': 'Código',
                'nome': 'Nome do Cliente',
                'valor': 'Valor (R$)',
                'status': 'Status',
                'data': 'Data/Hora',
                'metodo_pagamento': 'Meio de Pgto'
            })
            st.dataframe(df_hoje_exibir, use_container_width=True, hide_index=True)
            
            # Exportação de relatório em formato limpo
            csv = df_hoje.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Fechamento de Hoje (CSV/Excel)",
                data=csv,
                file_name=f"fechamento_{data_hj}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("Nenhuma venda registrada na data de hoje até o momento.")
    else:
        st.info("Nenhum registro de vendas localizado no sistema.")
