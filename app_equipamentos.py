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

# Configurações de segurança
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key-123')
PASSWORD_HASH = os.getenv('PASSWORD_HASH', '')

# Funções de Segurança
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
        
    if file.size > 10 * 1024 * 1024:  # 10MB
        st.error("Arquivo muito grande (máximo 10MB)")
        return False
        
    if not file.name.endswith(('.xlsx', '.xls')):
        st.error("Formato inválido. Use .xlsx ou .xls")
        return False
    
    try:
        # Testa leitura rápida do arquivo
        pd.read_excel(file, nrows=5)
        return True
    except Exception as e:
        st.error(f"Arquivo corrompido ou inválido: {str(e)}")
        return False

# Função de Sanitização Melhorada
def sanitize_data(df):
    """Limpa e valida os dados de entrada com tratamento robusto."""
    try:
        # Mapeamento de colunas alternativas
        column_mapping = {
            'id': 'ID',
            'sinal': 'SINAL',
            'data_hora': 'DATA_HORA',
            'estado': 'ESTADO',
            'signal': 'SINAL',
            'date_time': 'DATA_HORA',
            'status': 'ESTADO'
        }
        df = df.rename(columns=lambda x: column_mapping.get(str(x).lower(), x))
        
        # Verifica colunas obrigatórias
        required_columns = ['ID', 'SINAL', 'DATA_HORA', 'ESTADO']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            st.error(f"Colunas obrigatórias faltando: {missing}")
            return pd.DataFrame()
        
        # Debug: mostra dados brutos
        with st.expander("Visualização dos Dados Brutos"):
            st.write("Colunas recebidas:", df.columns.tolist())
            st.write("Amostra dos dados brutos:", df.head())
            st.write("Tipos de dados brutos:", df.dtypes)

        # Conversão segura de tipos
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        df['DATA_HORA'] = pd.to_datetime(df['DATA_HORA'], errors='coerce')
        
        # Mapeamento de estados diversos
        state_mapping = {
            'LIGADO': 1, 'DESLIGADO': 0,
            'ON': 1, 'OFF': 0,
            '1': 1, '0': 0,
            1: 1, 0: 0,
            'ATIVO': 1, 'INATIVO': 0,
            'LIG': 1, 'DESL': 0
        }
        df['ESTADO'] = df['ESTADO'].map(state_mapping)
        
        # Remove linhas inválidas
        initial_count = len(df)
        df = df.dropna(subset=required_columns)
        df = df[df['ESTADO'].notna()]
        final_count = len(df)
        
        # Debug: mostra resultados da sanitização
        st.write(f"Linhas antes da sanitização: {initial_count}")
        st.write(f"Linhas após sanitização: {final_count}")
        st.write(f"Linhas removidas: {initial_count - final_count}")
        
        if not df.empty:
            with st.expander("Visualização dos Dados Sanitizados"):
                st.write(df.head())
            return df
        else:
            st.error("Nenhum dado válido após sanitização. Verifique os logs acima.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Erro durante sanitização: {str(e)}")
        return pd.DataFrame()

# Função de Análise Principal (mantida conforme seu original)
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

# Interface Principal
def main():
    if not check_password():
        st.stop()
    
    st.title("⚙️ Análise de Estados de Equipamentos (Seguro)")
    
    uploaded_file = st.file_uploader("Carregue o arquivo Excel com os dados", type=['xlsx', 'xls'])
    
    if uploaded_file and validate_file(uploaded_file):
        try:
            # Leitura e sanitização
            with st.spinner("Processando arquivo..."):
                df_raw = pd.read_excel(uploaded_file)
                df = sanitize_data(df_raw)
            
            if df is None or df.empty:
                st.error("Não foi possível processar os dados. Verifique os logs acima.")
                return
            
            # Análise dos dados
            with st.spinner("Analisando dados..."):
                df_resultado, df_txt = analisar_dados(df)
            
            # Exibição de resultados
            st.subheader("Resultados da Análise")
            
            if df_resultado.empty:
                st.warning("Nenhum período de funcionamento encontrado")
            else:
                st.write(f"Total de períodos encontrados: {len(df_resultado)}")
                st.dataframe(df_resultado)
                
                # Exportação Excel
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    df_resultado.to_excel(writer, index=False, sheet_name='Resultados')
                st.download_button(
                    label="📥 Baixar Resultados (Excel)",
                    data=output_excel.getvalue(),
                    file_name="resultados_analise.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # Exportação TXT
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
