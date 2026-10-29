import streamlit as st
import pandas as pd
import numpy as np
import boto3
import io
import urllib.parse
import zipfile
import time


st.set_page_config(page_title="Gerador de Certificados CMM - Nuvem", layout="wide")

# Dicionários e Função de Reparação (Mantenha as suas originais)
STRICT_NS = "http://openxmlformats.org"
TRANS_NS = "http://openxmlformats.org"
OPCOES_CLIENTE = ["Metrologia", "Usinagem", "Pintura", "Compressores", "Lab. Fundição", "Fund.", "Unid. 3"]
OPCOES_METROLOGISTA = ["José Alcides Rosa Jr", "Cleocir de Souza"]
OPCOES_MMC = ["500.008", "500.009", "500.011", "500.012", "500.015"]
OPCOES_FORNECEDOR = ["CDM", "Usifer", "Torque", "Valente"]

def repair_xlsx_stream(in_bytes):
    in_buf = io.BytesIO(in_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            data = z_in.read(item.filename)
            if item.filename.endswith(".xml"):
                data = data.decode("utf-8").replace(STRICT_NS, TRANS_NS).encode("utf-8")
            z_out.writestr(item, data)
    out_buf.seek(0)
    return out_buf

st.title("Automação de Certificados CMM - Cloud")
st.markdown("---")

uploaded_file = st.file_uploader("Carregar Planilha de Medições (Excel)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        # 1. PRÉ-PROCESSAMENTO LOCAL PARA VISUALIZAÇÃO
        stream_corrigido = repair_xlsx_stream(uploaded_file.getvalue())
        df_topo = pd.read_excel(stream_corrigido, sheet_name="Report", nrows=12, header=None, engine="openpyxl")
        
        # Extração primária
        disp_ext = str(df_topo.iloc[4, 1]) if pd.notna(df_topo.iloc[4, 1]) else ""
        data_ext = str(df_topo.iloc[4, 3]).split()[0] if pd.notna(df_topo.iloc[4, 3]) else ""
        ordem_ext = str(df_topo.iloc[4, 5]) if pd.notna(df_topo.iloc[4, 5]) else ""
        desenho_ext = str(df_topo.iloc[7, 1]) if pd.notna(df_topo.iloc[7, 1]) else ""
        hora_ext = str(df_topo.iloc[7, 3]) if pd.notna(df_topo.iloc[7, 3]) else ""
        peca_ext = str(df_topo.iloc[7, 5]) if pd.notna(df_topo.iloc[7, 5]) else ""
        
        st.markdown("### Quadro 1 - Metadados")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            teste = st.text_input("Teste", value="")
            temp = st.text_input("Temperatura (°C)", value="20")
            cliente = st.selectbox("Cliente", options=OPCOES_CLIENTE, index=1)
        with col2:
            dispositivo = st.text_input("Dispositivo de Controle", value=disp_ext)
            desenho = st.text_input("Desenho", value=desenho_ext)
            metro = st.selectbox("Metrologista", options=OPCOES_METROLOGISTA, index=0)
        with col3:
            data_med = st.text_input("Data (dd/mm/aaaa)", value=data_ext)
            hora = st.text_input("Hora (HH:MM)", value=hora_ext)
            mmc_sel = st.selectbox("MMC", options=OPCOES_MMC, index=2)
        with col4:
            ordem = st.text_input("Ordem", value=ordem_ext)
            peca = st.text_input("Numero peça", value=peca_ext)
            fornecedor = st.selectbox("Fornecedor", options=OPCOES_FORNECEDOR, index=0)

        # 2. PROCESSAMENTO DA TABELA PARA PRÉ-VISUALIZAÇÃO
        stream_corrigido.seek(0)
        df_report = pd.read_excel(stream_corrigido, sheet_name="Report", header=12, engine="openpyxl")
        df_report = df_report.loc[:, ~df_report.columns.str.contains('^Unnamed')].dropna(subset=["Characteristic"])
        
        for col in ["Actual", "Nominal", "Upper Tol", "Lower Tol"]:
            if col in df_report.columns:
                df_report[col] = pd.to_numeric(df_report[col], errors='coerce')

        df_report['Medida_Num'] = df_report.groupby('Characteristic').cumcount() + 1
        df_medidas = df_report.pivot(index='Characteristic', columns='Medida_Num', values='Actual').reset_index()
        
        if 1 in df_medidas.columns: df_medidas.rename(columns={1: 'Medida 1'}, inplace=True)
        else: df_medidas['Medida 1'] = np.nan
        if 2 in df_medidas.columns: df_medidas.rename(columns={2: 'Medida 2'}, inplace=True)
        else: df_medidas['Medida 2'] = np.nan

        df_limites = df_report.drop_duplicates(subset=['Characteristic'])[['Characteristic', 'Nominal', 'Upper Tol', 'Lower Tol']]
        df_final = pd.merge(df_limites, df_medidas, on='Characteristic')
        df_final['Média'] = df_final[['Medida 1', 'Medida 2']].mean(axis=1)

        status_aprovado = []
        for i, row in df_final.iterrows():
            nom, ut, lt, med = row['Nominal'], row['Upper Tol'], row['Lower Tol'], row['Média']
            aprovado = True
            if pd.notnull(nom) and pd.notnull(med) and pd.notnull(ut) and pd.notnull(lt):
                l_sup = nom + ut
                l_inf = nom - lt if lt > 0 else nom + lt 
                if not (l_inf <= med <= l_sup): aprovado = False
            status_aprovado.append(aprovado)
        df_final['Aprovado'] = status_aprovado

        st.markdown("### Quadro 2 – Parâmetros, aprovação e certificado")
        def color_rows(row):
            color = '#c8e6c9' if row['Aprovado'] else '#ffcdd2'
            return [f'background-color: {color}; color: black' for _ in row]

        st.dataframe(df_final.style.apply(color_rows, axis=1).format("{:.3f}", na_rep="-", subset=["Nominal", "Upper Tol", "Lower Tol", "Medida 1", "Medida 2", "Média"]), use_container_width=True, hide_index=True)
        
        # 3. ENVIO PARA A NUVEM
        if st.button("Confirmar e Processar na Nuvem", type="primary"):
            
            with st.spinner('A processar e a aguardar a geração do certificado pela AWS (pode demorar alguns segundos)...'):
                try:
                    s3_client = boto3.client('s3')

                    # 1. Envio dos metadados e planilha
                 
                        # Codifica os metadados para evitar erros com acentos no S3
                    meta_custom = {
                        'cliente': urllib.parse.quote(cliente),
                        'fornecedor': urllib.parse.quote(fornecedor),
                        'metrologista': urllib.parse.quote(metro),
                        'mmc': urllib.parse.quote(mmc_sel),
                        'temperatura': urllib.parse.quote(temp),
                        'teste': urllib.parse.quote(teste),
                        'dispositivo': urllib.parse.quote(dispositivo),
                        'desenho': urllib.parse.quote(desenho),
                        'data_med': urllib.parse.quote(data_med),
                        'hora': urllib.parse.quote(hora),
                        'ordem': urllib.parse.quote(ordem),
                        'peca': urllib.parse.quote(peca)
                    }

                    s3_client.put_object(
                        Bucket="schulz-raw-data-grupo41",
                        Key=uploaded_file.name,
                        Body=uploaded_file.getvalue(),
                        Metadata=meta_custom
                    )
                    
                    
                    # 2. Configuração de Busca
                    bucket_pdf_saida = "schulz-pdf-certificates-grupo41"
                    chave_pdf_saida = f"Certificado_{dispositivo}_{data_med.replace('/', '-')}.pdf"

                    # Elimina o PDF antigo para evitar o download de ficheiros desatualizados
                    try:
                        s3_client.delete_object(Bucket=bucket_pdf_saida, Key=chave_pdf_saida)
                    except Exception:
                        pass
                    
                    pdf_bytes = None
                    tentativas = 15 # Tempo máximo de espera# 2. Configuração de Busca
                    bucket_pdf_saida = "schulz-pdf-certificates-grupo41"
                    chave_pdf_saida = f"Certificado_{dispositivo}_{data_med}.pdf"

                    # Elimina o PDF antigo para evitar o download de ficheiros desatualizados
                    try:
                        s3_client.delete_object(Bucket=bucket_pdf_saida, Key=chave_pdf_saida)
                    except Exception:
                        pass
    
                    
                    
                    pdf_bytes = None
                    tentativas = 15 # Tempo máximo de espera: ~30 segundos
                    
                    # 3. Polling: Procura o ficheiro no S3 a cada 2 segundos
                    for _ in range(tentativas):
                        try:
                            resposta = s3_client.get_object(Bucket=bucket_pdf_saida, Key=chave_pdf_saida)
                            pdf_bytes = resposta['Body'].read()
                            break # PDF encontrado, interrompe a busca
                        except s3_client.exceptions.NoSuchKey:
                            time.sleep(2) 
                    
                    # 4. Disponibilização do botão na Interface
                    if pdf_bytes:
                        st.success("Metadados confirmados! O certificado foi gerado com sucesso.")
                        st.download_button(
                            label="Baixar Certificado PDF",
                            data=pdf_bytes,
                            file_name=chave_pdf_saida,
                            mime="application/pdf",
                            type="primary"
                        )
                    else:
                        st.warning("O tempo limite de espera esgotou. O PDF ainda está em processamento na nuvem.")

                except Exception as e:
                    st.error(f"Erro na comunicação com a AWS: {e}")

    # Este bloco fecha o 'try' principal da leitura do ficheiro (linhas 36/37)
    except Exception as e:
        st.error(f"Erro ao processar a planilha: {e}")