import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import hashlib
import bcrypt
import os

# Configuração de segurança
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.warning("dotenv não está instalado. Usando variáveis padrão.")

SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
PASSWORD_HASH = os.getenv('PASSWORD_HASH', '')

# Função de autenticação
def check_password():
    """Verifica se o usuário digitou a senha correta."""
    if 'authenticated' in st.session_state:
        return True
    
    password = st.text_input("Senha de acesso", type="password", key="password_input")
    
    if password:
        if bcrypt.checkpw(password.encode(), PASSWORD_HASH.encode()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    
    return False

# Função de validação de arquivo
def validate_file(file):
    """Valida o arquivo enviado pelo usuário."""
    if not file:
        return False
        
    if file.size > 10 * 1024 * 1024:  # 10MB
        st.error("Arquivo muito grande (máximo 10MB)")
        return False
        
    if not file.name.endswith(('.xlsx', '.xls')):
        st.error("Formato inválido. Use .xlsx ou .xls")
        return False
        
    return True

# Função de sanitização (ADICIONADA)
def sanitize_data(df):
    """Limpa e valida os dados de entrada."""
    try:
        required_columns = ['ID', 'SINAL', 'DATA_HORA', 'ESTADO']
        if not all(col in df.columns for col in required_columns):
            st.error(f"Arquivo inválido. Colunas necessárias: {required_columns}")
            return pd.DataFrame()
        
        df = df.dropna(subset=required_columns)
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce').astype('Int64')
        df['DATA_HORA'] = pd.to_datetime(df['DATA_HORA'], errors='coerce')
        df['ESTADO'] = pd.to_numeric(df['ESTADO'], errors='coerce')
        df = df[df['ESTADO'].isin([0, 1])]
        return df.dropna()
    
    except Exception as e:
        st.error(f"Erro ao sanitizar dados: {str(e)}")
        return pd.DataFrame()

# Sua função de análise original (mantida)
def analisar_dados(df):
    # ... (mantenha todo o seu código original de análise aqui) ...
    return df_resultado, df_txt

# Interface principal
def main():
    if not check_password():
        st.stop()
    
    st.title("⚙️ Análise de Estados de Equipamentos")
    
    uploaded_file = st.file_uploader("Carregue o arquivo Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and validate_file(uploaded_file):
        try:
            df = pd.read_excel(uploaded_file)
            df = sanitize_data(df)  # Agora a função está definida
            
            if df.empty:
                st.warning("Nenhum dado válido após sanitização")
                return
            
            df_resultado, df_txt = analisar_dados(df)
            
            # ... (restante do seu código de exibição) ...
            
        except Exception as e:
            st.error(f"Erro no processamento: {str(e)}")

if __name__ == "__main__":
    main()
