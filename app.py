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

# --- MIGRAÇÃO AUTOMÁTICA E SEGURA ---
try:
    # Verifica se a tabela 'clientes' antiga existe e precisa de migração
    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='clientes'")
    if c.fetchone()[0] > 0:
        c.execute("PRAGMA table_info(clientes)")
        colunas = [col[1] for col in c.fetchall()]
        if 'sobrenome' not in colunas:
            # Renomeia tabela antiga para preservação de dados
            c.execute("ALTER TABLE clientes RENAME TO clientes_antigo")
            conn.commit()
            
            # Cria nova tabela com a estrutura de segurança atualizada
            c.execute('''CREATE TABLE IF NOT EXISTS clientes (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         nome TEXT,
                         sobrenome TEXT,
                         telefone TEXT,
                         UNIQUE(nome, sobrenome, telefone))''')
            conn.commit()
            
            # Migra registros separando nome de sobrenome de forma inteligente
            c.execute("SELECT telefone, nome FROM clientes_antigo")
            antigos = c.fetchall()
            for tel, nome_completo in antigos:
                partes = nome_completo.strip().split(" ", 1)
                p_nome = partes[0]
                p_sobrenome = partes[1] if len(partes) > 1 else ""
                c.execute("INSERT OR IGNORE INTO clientes (nome, sobrenome, telefone) VALUES (?, ?, ?)", 
                          (p_nome, p_sobrenome, tel))
            conn.commit()
except Exception:
    pass

# Criar tabelas garantindo integridade dos dados
c.execute('''CREATE TABLE IF NOT EXISTS clientes (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             nome TEXT,
             sobrenome TEXT,
             telefone TEXT,
             UNIQUE(nome, sobrenome, telefone))''')

c.execute('''CREATE TABLE IF NOT EXISTS vendas (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             cliente_id INTEGER,
             telefone TEXT,
             valor REAL,
             status TEXT,
             data TEXT,
             metodo_pagamento TEXT,
             observacao TEXT)''')
conn.commit()

