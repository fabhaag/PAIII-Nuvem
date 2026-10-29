import json
import boto3
import pandas as pd
import io
import pg8000.dbapi
import urllib.parse

s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    try:
        # 1. Identifica o bucket e o ficheiro recém-chegado
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        file_key_encoded = event['Records'][0]['s3']['object']['key']
        file_key = urllib.parse.unquote_plus(file_key_encoded)
        
        # 2. Faz o download do ficheiro e extrai metadados do S3
        response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        file_content = response['Body'].read()
        metadados = response.get('Metadata', {})
        
        # 3. Descodifica os valores provenientes do Streamlit
        dispositivo = urllib.parse.unquote(metadados.get('dispositivo', ''))
        data_medicao = urllib.parse.unquote(metadados.get('data_med', ''))
        hora_medicao = urllib.parse.unquote(metadados.get('hora', ''))
        ordem = urllib.parse.unquote(metadados.get('ordem', ''))
        desenho = urllib.parse.unquote(metadados.get('desenho', ''))
        numero_peca = urllib.parse.unquote(metadados.get('peca', ''))
        cliente = urllib.parse.unquote(metadados.get('cliente', ''))
        metrologista = urllib.parse.unquote(metadados.get('metrologista', ''))
        mmc = urllib.parse.unquote(metadados.get('mmc', ''))
        fornecedor = urllib.parse.unquote(metadados.get('fornecedor', ''))
        teste = urllib.parse.unquote(metadados.get('teste', ''))
        temperatura = urllib.parse.unquote(metadados.get('temperatura', ''))

        # =========================================================================
        # PARTE 2: PROCESSAMENTO DA TABELA DE MEDIÇÕES
        # =========================================================================
        stream_corrigido = io.BytesIO(file_content)
        df_report = pd.read_excel(stream_corrigido, sheet_name="Report", header=12, engine="openpyxl")
        df_report = df_report.loc[:, ~df_report.columns.str.contains('^Unnamed')]
        df_report = df_report.dropna(subset=["Characteristic"])
        
        colunas_num = ["Actual", "Nominal", "Upper Tol", "Lower Tol"]
        for col in colunas_num:
            if col in df_report.columns:
                df_report[col] = pd.to_numeric(df_report[col], errors='coerce')
                
        df_report['Medida_Num'] = df_report.groupby('Characteristic').cumcount() + 1
        df_medidas = df_report.pivot(index='Characteristic', columns='Medida_Num', values='Actual').reset_index()
        
        if 1 in df_medidas.columns: df_medidas.rename(columns={1: 'Medida 1'}, inplace=True)
        else: df_medidas['Medida 1'] = None
        if 2 in df_medidas.columns: df_medidas.rename(columns={2: 'Medida 2'}, inplace=True)
        else: df_medidas['Medida 2'] = None
        
        df_limites = df_report.drop_duplicates(subset=['Characteristic'])[['Characteristic', 'Nominal', 'Upper Tol', 'Lower Tol']]
        df_final = pd.merge(df_limites, df_medidas, on='Characteristic')
        df_final['Média'] = df_final[['Medida 1', 'Medida 2']].mean(axis=1)
        
        # Avaliação de conformidade por linha e geral, com cálculo de desvio padrão
        df_final['desvio_padrao'] = df_final[['Medida 1', 'Medida 2']].std(axis=1).fillna(0)
        
        status_aprovado = []
        calibracao_sucesso = "Aprovado"
        
        for i, row in df_final.iterrows():
            nominal, upper_tol, lower_tol, media = row['Nominal'], row['Upper Tol'], row['Lower Tol'], row['Média']
            aprovado_linha = 1 # 1 para Aprovado
            if pd.notnull(nominal) and pd.notnull(media) and pd.notnull(upper_tol) and pd.notnull(lower_tol):
                limite_superior = nominal + upper_tol
                limite_inferior = nominal - lower_tol if lower_tol > 0 else nominal + lower_tol 
                if not (limite_inferior <= media <= limite_superior):
                    aprovado_linha = 0 # 0 para Reprovado
                    calibracao_sucesso = "Reprovado"
            
            status_aprovado.append(aprovado_linha)
            
        df_final['Aprovado'] = status_aprovado

        # =========================================================================
        # PARTE 3: INSERÇÃO NO BANCO DE DADOS (RDS)
        # =========================================================================
        conn = pg8000.dbapi.connect(
            host="database-1.cm1oydecnxjd.us-east-1.rds.amazonaws.com",
            database="postgres",
            user="postgres",
            password="12345678",
            port=5432
        )
        cursor = conn.cursor()
        
        # 1. Inserção na tabela metadados (incluindo Temperatura) com RETURNING id
        query_insercao_meta = """
            INSERT INTO metadados 
            (dispositivo_controle, data_medicao, hora_medicao, ordem, desenho, numero_peca, cliente, metrologista, mmc, fornecedor, teste, temperatura) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """
        valores_meta = (dispositivo, data_medicao, hora_medicao, ordem, desenho, numero_peca, cliente, metrologista, mmc, fornecedor, teste, temperatura)
        
        cursor.execute(query_insercao_meta, valores_meta)
        id_metadados = cursor.fetchone()[0]

        # 2. Cria o registo mestre na tabela Certificado e obtém o seu ID
        insert_certificado = """
            INSERT INTO Certificado (id_metadados, fator_k, incerteza_u, status_final) 
            VALUES (%s, %s, %s, %s) RETURNING id;
        """
        cursor.execute(insert_certificado, (id_metadados, 2.23, 0.002, calibracao_sucesso))
        id_certificado = cursor.fetchone()[0]
        
        # 3. Insere linha a linha cada característica/cota na tabela Parametros
        query_insercao = """
            INSERT INTO parametros (
                id_certificado, caracteristica, nominal, tolerancia_superior, 
                tolerancia_inferior, medida_1, medida_2, media, desvio_padrao, erro, aprovado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        for i, row in df_final.iterrows():
            carac = str(row['Characteristic'])
            nom = float(row['Nominal']) if pd.notna(row['Nominal']) else None
            tsup = float(row['Upper Tol']) if pd.notna(row['Upper Tol']) else None
            tinf = float(row['Lower Tol']) if pd.notna(row['Lower Tol']) else None
            m1 = float(row['Medida 1']) if pd.notna(row['Medida 1']) else None
            m2 = float(row['Medida 2']) if pd.notna(row['Medida 2']) else None
            media = float(row['Média']) if pd.notna(row['Média']) else None
            desvio = float(row['desvio_padrao']) if pd.notna(row['desvio_padrao']) else 0.0
            aprov = int(row['Aprovado'])
            erro = abs(media - nom) if (media is not None and nom is not None) else None
            
            cursor.execute(query_insercao, (id_certificado, carac, nom, tsup, tinf, m1, m2, media, desvio, erro, aprov))
            
        conn.commit()

        # 4. Aciona a AWS Lambda geradora de PDF de forma assíncrona
        payload = {"id_metadados": id_metadados} 
        lambda_client.invoke(
            FunctionName='lambda-gerador-pdf',
            InvocationType='Event',
            Payload=json.dumps(payload)
        )
        print(f"Função geradora de PDF acionada para o ID: {id_metadados}")
        
        return {"statusCode": 200, "body": json.dumps("ETL concluído e PDF em geração")}

    except Exception as e:
        print(f"Erro no processamento ETL: {e}")
        return {"statusCode": 500, "body": json.dumps(f"Erro interno: {str(e)}")}
        
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()