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

# Função de sanitização modificada para mostrar dados inválidos
def sanitize_data(df):
    """Limpa e valida os dados de entrada e retorna dados válidos e inválidos."""
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
            return pd.DataFrame(), df  # Retorna vazio para válidos e todos para inválidos
        
        # Faz cópias para não modificar o original
        df_valid = df.copy()
        df_invalid = df.copy()
        
        # Processa dados válidos
        df_valid['ID'] = pd.to_numeric(df_valid['ID'], errors='coerce')
        df_valid['DATA_HORA'] = pd.to_datetime(df_valid['DATA_HORA'], errors='coerce')
        df_valid['ESTADO'] = pd.to_numeric(df_valid['ESTADO'], errors='coerce')
        
        # Filtra dados válidos
        mask = (
            df_valid['ID'].notna() & 
            df_valid['DATA_HORA'].notna() & 
            df_valid['ESTADO'].notna() & 
            df_valid['ESTADO'].isin([0, 1])
        )
        
        df_valid = df_valid[mask].copy()
        df_invalid = df_invalid[~mask].copy()
        
        return df_valid, df_invalid
    
    except Exception as e:
        st.error(f"Erro durante sanitização: {str(e)}")
        return pd.DataFrame(), df

# Função principal de análise
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
            st.success(f"Dados carregados com sucesso! Total de registros: {len(df_raw)}")
            
            # Sanitizar os dados
            df_valid, df_invalid = sanitize_data(df_raw.copy())
            
            # Mostrar abas de visualização
            tab1, tab2 = st.tabs(["Dados Brutos", "Dados Inválidos"])
            
            with tab1:
                st.subheader("Dados Brutos")
                st.write("Visualização dos dados originais:")
                st.dataframe(df_raw)
            
            with tab2:
                st.subheader("Dados Inválidos")
                if df_invalid.empty:
                    st.success("Todos os dados são válidos!")
                else:
                    st.write("Registros que não atendem aos critérios de validação:")
                    st.dataframe(df_invalid)
                    
                    st.download_button(
                        label="Baixar Dados Inválidos (Excel)",
                        data=export_to_excel(df_invalid, 'Dados_Invalidos'),
                        file_name="dados_invalidos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            # Seção de análise (sempre visível após upload)
            st.markdown("---")
            st.subheader("Análise de Dados")
            
            if df_valid.empty:
                st.error("Nenhum dado válido para análise")
            else:
                # Executar análise automaticamente
                with st.spinner("Processando dados válidos..."):
                    df_resultado, df_txt = analisar_dados(df_valid)
                
                # Mostrar resultados
                st.write(f"Períodos com duração superior a 3 minutos encontrados: {len(df_resultado)}")
                
                # Exibir tabela de resultados
                st.dataframe(df_resultado)
                
                # Seção de exportação
                st.subheader("Exportar Resultados")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="Baixar Resultados em Excel",
                        data=export_to_excel(df_resultado, 'Resumo_Tempos_Ligado'),
                        file_name="Resumo_Tempos_Ligado.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                with col2:
                    output_txt = io.StringIO()
                    df_txt.to_csv(output_txt, index=False, header=False, lineterminator='\n')
                    st.download_button(
                        label="Baixar Eventos em TXT",
                        data=output_txt.getvalue(),
                        file_name="Estados_Equipamentos.txt",
                        mime="text/plain"
                    )
                
                # Estatísticas
                st.subheader("Estatísticas")
                col1, col2, col3 = st.columns(3)
                col1.metric("Total de Períodos", len(df_resultado))
                col2.metric("Duração Média (min)", round(df_resultado['Duração (minutos)'].mean(), 2))
                col3.metric("Duração Máxima (min)", round(df_resultado['Duração (minutos)'].max(), 2))
        
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {str(e)}")

if __name__ == "__main__":
    main()
