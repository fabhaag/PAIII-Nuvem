import json
import boto3
import io
import pg8000.dbapi
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    # 1. Configurações de Conexão com o RDS
    rds_host = "database-1.cm1oydecnxjd.us-east-1.rds.amazonaws.com"
    db_user = "postgres"
    db_password = "12345678" # Recomenda-se usar AWS Secrets Manager em produção
    db_name = "postgres"
    
    try:
        conn = pg8000.dbapi.connect(

            host="database-1.cm1oydecnxjd.us-east-1.rds.amazonaws.com",
            database="postgres",
            user="postgres",
            password="12345678",
            port=5432 # Nota: No pg8000 a porta deve ser um número inteiro, sem aspas
        )
        cursor = conn.cursor()
        
        # 2. Buscar o último certificado processado (ou usar um ID recebido no evento)
        id_metadados = event.get('id_metadados')
        
        if id_metadados:
            cursor.execute("SELECT * FROM Metadados WHERE id = %s;", (id_metadados,))
        else:
            cursor.execute("SELECT * FROM Metadados ORDER BY id DESC LIMIT 1;")
            
        metadados = cursor.fetchone()
        
        if not metadados:
            return {"statusCode": 404, "body": "Nenhum metadado encontrado."}
            
        # Mapeamento do resultado do banco (ajuste os índices conforme a sua tabela)
        id_meta, dispositivo, data_med, hora, ordem, desenho, num_peca, cliente, metro, mmc, forn, temp = metadados
        
        # Busca parâmetros vinculados a este metadado
        # Assumindo que a tabela Certificado liga Metadados e Parametros
        cursor.execute("SELECT id, fator_k, incerteza_u, status_final FROM Certificado WHERE id_metadados = %s;", (id_meta,))
        certificado = cursor.fetchone()
        id_cert, val_k, val_u, status_final = certificado if certificado else (None, 2.23, 0.002, "N/A")
        
        cursor.execute("SELECT caracteristica, nominal, tolerancia_superior, tolerancia_inferior, media, erro FROM Parametros WHERE id_certificado = %s;", (id_cert,))
        parametros = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # 3. Geração do PDF em Memória (ReportLab)
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        
        styles = getSampleStyleSheet()
        style_title = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], alignment=1)
        style_normal = styles['Normal']
        style_bold = ParagraphStyle(name='BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold')
        
        elementos = []
        
        # Inserção da imagem superior centralizada (ajustada para largura útil da página A4 de 18cm)
        try:
            # IMPORTANTE: Substitua 'nome_da_sua_imagem.png' pelo caminho correto do arquivo
            img = Image('/var/task/images/BarraSuperior.jpeg', width=18*cm, height=1.82*cm)
            img.hAlign = 'CENTER'
            elementos.append(img)
            elementos.append(Spacer(1, 12))
        except Exception as e:
            print(f"ERRO AO CARREGAR IMAGEM: {e}")

        
        ano = datetime.now().strftime("%Y")
        ordem_str = ordem if ordem is not None else ""
        elementos.append(Paragraph(f"<b>Certificado de Calibração nº {ordem_str}/{ano}</b>   Data: {data_med}", style_title))
        elementos.append(Paragraph(f"<b>Solicitante:</b> {cliente}", style_normal))
        elementos.append(Spacer(1, 12))
        
        elementos.append(Paragraph("<b>1. Descrição do instrumento calibrado</b>", style_bold))
        elementos.append(Paragraph("Denominação: Dispositivo de controle", style_normal))
        elementos.append(Paragraph(f"Código: {dispositivo}", style_normal))
        elementos.append(Paragraph(f"Fabricante: {forn}", style_normal))
        elementos.append(Spacer(1, 12))
        
        elementos.append(Paragraph("<b>2. Padrão utilizado</b>", style_bold))
        elementos.append(Paragraph(f"Máquina de medição por coordenadas {mmc} - Carl Zeiss", style_normal))
        elementos.append(Paragraph(f"Certificado de Calibração n° 241120502390 - Carl Zeiss; de 20/11/2024 - Próxima Calibração: 31/08/2026", style_normal))
        elementos.append(Spacer(1, 12))

        elementos.append(Paragraph("<b>3. Procedimento de calibração</b>", style_bold))
        elementos.append(Paragraph("Nr. do procedimento / revisão: Calibração de dispositivo de controle - ITL-0026 (revisão 2).", style_normal))
        elementos.append(Paragraph("O instrumento foi medido na máquina de medição por coordenadas através de elementos geométricos definidos, sendo o resultado apresentado a média de duas medições realizadas.", style_normal))
        elementos.append(Paragraph("Os resultados estão referenciados a temperatura de 20° Celsius.", style_normal))
        elementos.append(Spacer(1, 12))
        
        elementos.append(Paragraph("<b>3. Resultados (mm)</b>", style_bold))
        elementos.append(Spacer(1, 6))
        
        dados_tabela = [["Parâmetro avaliado", "Valor nominal", "Tol. +", "Tol. -", "Valor obtido", "Erro"]]
        
        for param in parametros:
            carac, nom, t_sup, t_inf, med, err = param
            dados_tabela.append([
                str(carac), 
                f"{nom:.3f}".replace('.', ',') if nom is not None else "-", 
                f"{t_sup:.3f}".replace('.', ',') if t_sup is not None else "-", 
                f"{t_inf:.3f}".replace('.', ',') if t_inf is not None else "-", 
                f"{med:.3f}".replace('.', ',') if med is not None else "-", 
                f"{err:.3f}".replace('.', ',') if err is not None else "-"
            ])
            
        tabela = Table(dados_tabela, colWidths=[5.5*cm, 2.5*cm, 2*cm, 2*cm, 2.5*cm, 2*cm])
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ]))
        
        elementos.append(tabela)
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph(f"<b>4. Incerteza de medição:</b> {val_u} mm, k = {val_k}", style_bold))
        elementos.append(Paragraph(f"<b>5. Parecer Final:</b> {status_final}", style_bold))

        elementos.append(Paragraph("<b>6. Observações</b>", style_bold))
        elementos.append(Paragraph("*Os parâmetros avaliados foram obtidos da Ficha de Auto Controle do produto que o dispositivo controla.", style_normal))
        elementos.append(Paragraph(f"Técnico executante: {metro}", style_normal))
        elementos.append(Spacer(1, 24))

        elementos.append(Paragraph("_______________________________", style_normal))
        elementos.append(Paragraph("Signatário Autorizado", style_normal))
        elementos.append(Paragraph("João Carlos Gomes de Oliveira", style_normal))
        
        doc.build(elementos)
        pdf_buffer.seek(0)
        
        # 4. Upload do PDF para o Amazon S3
        nome_arquivo = f"Certificado_{dispositivo}_{data_med.replace('/', '-')}.pdf"
        bucket_saida = "schulz-pdf-certificates-grupo41"
        
        s3_client.put_object(
            Bucket=bucket_saida,
            Key=nome_arquivo,
            Body=pdf_buffer.getvalue(),
            ContentType="application/pdf"
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps(f"PDF {nome_arquivo} gerado e salvo no S3 com sucesso!")
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(f"Erro na geração do PDF: {str(e)}")
        }