# ☁️ Automação de Certificados de Calibração CMM - Schulz S.A.

![AWS](https://img.shields.io/badge/AWS-Free_Tier-FF9900?style=flat-square&logo=amazon-aws&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_App-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RDS-4169E1?style=flat-square&logo=postgresql&logoColor=white)

## 📌 Sobre o Projeto
Este repositório contém o código-fonte e a infraestrutura do ecossistema tecnológico desenvolvido para a **Schulz S.A.** como parte do **Projeto Aplicado III** (Centro Universitário SENAI/SC - Campus Florianópolis). 

O objetivo principal é automatizar o processo de validação metrológica e a emissão de certificados de Máquinas de Medição por Coordenadas (MMC). A solução marca a transição de um MVP local para um ambiente em nuvem integrado, funcional e 100% aderente à **Camada Gratuita (Free Tier) da AWS** utilizando arquitetura *Serverless*.

---

## 🎥 Demonstração e Evidência

Uma demonstração completa do funcionamento da plataforma (fim a fim) cobrindo o upload da planilha, visualização local e o processamento orquestrado na AWS está disponível no YouTube:

[![Vídeo de Demonstração](https://img.shields.io/badge/YouTube-Assistir_Demonstração-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=t-fiT-HkLh8)

---

## 👥 Equipe - Grupo 41
* **Nicolas Rafael Duma** - nicolasduma@outlook.com
* **Fabiano Carcuchinski Haag** - fabhaag@gmail.com
* **Silas Bratti Batista** - silas.bratti.bratti@gmail.com
* **Nicoly Pereira Carvalho** - nicolycarvalho821@gmail.com
* **Victor Hugo de Souza** - victorhugodesouza.dev@gmail.com

---

## ⚙️ Arquitetura em Nuvem (AWS)

A infraestrutura foi desenhada para garantir custo zero (MVP), escalabilidade e alta disponibilidade:

1. **Frontend (Amazon EC2 - `t3.small`)**: Hospeda a aplicação Web Streamlit (`app_st_cloud.py`). Interface primária dos engenheiros e técnicos metrologistas.
2. **Armazenamento (Amazon S3)**:
   * `schulz-raw-data-grupo41`: Recebe as planilhas de metadados geradas pela MMC.
   * `schulz-pdf-certificates-grupo41`: Armazena os certificados em formato PDF finais.
3. **Processamento (AWS Lambda)**:
   * `lambda-etl-schultz`: Disparada via evento de upload no S3. Processa cálculos estatísticos (Pandas), extrai dados XML e alimenta o banco de dados.
   * `lambda-gerador-pdf`: Invocada assincronamente. Desenha o certificado de calibração utilizando `ReportLab` e salva no S3. Utiliza *Layers* customizadas (Pillow, pg8000, Reportlab) para rodar em ambiente Linux (x86_64).
4. **Banco de Dados (Amazon RDS - `db.t3.micro`)**: Instância PostgreSQL relacional com 3 tabelas principais (`metadados`, `certificado`, `parametros`) para integridade histórica.
5. **Monitoramento**: Amazon CloudWatch para rastreabilidade de logs.

---

## 🚀 Funcionalidades da Plataforma Web

* **Pré-processamento e Reparo:** Identifica e corrige formatações XML corrompidas nativamente antes do processamento.
* **Extração de Metadados:** Captura automática do cabeçalho do relatório (dispositivo, peça, data, hora) e permite a inserção manual de parâmetros de inspeção complementares.
* **Motor Transacional (Pandas):** Validação imediata das cotas e tolerâncias. A interface devolve uma matriz visual (Verde = Aprovado / Vermelho = Reprovado).
* **Integração Assíncrona (Polling):** Comunicação com o S3 para envio de metadados codificados (UTF-8 safe) e verificação periódica até a disponibilização do PDF do certificado final gerado em nuvem.

---

## 📋 Matriz de Rastreabilidade de Requisitos

| ID | Requisito | Solução Técnica | Status |
|---|---|---|---|
| **REQ 01** | Interface amigável para ingestão de relatórios CMM gerados no equipamento sem intervenção manual severa. | Aplicação Streamlit Web com reparo autônomo de XML corrompido e pré-visualização de metadados. | ✅ Concluído |
| **REQ 02** | Validação imediata das cotas e tolerâncias e identificação visual de peças reprovadas. | Motor transacional Pandas local no frontend que gera matriz de cores (Verde/Vermelho). | ✅ Concluído |
| **REQ 03** | Centralização e garantia de integridade dos dados históricos de medição para futuras auditorias e BI. | Banco de dados relacional Amazon RDS (PostgreSQL) e função Lambda ETL utilizando pg8000. | ✅ Concluído |
| **REQ 04** | Geração automatizada do Certificado de Calibração com logotipo e assinaturas da empresa. | Função Lambda Geradora de PDF via ReportLab, camada Pillow instalada e persistência do documento gerado no bucket Amazon S3. | ✅ Concluído |
| **REQ 05** | Arquitetura de custo zero para a etapa de prototipagem (MVP). | Uso restrito da Camada Gratuita da AWS: Lambdas invocadas por evento, RDS classe Micro, S3 e EC2 Free Tier. | ✅ Concluído |