# Adiciona colunas novas caso a tabela 'vendas' antiga já exista
colunas_novas = [
    ("cliente_id", "INTEGER"),
    ("metodo_pagamento", "TEXT"),
    ("observacao", "TEXT")
]
for col_nome, col_tipo in colunas_novas:
    try:
        c.execute(f"ALTER TABLE vendas ADD COLUMN {col_nome} {col_tipo}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

# Associa de forma retroativa vendas antigas aos novos IDs de cliente
try:
    c.execute("SELECT id, telefone FROM vendas WHERE cliente_id IS NULL AND telefone IS NOT NULL")
    vendas_sem_id = c.fetchall()
    for v_id, tel in vendas_sem_id:
        c.execute("SELECT id FROM clientes WHERE telefone = ?", (tel,))
        cli = c.fetchone()
        if cli:
            c.execute("UPDATE vendas SET cliente_id = ? WHERE id = ?", (cli[0], v_id))
    conn.commit()
except Exception:
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

# Menu em formato de abas individuais no topo (fácil acesso no celular e PC)
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
    sobrenome_cliente = ""
    cliente_id = None
    
    if telefone:
        # Busca todos os clientes cadastrados com este mesmo número
        c.execute("SELECT id, nome, sobrenome FROM clientes WHERE telefone = ?", (telefone,))
        clientes_encontrados = c.fetchall()
        
        if clientes_encontrados:
            st.info(f"Encontramos {len(clientes_encontrados)} cadastro(s) com este telefone.")
            
            opcoes = []
            id_map = {}
            for cid, nom, sob in clientes_encontrados:
                label = f"{nom} {sob}"
                opcoes.append(label)
                id_map[label] = (cid, nom, sob)
            
            opcoes.append("➕ Cadastrar nova pessoa com este mesmo telefone")
            
            escolha = st.selectbox("Selecione o cliente responsável pela compra:", opcoes, key="venda_selecao_cliente")
            
            if escolha != "➕ Cadastrar nova pessoa com este mesmo telefone":
                cliente_id, nome_cliente, sobrenome_cliente = id_map[escolha]
                st.success(f"Cliente selecionado: **{nome_cliente} {sobrenome_cliente}**")
            else:
                nome_cliente = st.text_input("Nome do Novo Cliente:", key="venda_nome_novo")
                sobrenome_cliente = st.text_input("Sobrenome do Novo Cliente:", key="venda_sobrenome_novo")
        else:
            st.warning("Novo cliente detectado!")
            nome_cliente = st.text_input("Nome do Novo Cliente:", key="venda_nome_novo_sem_tel")
            sobrenome_cliente = st.text_input("Sobrenome do Novo Cliente:", key="venda_sobrenome_novo_sem_tel")

    valor = st.number_input("Valor da Compra (R$)", min_value=0.0, step=0.01, key="venda_valor")
    
    if st.button("Confirmar Venda", use_container_width=True):
        if telefone and nome_cliente and valor > 0:
            # Cadastra novo cliente apenas se não houver um ID selecionado
            if not cliente_id:
                try:
                    c.execute("INSERT INTO clientes (nome, sobrenome, telefone) VALUES (?, ?, ?)", 
                              (nome_cliente.strip(), sobrenome_cliente.strip(), telefone.strip()))
                    conn.commit()
                    cliente_id = c.lastrowid
                except sqlite3.IntegrityError:
                    # Se disparar UNIQUE constraint (nome + sobrenome + telefone idênticos)
                    c.execute("SELECT id FROM clientes WHERE nome = ? AND sobrenome = ? AND telefone = ?", 
                              (nome_cliente.strip(), sobrenome_cliente.strip(), telefone.strip()))
                    cliente_id = c.fetchone()[0]
            
            # Registra a venda vinculando ao ID único do cliente
            data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute('''INSERT INTO vendas (cliente_id, telefone, valor, status, data, metodo_pagamento, observacao) 
                         VALUES (?, ?, ?, 'Pendente', ?, NULL, NULL)''', 
                      (cliente_id, telefone, valor, data_atual))
            conn.commit()
            
            st.success(f"Venda de R$ {valor:.2f} registrada para {nome_cliente.strip()} {sobrenome_cliente.strip()}!")
            realizar_backup()
            st.rerun()
        else:
            st.error("Por favor, preencha todos os campos e certifique-se de que o valor é maior que zero.")

# --- TAB 2: DAR BAIXA EM PAGAMENTOS ---
with tab_baixa:
    st.subheader("Contas a Receber")
    
    # Busca com LEFT JOIN para listar vendas pendentes com o nome e sobrenome corretos
    query_pendentes = '''SELECT vendas.id, 
                               COALESCE(clientes.nome || ' ' || clientes.sobrenome, 'Sem Nome (' || vendas.telefone || ')') as nome, 
                               vendas.valor, vendas.data, vendas.observacao 
                        FROM vendas 
                        LEFT JOIN clientes ON vendas.cliente_id = clientes.id 
                        WHERE vendas.status = 'Pendente' '''
    
    try:
        df_pendentes = pd.read_sql_query(query_pendentes, conn)
        
        if not df_pendentes.empty:
            df_exibir = df_pendentes.rename(columns={
                'id': 'Código',
                'nome': 'Nome do Cliente',
                'valor': 'Valor Pendente (R$)',
                'data': 'Data/Hora',
                'observacao': 'Observação'
            })
            
            st.dataframe(df_exibir, use_container_width=True, hide_index=True)
            
            st.write("---")
            st.subheader("Dar Baixa de Pagamento")
            
            # Lista de seleção de contas de fácil acesso
            opcoes_vendas = []
            venda_map = {}
            for _, row in df_pendentes.iterrows():
                label = f"Cod: {row['id']} | {row['nome']} - R$ {row['valor']:.2f}"
                opcoes_vendas.append(label)
                venda_map[label] = row['id']
                
            venda_selecionada = st.selectbox("Selecione a conta que está sendo paga:", opcoes_vendas, key="selecao_venda_baixa")
            id_para_baixa = venda_map[venda_selecionada]
            
            forma_pagamento = st.radio("Forma de recebimento:", ["Pix", "Dinheiro"], horizontal=True, key="baixa_pagamento")
            
            # Nova Opção: Anotação Opcional durante a baixa
            observacao = st.text_input("Observação / Anotação para esta venda (Opcional):", placeholder="Ex: Pago com atraso, entregue em mãos, etc.", key="baixa_observacao")
            
            if st.button("Confirmar Recebimento (Dar Baixa)", use_container_width=True):
                c.execute("UPDATE vendas SET status = 'Pago', metodo_pagamento = ?, observacao = ? WHERE id = ?", 
                          (forma_pagamento, observacao.strip() if observacao else None, id_para_baixa))
                conn.commit()
                st.success(f"Baixa realizada com sucesso via {forma_pagamento}!")
                realizar_backup()
                st.rerun()
        else:
            st.info("Não existem contas pendentes de pagamento no momento!")
            
    except Exception as e:
        st.error("Ocorreu um erro ao carregar os dados das baixas.")

# --- TAB 3: REGISTRO GERAL E RELATÓRIOS ---
with tab_resumo:
    st.subheader("Resumo Geral de Caixa")
    
    try:
        df_vendas = pd.read_sql_query('''
            SELECT vendas.id, 
                   COALESCE(clientes.nome || ' ' || clientes.sobrenome, 'Sem Nome (' || vendas.telefone || ')') as nome, 
                   vendas.valor, vendas.status, vendas.data, vendas.metodo_pagamento, vendas.observacao 
            FROM vendas
            LEFT JOIN clientes ON vendas.cliente_id = clientes.id
        ''', conn)
    except Exception:
        df_vendas = pd.DataFrame()

    if not df_vendas.empty:
        total_vendido = df_vendas['valor'].sum()
        total_recebido = df_vendas[df_vendas['status'] == 'Pago']['valor'].sum()
        total_a_receber = df_vendas[df_vendas['status'] == 'Pendente']['valor'].sum()
        
        total_pix = df_vendas[df_vendas['metodo_pagamento'] == 'Pix']['valor'].sum()
        total_dinheiro = df_vendas[df_vendas['metodo_pagamento'] == 'Dinheiro']['valor'].sum()
        
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
                'metodo_pagamento': 'Meio de Pgto',
                'observacao': 'Observação'
            })
            st.dataframe(df_hoje_exibir, use_container_width=True, hide_index=True)
            
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
