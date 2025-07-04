import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# Configuração da página
st.set_page_config(
    page_title="Análise de Estados de Equipamentos",
    page_icon="⚙️",
    layout="wide"
)

# Título da aplicação
st.title("⚙️ Análise de Estados de Equipamentos")
st.markdown("""
Esta aplicação analisa os períodos de funcionamento dos equipamentos com base nos dados de estado (0=OFF, 1=ON).
""")
st.markdown("---")

# Função principal de análise (adaptada do seu script)
def analisar_dados(df):
    # Converter a coluna de data/hora
    df['DATA_HORA'] = pd.to_datetime(df['DATA_HORA'])
    
    # Ordenar por ID, SINAL e data/hora
    df = df.sort_values(by=["ID", "SINAL", "DATA_HORA"]).reset_index(drop=True)
    
    # Lista para guardar períodos de ligado
    periodos_ligado = []
    eventos_txt = []
    
    # Agrupar por equipamento (ID + SINAL)
    for (id_val, sinal), grupo in df.groupby(["ID", "SINAL"]):
        grupo = grupo.reset_index(drop=True)
        ligado = None  # marca o início do período ligado
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
                    # Guardar os eventos para o arquivo TXT
                    eventos_txt.append(linha_on)
                    eventos_txt.append(f"{int(row['ID'])};OFF;{desligado.strftime('%Y-%m-%d %H:%M:%S.000')}")
                ligado = None
                linha_on = None
    
    # Criar DataFrames com os resultados
    df_resultado = pd.DataFrame(periodos_ligado)
    df_txt = pd.DataFrame(eventos_txt, columns=["Evento"])
    
    return df_resultado, df_txt

# Interface principal
def main():
    # Upload do arquivo
    uploaded_file = st.file_uploader("Carregue o arquivo Excel com os dados", type=['xlsx'])
    
    if uploaded_file is not None:
        try:
            # Ler os dados
            df = pd.read_excel(uploaded_file, sheet_name="Sheet1")
            st.success(f"Dados carregados com sucesso! Total de registros: {len(df)}")
            
            # Mostrar prévia dos dados
            with st.expander("Visualizar dados brutos"):
                st.dataframe(df.head())
            
            # Executar análise quando o botão for clicado
            if st.button("Analisar Dados", type="primary"):
                with st.spinner("Processando dados..."):
                    df_resultado, df_txt = analisar_dados(df)
                
                # Mostrar resultados
                st.subheader("Resultados da Análise")
                st.write(f"Períodos com duração superior a 3 minutos encontrados: {len(df_resultado)}")
                
                # Exibir tabela de resultados
                st.dataframe(df_resultado)
                
                # Criar arquivos para download
                st.subheader("Exportar Resultados")
                
                # Excel
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    df_resultado.to_excel(writer, index=False, sheet_name='Resumo_Tempos_Ligado')
                st.download_button(
                    label="Baixar Resultados em Excel",
                    data=output_excel.getvalue(),
                    file_name="Resumo_Tempos_Ligado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # TXT
                output_txt = io.StringIO()
                df_txt.to_csv(output_txt, index=False, header=False, line_terminator='\n')
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