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

# Função de autenticação
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

# Função para converter para datetime seguro
def safe_to_datetime(date_series):
    """Converte uma série para datetime de forma segura."""
    if pd.api.types.is_datetime64_any_dtype(date_series):
        return date_series
    return pd.to_datetime(date_series, errors='coerce')

# Função para identificar dados inválidos
def get_invalid_data(df_raw, df_valid, df_resultado):
    """Identifica todos os dados que foram descartados na análise."""
    df_invalid = df_raw.copy()
    df_invalid['VALIDADO'] = False
    df_invalid['MOTIVO_INVALIDO'] = ''
    
    # Converte datas
    df_invalid['DATA_HORA'] = safe_to_datetime(df_invalid['DATA_HORA'])
    
    # 1. Marca registros com problemas de validação básica
    mask_invalid = (
        df_invalid['ID'].isna() |
        df_invalid['SINAL'].isna() |
        df_invalid['DATA_HORA'].isna() |
        ~df_invalid['ESTADO'].isin([0, 1])
    )
    
    df_invalid.loc[mask_invalid, 'MOTIVO_INVALIDO'] = 'Dados faltantes ou inválidos'
    
    # 2. Para registros válidos que não estão nos resultados (períodos <3min)
    if not df_resultado.empty:
        # Cria lista de todos os períodos válidos
        valid_periods = []
        for _, periodo in df_resultado.iterrows():
            start = pd.to_datetime(periodo['Início Ligado'])
            end = pd.to_datetime(periodo['Fim Ligado'])
            valid_periods.append((start, end))
        
        # Marca registros que não estão em nenhum período válido
        for idx, row in df_invalid.iterrows():
            if row['MOTIVO_INVALIDO'] == '':
                in_valid_period = False
                current_time = row['DATA_HORA']
                
                if pd.isna(current_time):
                    continue
                
                for start, end in valid_periods:
                    if start <= current_time <= end:
                        in_valid_period = True
                        break
                
                if not in_valid_period:
                    df_invalid.at[idx, 'MOTIVO_INVALIDO'] = 'Período menor que 3 minutos'
    
    # Filtra apenas os inválidos
    df_invalid = df_invalid[df_invalid['MOTIVO_INVALIDO'] != '']
    
    return df_invalid[['ID', 'SINAL', 'DATA_HORA', 'ESTADO', 'MOTIVO_INVALIDO']]

# Função de sanitização
def sanitize_data(df):
    """Limpa e valida os dados de entrada."""
    try:
        # Mapeamento de colunas alternativas
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
        
        # Conversão de tipos
        df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        df['DATA_HORA'] = safe_to_datetime(df['DATA_HORA'])
        df['ESTADO'] = pd.to_numeric(df['ESTADO'], errors='coerce')
        
        # Filtra dados válidos
        mask = (
            df['ID'].notna() & 
            df['SINAL'].notna() & 
            df['DATA_HORA'].notna() & 
            df['ESTADO'].isin([0, 1])
        )
        
        return df[mask].copy()
    
    except Exception as e:
        st.error(f"Erro durante sanitização: {str(e)}")
        return pd.DataFrame()

# Função principal de análise
def analisar_dados(df):
    """Analisa os períodos de funcionamento dos equipamentos."""
    df['DATA_HORA'] = safe_to_datetime(df['DATA_HORA'])
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

# Função para exportar Excel
def export_to_excel(df, sheet_name='Sheet1'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# Interface principal
def main():
    if not check_password():
        st.stop()
    
    st.title("⚙️ Análise de Estados de Equipamentos")
    st.markdown("""
    Esta aplicação analisa os períodos de funcionamento dos equipamentos com base nos dados de estado (0=OFF, 1=ON).
    """)
    st.markdown("---")
    
    # Upload do arquivo
    uploaded_file = st.file_uploader("Carregue o arquivo Excel com os dados", type=['xlsx'])
    
    if uploaded_file is not None:
        try:
            # Ler os dados
            df_raw = pd.read_excel(uploaded_file, sheet_name="Sheet1")
            df_raw['DATA_HORA'] = safe_to_datetime(df_raw['DATA_HORA'])
            
            st.success(f"Dados carregados com sucesso! Total de registros: {len(df_raw)}")
            
            # Mostrar dados brutos
            with st.expander("Visualizar Dados Brutos"):
                st.dataframe(df_raw)
            
            # Sanitizar os dados
            df_valid = sanitize_data(df_raw.copy())
            
            # Botão para acionar a análise
            if st.button("Analisar Dados", type="primary"):
                if df_valid.empty:
                    st.error("Nenhum dado válido para análise")
                else:
                    with st.spinner("Processando dados..."):
                        # Executar análise e armazenar na sessão
                        st.session_state.df_resultado, st.session_state.df_txt = analisar_dados(df_valid)
                        st.session_state.df_invalid = get_invalid_data(df_raw.copy(), df_valid, st.session_state.df_resultado)
            
            # Mostrar resultados se existirem na sessão
            if 'df_resultado' in st.session_state:
                # Mostrar seção de dados inválidos
                st.subheader("Dados Invalidados")
                if st.session_state.df_invalid.empty:
                    st.success("Todos os dados foram considerados válidos!")
                else:
                    st.write(f"Total de registros invalidados: {len(st.session_state.df_invalid)}")
                    st.dataframe(st.session_state.df_invalid)
                    
                    st.download_button(
                        label="Baixar Dados Invalidados (Excel)",
                        data=export_to_excel(st.session_state.df_invalid, 'Dados_Invalidos'),
                        file_name="dados_invalidos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                # Mostrar resultados da análise
                st.markdown("---")
                st.subheader("Resultados da Análise")
                
                if st.session_state.df_resultado.empty:
                    st.warning("Nenhum período válido encontrado")
                else:
                    st.write(f"Períodos com duração superior a 3 minutos encontrados: {len(st.session_state.df_resultado)}")
                    st.dataframe(st.session_state.df_resultado)
                    
                    # Seção de exportação (sempre disponível após análise)
                    st.subheader("Exportar Resultados")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.download_button(
                            label="Baixar Resultados em Excel",
                            data=export_to_excel(st.session_state.df_resultado, 'Resumo_Tempos_Ligado'),
                            file_name="Resumo_Tempos_Ligado.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    with col2:
                        output_txt = io.StringIO()
                        st.session_state.df_txt.to_csv(output_txt, index=False, header=False, lineterminator='\n')
                        st.download_button(
                            label="Baixar Eventos em TXT",
                            data=output_txt.getvalue(),
                            file_name="Estados_Equipamentos.txt",
                            mime="text/plain"
                        )
                    
                    # Estatísticas
                    st.subheader("Estatísticas")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total de Períodos", len(st.session_state.df_resultado))
                    col2.metric("Duração Média (min)", round(st.session_state.df_resultado['Duração (minutos)'].mean(), 2))
                    col3.metric("Duração Máxima (min)", round(st.session_state.df_resultado['Duração (minutos)'].max(), 2))
        
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {str(e)}")

if __name__ == "__main__":
    main()
