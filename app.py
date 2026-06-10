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
             (id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, valor REAL, status TEXT, data TEXT)''')
conn.commit()

# --- FUNÇÕES DE BACKUP AUTOMÁTICO ---
def realizar_backup():
    if not os.path.exists('backups'):
        os.makedirs('backups')
    hora_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile('sistema_vendas.db', f'backups/backup_{hora_atual}.db')

# --- INTERFACE ---
st.title("📱 Sistema de Vendas e Caixa")

menu = ["Nova Venda", "Dar Baixa (Pagamentos)", "Registro Geral / PDF"]
choice = st.sidebar.selectbox("Menu", menu)

# --- 1. NOVA VENDA ---
if choice == "Nova Venda":
    st.subheader("🛒 Registrar Venda")
    
    telefone = st.text_input("Telefone do Cliente:")
    nome_cliente = ""
    
    if telefone:
        # Verifica se cliente já existe
        c.execute("SELECT nome FROM clientes WHERE telefone = ?", (telefone,))
        res = c.fetchone()
        if res:
            nome_cliente = res[0]
            st.success(f"Cliente encontrado: **{nome_cliente}**")
        else:
            nome_cliente = st.text_input("Novo Cliente - Digite o Nome:")
            if nome_cliente and st.button("Cadastrar Cliente"):
                c.execute("INSERT INTO clientes VALUES (?, ?)", (telefone, nome_cliente))
                conn.commit()
                st.success("Cliente cadastrado com sucesso!")

    valor = st.number_input("Valor da Compra (R$)", min_value=0.0, step=0.01)
    
    if st.button("Confirmar Venda"):
        if telefone and nome_cliente and valor > 0:
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO vendas (telefone, valor, status, data) VALUES (?, ?, 'Pendente', ?)", 
                      (telefone, valor, data_atual))
            conn.commit()
            st.success(f"Venda de R$ {valor:.2f} registrada para {nome_cliente}!")
            realizar_backup() # Aciona o backup
        else:
            st.error("Preencha todos os campos corretamente.")

# --- 2. DAR BAIXA ---
elif choice == "Dar Baixa (Pagamentos)":
    st.subheader("💳 Baixa em Pagamentos")
    
    # Busca simplificada para evitar conflito de colunas
    query = '''SELECT vendas.id, clientes.nome, vendas.valor, vendas.data 
               FROM vendas 
               INNER JOIN clientes ON vendas.telefone = clientes.telefone 
               WHERE vendas.status = 'Pendente''''
    
    try:
        df_pendentes = pd.read_sql_query(query, conn)
        
        if not df_pendentes.empty:
            # Renomeia as colunas apenas para exibição bonita na tela
            df_exibir = df_pendentes.rename(columns={
                'id': 'ID da Venda',
                'nome': 'Nome do Cliente',
                'valor': 'Valor (R$)',
                'data': 'Data/Hora'
            })
            st.dataframe(df_exibir)
            
            venda_id = st.number_input("Digite o ID da venda para dar baixa:", min_value=1, step=1)
            if st.button("Confirmar Recebimento"):
                c.execute("UPDATE vendas SET status = 'Pago' WHERE id = ?", (venda_id,))
                conn.commit()
                st.success("Pagamento registrado com sucesso!")
                st.rerun() # Atualiza a tela automaticamente
        else:
            st.info("Não há contas pendentes no momento.")
            
    except Exception as e:
        st.error("Erro ao carregar os dados. O banco de dados pode estar desalinhado.")
        if st.button("Recriar Tabelas do Banco (Limpar Erros)"):
            c.execute('''CREATE TABLE IF NOT EXISTS vendas 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT, valor REAL, status TEXT, data TEXT)''')
            conn.commit()
            st.rerun()

# --- 3. REGISTRO GERAL E FECHAMENTO ---
elif choice == "Registro Geral / PDF":
    st.subheader("📊 Resumo Financeiro")
    
    # Cálculos
    df_vendas = pd.read_sql_query("SELECT * FROM vendas", conn)
    
    if not df_vendas.empty:
        total_vendido = df_vendas['valor'].sum()
        total_recebido = df_vendas[df_vendas['status'] == 'Pago']['valor'].sum()
        total_a_receber = df_vendas[df_vendas['status'] == 'Pendente']['valor'].sum()
        
        # Exibição dos Cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Vendido", f"R$ {total_vendido:.2f}")
        col2.metric("Total Recebido", f"R$ {total_recebido:.2f}")
        col3.metric("A Receber", f"R$ {total_a_receber:.2f}", delta_color="inverse")
        
        # Gerador de PDF / Relatório do Dia (Simulado para exportação rápida em Excel/CSV ou impressão)
        st.write("---")
        st.subheader("🕒 Fechamento das 17:00h")
        
        data_hj = datetime.now().strftime("%Y-%m-%d")
        df_hoje = df_vendas[df_vendas['data'].str.contains(data_hj)]
        
        if not df_hoje.empty:
            st.write("Vendas do dia de hoje:")
            st.dataframe(df_hoje)
            
            # Botão para baixar relatório pronto
            csv = df_hoje.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Gerar Relatório das 17h (CSV/Excel)", csv, f"fechamento_{data_hj}.csv", "text/csv")
        else:
            st.info("Nenhuma venda realizada hoje até o momento.")
