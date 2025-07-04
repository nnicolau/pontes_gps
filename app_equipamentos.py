import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import hashlib
import bcrypt
import os
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# Configuração de segurança
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.warning("dotenv não está instalado. Usando variáveis padrão.")

# Configurações de segurança
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key-123')
PASSWORD_HASH = os.getenv('PASSWORD_HASH', '')

# Funções de Segurança (mantidas iguais)
def check_password():
    """Verifica se o usuário digitou a senha correta."""
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        return True
    
    password = st.text_input("Senha de acesso", type="password", key="password_input")
    
    if password:
        if bcrypt.checkpw(password.encode(), PASSWORD_HASH.encode()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    
    return False

def validate_file(file):
    """Validação detalhada do arquivo de entrada."""
    if not file:
        return False
        
    if file.size > 10 * 1024 * 1024:
        st.error("Arquivo muito grande (máximo 10MB)")
        return False
        
    if not file.name.endswith(('.xlsx', '.xls')):
        st.error("Formato inválido. Use .xlsx ou .xls")
        return False
    
    try:
        pd.read_excel(file, nrows=5)
        return True
    except Exception as e:
        st.error(f"Arquivo corrompido ou inválido: {str(e)}")
        return False

# Função de Sanitização (mantida igual)
def sanitize_data(df):
    """Limpa e valida os dados de entrada."""
    try:
        column_mapping = {
            'id': 'ID',
            'sinal': 'SINAL',
            'data_hora': 'DATA_HORA',
            'estado': 'ESTADO'
        }
        df = df.rename(columns=lambda x: column_mapping.get(str(x).lower(), x))
        
        required_columns = ['ID', 'SINAL', 'DATA_HORA', 'ESTADO']
        if not all(col in df.columns for col in required_columns):
            st.error(f"Colunas obrigatórias faltando: {required_columns}")
            return pd.DataFrame()
        
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        df['DATA_HORA'] = pd.to_datetime(df['DATA_HORA'], errors='coerce')
        df['ESTADO'] = pd.to_numeric(df['ESTADO'], errors='coerce')
        
        df = df.dropna(subset=required_columns)
        df = df[df['ESTADO'].isin([0, 1])]
        
        return df
    
    except Exception as e:
        st.error(f"Erro durante sanitização: {str(e)}")
        return pd.DataFrame()

# Função de Análise (mantida igual)
def analisar_dados(df):
    """Analisa os períodos de funcionamento dos equipamentos."""
    df = df.sort_values(by=["ID", "SINAL", "DATA_HORA"]).reset_index(drop=True)
    
    periodos_ligado = []
    eventos_txt = []
    
    for (id_val, sinal), grupo in df.groupby(["ID", "SINAL"]):
        grupo = grupo.reset_index(drop=True)
        ligado = None
        linha_on = None

        for i, row in grupo.iterrows():
            if row['ESTADO'] == 1:
                ligado = row['DATA_HORA']
                linha_on = f"{int(row['ID'])};ON;{ligado.strftime('%Y-%m-%d %H:%M:%S.000')}"
            elif row['ESTADO'] == 0 and ligado:
                desligado = row['DATA_HORA']
                duracao = desligado - ligado
                minutos = duracao.total_seconds() / 60
                if minutos > 3:
                    periodos_ligado.append({
                        "ID": id_val,
                        "Equipamento": sinal,
                        "Início Ligado": ligado,
                        "Fim Ligado": desligado,
                        "Duração (minutos)": round(minutos, 2)
                    })
                    eventos_txt.append(linha_on)
                    eventos_txt.append(f"{int(row['ID'])};OFF;{desligado.strftime('%Y-%m-%d %H:%M:%S.000')}")
                ligado = None
                linha_on = None
    
    df_resultado = pd.DataFrame(periodos_ligado)
    df_txt = pd.DataFrame(eventos_txt, columns=["Evento"])
    
    return df_resultado, df_txt

# Função para exportar Excel com OpenPyXL (mantida igual)
def export_to_excel(df):
    """Exporta DataFrame para Excel usando OpenPyXL."""
    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    
    wb.save(output)
    return output.getvalue()

# Interface Principal (modificada para mostrar dados brutos)
def main():
    if not check_password():
        st.stop()
    
    st.title("⚙️ Análise de Estados de Equipamentos")
    
    uploaded_file = st.file_uploader("Carregue o arquivo Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and validate_file(uploaded_file):
        try:
            # Leitura dos dados
            with st.spinner("Carregando dados..."):
                df_raw = pd.read_excel(uploaded_file)
                df = sanitize_data(df_raw)
            
            if df is None or df.empty:
                st.error("Não foi possível processar os dados. Verifique o formato do arquivo.")
                return
            
            # Cria abas para visualização
            tab1, tab2 = st.tabs(["📊 Dados Brutos", "📈 Resultados da Análise"])
            
            with tab1:
                st.subheader("Dados Brutos Completos")
                st.write(f"Total de registros: {len(df_raw)}")
                
                # Mostra dados brutos com filtros
                st.dataframe(df_raw, height=500)
                
                # Estatísticas dos dados brutos
                st.subheader("Estatísticas dos Dados Brutos")
                if 'ID' in df_raw.columns:
                    st.write(f"Equipamentos únicos: {df_raw['ID'].nunique()}")
                if 'DATA_HORA' in df_raw.columns:
                    st.write(f"Período coberto: {df_raw['DATA_HORA'].min()} a {df_raw['DATA_HORA'].max()}")
                
                # Download dos dados brutos
                st.download_button(
                    label="📥 Baixar Dados Brutos (Excel)",
                    data=export_to_excel(df_raw),
                    file_name="dados_brutos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with tab2:
                # Análise dos dados
                with st.spinner("Analisando dados..."):
                    df_resultado, df_txt = analisar_dados(df)
                
                st.subheader("Resultados da Análise")
                
                if df_resultado.empty:
                    st.warning("Nenhum período de funcionamento encontrado")
                else:
                    st.write(f"Total de períodos encontrados: {len(df_resultado)}")
                    
                    # Mostra resultados com filtros
                    st.dataframe(df_resultado, height=400)
                    
                    # Gráfico de duração dos períodos
                    st.subheader("Distribuição das Durações")
                    st.bar_chart(df_resultado['Duração (minutos)'].value_counts())
                    
                    # Exportação dos resultados
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="📥 Baixar Resultados (Excel)",
                            data=export_to_excel(df_resultado),
                            file_name="resultados_analise.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    with col2:
                        output_txt = io.StringIO()
                        df_txt.to_csv(output_txt, index=False, header=False, lineterminator='\n')
                        st.download_button(
                            label="📥 Baixar Eventos (TXT)",
                            data=output_txt.getvalue(),
                            file_name="eventos_equipamentos.txt",
                            mime="text/plain"
                        )
                    
                    # Estatísticas
                    st.subheader("Estatísticas")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Períodos", len(df_resultado))
                    col2.metric("Duração Média (min)", f"{df_resultado['Duração (minutos)'].mean():.1f}")
                    col3.metric("Duração Máxima (min)", f"{df_resultado['Duração (minutos)'].max():.1f}")
        
        except Exception as e:
            st.error(f"Erro no processamento: {str(e)}")

if __name__ == "__main__":
    main()
