from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import aiofiles
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import logging
import mercadopago # Importa a SDK do Mercado Pago
import firebase_admin # Importa a SDK do Firebase Admin
from firebase_admin import credentials, firestore
import json # Para carregar a chave JSON do Firebase

#Versão 1.02

# Configura o logging para ver mensagens no console do Render para depuração
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Carrega variáveis de ambiente do arquivo .env (para desenvolvimento local)
# EM PRODUÇÃO NO RENDER, ESTAS VARIÁVEIS DEVEM SER CONFIGURADAS DIRETAMENTE NO DASHBOARD DO RENDER.
load_dotenv()

app = FastAPI()

# --- INÍCIO DA CONFIGURAÇÃO CORS ---
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8080",
    "https://dra-clausula.onrender.com" # URL do seu frontend no Render
    # ADICIONE AQUI QUAISQUER OUTROS DOMÍNIOS ONDE SEU FRONTEND ESTARÁ HOSPEDADO
    # Exemplo: "https://seu-dominio-customizado.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- FIM DA CONFIGURAÇÃO CORS ---

# --- CONFIGURAÇÃO FIREBASE/FIRESTORE ---
# Tenta obter a chave da conta de serviço do Firebase das variáveis de ambiente
# VOCÊ DEVE CONFIGURAR A VARIÁVEL FIREBASE_SERVICE_ACCOUNT_KEY NO DASHBOARD DO RENDER!
FIREBASE_SERVICE_ACCOUNT_KEY_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")

if FIREBASE_SERVICE_ACCOUNT_KEY_JSON:
    try:
        # Carrega as credenciais do JSON string
        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_KEY_JSON))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase Admin SDK inicializado com sucesso.")
    except Exception as e:
        logging.error(f"Erro ao inicializar Firebase Admin SDK: {e}")
        db = None # Garante que db seja None se a inicialização falhar
else:
    logging.warning("Variável de ambiente FIREBASE_SERVICE_ACCOUNT_KEY não encontrada. Firestore não será inicializado.")
    db = None # DB não estará disponível

# --- FIM DA CONFIGURAÇÃO FIREBASE/FIRESTORE ---


# --- CONFIGURAÇÃO MERCADO PAGO ---
# Obtém o Access Token do Mercado Pago das variáveis de ambiente
# VOCÊ DEVE CONFIGURAR MERCADOPAGO_ACCESS_TOKEN NO DASHBOARD DO RENDER!
MERCADOPAGO_ACCESS_TOKEN = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")

if not MERCADOPAGO_ACCESS_TOKEN:
    logging.error("ERRO CRÍTICO: MERCADOPAGO_ACCESS_TOKEN não configurado nas variáveis de ambiente.")
    raise Exception("MERCADOPAGO_ACCESS_TOKEN é obrigatório para a API do Mercado Pago. Por favor, configure no Render.")

# Inicializa a SDK do Mercado Pago com o Access Token
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# --- FIM DA CONFIGURAÇÃO MERCADO PAGO ---


@app.post("/api/pagamento/criar-checkout")
async def criar_checkout_mercadopago(
    item_title: str = Form("Análise de Contrato Dra. Cláusula"),
    item_price: float = Form(0.01), # PREÇO ALTERADO PARA 0.01 CENTAVOS default o preço ven do frontend
    user_email: str = Form(...), # E-mail do usuário para associar ao pagamento
    user_id: str = Form(...) # user_id do frontend para associar o pagamento no Firestore
    
):
    """
    Endpoint para criar uma preferência de pagamento no Mercado Pago e retornar o link de checkout.
    Este endpoint será chamado pelo seu frontend quando o usuário clicar em 'Realizar Pagamento'.
    """
    if not MERCADOPAGO_ACCESS_TOKEN:
        logging.error("Tentativa de criar checkout sem MERCADOPAGO_ACCESS_TOKEN configurado.")
        raise HTTPException(status_code=500, detail="Serviço de pagamento não configurado. Por favor, contate o suporte.")

    # A URL REAL DA SUA API NO RENDER - ESSENCIAL PARA O WEBHHOOK DO MERCADO PAGO
    # Usamos RENDER_EXTERNAL_HOSTNAME para obter a URL dinâmica do Render, ou um fallback
    API_RENDER_URL = os.environ.get("RENDER_EXTERNAL_HOSTNAME") 
    if not API_RENDER_URL:
        # Fallback se não for executado no Render ou variável não setada.
        # SUBSTITUA ESTA URL PELA URL REAL DA SUA API NO RENDER!
        API_RENDER_URL = "contrato-analisador-api.onrender.com" # Ex: "minha-api-dra-clausula.onrender.com"
        logging.warning(f"RENDER_EXTERNAL_HOSTNAME não encontrado. Usando URL hardcoded de fallback: {API_RENDER_URL}")


    # Dados da preferência de pagamento a ser enviada ao Mercado Pago
    preference_data = {
        "items": [
            {
                "title": item_title,
                "quantity": 1,
                "unit_price": item_price
            }
        ],
        # URLs para onde o Mercado Pago redirecionará o usuário após o pagamento
        # VOCÊ DEVE SUBSTITUIR ESTAS URLs PELAS URLs REAIS DO SEU FRONTEND NO RENDER!
        "back_urls": {
            "success": "https://dra-clausula.onrender.com/pagamento-sucesso.html", # Página de sucesso no seu frontend
            "failure": "https://dra-clausula.onrender.com/pagamento-falha.html",   # Página de falha no seu frontend
            "pending": "https://dra-clausula.onrender.com/pagamento-pendente.html" # Página de pagamento pendente no seu frontend
        },
        "auto_return": "approved", # Redireciona automaticamente se o pagamento for aprovado
        "payer": {
            "email": user_email # E-mail do pagador para pré-preencher no checkout do MP
        },
        # URL do seu Webhook para receber notificações assíncronas do Mercado Pago
        # AQUI USAMOS A API_RENDER_URL OBTIDA ACIMA
        "notification_url": f"https://{API_RENDER_URL}/api/pagamento/webhook-mercadopago?source=webhooks", 
        # O external_reference é crucial para identificar a transação e o usuário
        # AGORA USANDO user_id DO FRONTEND
        "external_reference": f"ANALISE-{user_id}-{os.urandom(4).hex()}" 
    }

    try:
        logging.info(f"Iniciando criação de preferência de pagamento no Mercado Pago para {user_email} (User ID: {user_id})...")
        preference_response = sdk.preference().create(preference_data)
        
        preference = preference_response["response"]
        
        if "init_point" not in preference:
            logging.error(f"Erro: 'init_point' não encontrado na resposta do Mercado Pago. Resposta completa: {preference}")
            raise HTTPException(status_code=500, detail="Erro interno ao gerar link de pagamento. Tente novamente ou contate o suporte.")

        logging.info(f"Preferência de pagamento criada com sucesso. Link de checkout: {preference['init_point']}")
        return JSONResponse(status_code=200, content={
            "checkout_url": preference["init_point"],
            "preference_id": preference["id"],
            "external_reference": preference_data["external_reference"] # Retorna para o frontend
        })

    except mercadopago.exceptions.MPException as e:
        logging.exception(f"Erro na SDK do Mercado Pago ao criar preferência (Status: {e.status_code}, Mensagem: {e.message})")
        raise HTTPException(status_code=e.status_code if hasattr(e, 'status_code') else 500, detail=f"Erro no serviço de pagamento: {e.message}")
    except Exception as e:
        logging.exception(f"Erro inesperado ao criar preferência de pagamento: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao criar pagamento: {str(e)}")

# Endpoint para Webhook do Mercado Pago (ESSENCIAL PARA CONFIRMAÇÃO SEGURA)
# Este endpoint é chamado pelo Mercado Pago quando o status de um pagamento muda.
# NÃO é acessado diretamente pelo navegador do usuário.
@app.post("/api/pagamento/webhook-mercadopago")
async def mercadopago_webhook(
    # O Mercado Pago envia o tópico e o ID da notificação como parâmetros de query
    topic: str = None, 
    id: str = None
):
    logging.info(f"Webhook do Mercado Pago recebido. Tópico: {topic}, ID da Notificação: {id}")

    if not db:
        logging.error("Firestore não está inicializado. Não é possível processar webhook.")
        # Retorna 200 OK para o MP para evitar reenvio, mas loga o erro.
        return JSONResponse(status_code=200, content={"status": "Firestore indisponível"})

    if topic == "payment":
        try:
            payment_info = sdk.payment().get(id) # Busca os detalhes do pagamento no Mercado Pago
            payment_status = payment_info["response"]["status"]
            external_reference = payment_info["response"]["external_reference"] # Nosso ID único
            user_email = payment_info["response"]["payer"]["email"]
            
            # Extrair o user_id do external_reference se ele foi formatado como "ANALISE-{user_id}-{random_hex}"
            # Isso é CRÍTICO para associar o pagamento ao usuário correto no Firestore.
            parts = external_reference.split('-')
            user_id_from_ref = parts[1] if len(parts) > 1 else "unknown" # Pega o segundo elemento após o split

            logging.info(f"Detalhes do Pagamento no Webhook - ID: {id}, Status: {payment_status}, Ref Externa: {external_reference}, Email: {user_email}, User ID (from ref): {user_id_from_ref}")

            # Salvar o status do pagamento no Firestore
            # A estrutura é payments/{userId}/transactions/{payment_id}
            payment_doc_ref = db.collection("payments").document(user_id_from_ref).collection("transactions").document(id)
            
            payment_data = {
                "payment_id": id,
                "status": payment_status,
                "external_reference": external_reference,
                "user_email": user_email,
                "user_id": user_id_from_ref, # Garantir que o user_id seja salvo no documento
                "timestamp": firestore.SERVER_TIMESTAMP # Salva o timestamp do servidor
            }
            
            # CORREÇÃO: Removido 'await' aqui, pois firestore.Client.document.set() é síncrono.
            payment_doc_ref.set(payment_data, merge=True) 
            logging.info(f"Status do pagamento {id} para {user_id_from_ref} salvo no Firestore como '{payment_status}'.")

            if payment_status == "approved":
                # Lógica adicional para serviço aprovado
                logging.info(f"Pagamento APROVADO para {user_email} (User ID: {user_id_from_ref}). Serviço pronto para análise.")
            elif payment_status == "pending":
                logging.info(f"Pagamento PENDENTE para {user_email} (User ID: {user_id_from_ref}).")
            elif payment_status == "rejected":
                logging.info(f"Pagamento REJEITADO para {user_email} (User ID: {user_id_from_ref}).")
            else:
                logging.info(f"Status de pagamento desconhecido/não tratado: {payment_status}")
            
        except Exception as e:
            logging.exception(f"Erro ao processar webhook de pagamento {id}: {e}")
            return JSONResponse(status_code=200, content={"status": "erro no processamento"})
    else:
        logging.info(f"Webhook de tópico '{topic}' recebido, mas não tratado.")

    # É fundamental retornar um status 200 OK para o Mercado Pago
    return JSONResponse(status_code=200, content={"status": "ok"})


# NOVO ENDPOINT: Verificar status de pagamento no Firestore
@app.get("/api/pagamento/verificar-status")
async def verificar_status_pagamento(user_id: str):
    """
    Endpoint para o frontend consultar o status do pagamento de um usuário no Firestore.
    Verifica se existe pelo menos um pagamento aprovado para o given user_id.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Serviço de banco de dados indisponível.")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="ID do usuário é obrigatório.")

    try:
        # Busca o documento mais recente de pagamento aprovado para este user_id
        # A estrutura é payments/{userId}/transactions/{payment_id}
        payments_ref = db.collection("payments").document(user_id).collection("transactions")
        
        # Consulta para buscar um pagamento aprovado.
        # order_by("timestamp", direction=firestore.Query.DESCENDING) + limit(1)
        # para pegar o mais recente se houver múltiplos.
        query_ref = payments_ref.where("status", "==", "approved").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1)
        docs = query_ref.get()

        if docs:
            # Pelo menos um documento de pagamento aprovado foi encontrado
            payment_data = docs[0].to_dict() # Pega o primeiro (e único) resultado
            logging.info(f"Pagamento aprovado encontrado para User ID: {user_id}. Status: {payment_data['status']}")
            return JSONResponse(status_code=200, content={"status": "approved", "message": "Pagamento confirmado com sucesso."})
        else:
            logging.info(f"Nenhum pagamento aprovado encontrado para User ID: {user_id}.")
            return JSONResponse(status_code=200, content={"status": "pending_or_rejected", "message": "Pagamento não aprovado ou pendente."})

    except Exception as e:
        logging.exception(f"Erro ao verificar status de pagamento para User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao verificar status de pagamento: {str(e)}")


@app.post("/api/contrato/analisar")
async def analisar_contrato(
    nome: str = Form(...),
    email: str = Form(...),
    parte: str = Form(...),
    arquivo: UploadFile = File(...),
    user_id: str = Form(...) # Recebe o user_id do frontend para verificar pagamento
):
    # --- IMPORTANTE: VERIFICAÇÃO DE PAGAMENTO ANTES DA ANÁLISE ---
    # Agora que temos o Firestore, podemos verificar o status de pagamento real.
    if not db:
        logging.error("Firestore não está inicializado. Não é possível verificar pagamento.")
        raise HTTPException(status_code=500, detail="Serviço de banco de dados indisponível para verificar pagamento.")
    
    try:
        logging.info(f"API Analisar Contrato: Verificando pagamento para User ID: {user_id}")
        payments_ref = db.collection("payments").document(user_id).collection("transactions")
        query_ref = payments_ref.where("status", "==", "approved").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1)
        docs = query_ref.get()

        if not docs:
            logging.warning(f"API Analisar Contrato: Tentativa de análise para User ID {user_id} sem pagamento aprovado. Documentos encontrados: {len(docs)}")
            raise HTTPException(status_code=403, detail="Pagamento não confirmado para este serviço. Por favor, conclua o pagamento.")
        
        logging.info(f"API Analisar Contrato: Pagamento aprovado confirmado para User ID: {user_id}. Prosseguindo com a análise.")

    except Exception as e:
        logging.exception(f"API Analisar Contrato: Erro ao verificar status de pagamento para User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao verificar pagamento: {str(e)}")

    # O restante do código da análise de contrato continua aqui
    if not arquivo:
        logging.error("Erro: Arquivo não enviado na requisição.")
        return JSONResponse(status_code=400, content={"erro": "Arquivo não enviado."})

    temp_path = "" # Inicializa temp_path
    try:
        temp_path = f"temp_{arquivo.filename}"
        async with aiofiles.open(temp_path, 'wb') as out_file:
            content = await arquivo.read()
            await out_file.write(content)
        logging.info(f"Arquivo temporário '{arquivo.filename}' salvo em: {temp_path}")

        from Api_Gemini import processar_pdf_com_gemini
        
        Prompt = f"""
## Instrução para Análise de Contrato

Você é a "Dra. Cláusula", uma especialista em análise de contratos. Sua tarefa é analisar o contrato fornecido, focando nos interesses e segurança jurídica da parte especificada.

### Contexto da Análise:
- O contrato deve ser analisado sob a perspectiva da parte: **{parte}**.
- **Adapte a análise ao tipo de contrato fornecido.**

### Tarefas de Análise:
1.  **Identificação e Validação das Partes:** Verifique se todas as partes envolvidas estão corretamente identificadas, incluindo nomes completos/razões sociais, documentos de identificação/CNPJ e detalhes de contato. Indique qualquer inconsistência ou ausência.
2.  **Objeto e Obrigações Contratuais:** Descreva de forma concisa o objeto principal do contrato e as obrigações claras de cada parte. Avalie a precisão e completude da descrição dos serviços ou produtos.
3.  **Termos e Condições Essenciais:** Analise cuidadosamente os termos e condições gerais, incluindo prazos, formas de pagamento, direitos e responsabilidades de cada parte, e condições de encerramento do contrato.
4.  **Pontos Críticos:** Indique os pontos positivos e negativos específicos do contrato para a parte **{parte}**, considerando os valores, prazos e condições financeiras acordados.
5.  **Cláusulas de Garantia e Responsabilidade:** Verifique garantias oferecidas, condições de posse, entrega ou uso, e as responsabilidades explícitas de cada parte em caso de falhas ou danos.
6.  **Descumprimento, Rescisão e Penalidades:** Analise como o contrato trata o descumprimento, inadimplência, as condições de rescisão, multas e penalidades associadas, bem como a resolução de disputas.
7.  **Sugestões de Alteração:** Sugira melhorias específicas para proteger ainda mais os interesses da parte **{parte}**, fundamentando cada proposta.
8.  **Propostas de Cláusulas Substitutas:** Redija versões melhoradas de cláusulas existentes, se a alteração sugerida exigir uma nova redação.
9.  **Novas Cláusulas Essenciais:** Proponha a inclusão de quaisquer cláusulas adicionais que sejam relevantes e necessárias para a segurança jurídica da parte **{parte}**, justificando sua importância.

### Formato:
- Responda em **HTML**, sem saudações iniciais.
- Use títulos (`<h2>`), listas (`<ul>`), parágrafos (`<p>`) e negrito (`<strong>`).
- **Finalize com:** `Atenciosamente,<br>Dra. Cláusula`
"""
        resposta_ia = ""
        try:
            logging.info("Chamando a função de processamento de IA...")
            resposta_ia = processar_pdf_com_gemini(Prompt, temp_path)
            logging.info("Resposta da IA recebida com sucesso.")

            # --- INÍCIO DA CORREÇÃO: Limpar a resposta da IA para o e-mail ---
            if isinstance(resposta_ia, str):
                # Remove '```html' do início, opcionalmente com quebras de linha
                resposta_ia = resposta_ia.replace("```html", "").strip()
                # Remove '```' do final, opcionalmente com quebras de linha
                resposta_ia = resposta_ia.replace("```", "").strip()
            # --- FIM DA CORREÇÃO ---

        except ImportError:
            logging.exception("Erro de importação: Api_Gemini ou processar_pdf_com_gemini não encontrados. Verifique o arquivo e o caminho.")
            return JSONResponse(status_code=500, content={"erro": "Erro interno: Módulo de IA não encontrado ou com problema."})
        except Exception as e:
            logging.exception(f"Erro inesperado ao processar PDF com Gemini: {e}")
            return JSONResponse(status_code=500, content={"erro": f"Erro na análise de IA: {str(e)}. Verifique o log para mais detalhes."})

        # --- CONFIGURAÇÃO DE E-MAIL (MANTIDA ORIGINALMENTE) ---
        try:
            # Credenciais de e-mail hardcoded como solicitado
            EMAIL_ADDRESS = "draclausula@gmail.com"
            EMAIL_PASSWORD = "adunjzuwoqahruuj"

            msg = EmailMessage()
            msg["Subject"] = "Resultado da Análise Contratual - Dra. Cláusula"
            msg["From"] = EMAIL_ADDRESS
            msg["To"] = email
            msg.set_content(resposta_ia, subtype='html')

            with open(temp_path, 'rb') as f:
                msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=arquivo.filename)

            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                smtp.send_message(msg)
            logging.info(f"E-mail de análise enviado com sucesso para {email}")

        except smtplib.SMTPAuthenticationError:
            logging.exception("Erro de autenticação SMTP: Verifique as credenciais e se há necessidade de senha de aplicativo.")
            return JSONResponse(status_code=500, content={"erro": "Falha na autenticação do e-mail. Credenciais ou senha de aplicativo inválidas."})
        except smtplib.SMTPConnectError:
            logging.exception("Erro de conexão SMTP: Não foi possível conectar ao servidor de e-mail. Verifique a porta, o servidor e o firewall do ambiente de hospedagem.")
            return JSONResponse(status_code=500, content={"erro": "Falha ao conectar ao servidor de e-mail. Tente novamente mais tarde."})
        except smtplib.SMTPException as e:
            logging.exception(f"Erro SMTP genérico: {e}")
            return JSONResponse(status_code=500, content={"erro": f"Falha no envio do e-mail: Erro do servidor SMTP. ({str(e)})"})
        except Exception as e:
            logging.exception(f"Erro inesperado ao enviar e-mail: {e}")
            return JSONResponse(status_code=500, content={"erro": f"Falha ao enviar e-mail: {str(e)}. Verifique o log."})

        return {"mensagem": "Análise enviada por e-mail com sucesso! Verifique sua caixa de entrada e spam."}

    finally:
        # Garante que o arquivo temporário seja removido, mesmo que ocorra um erro
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logging.info(f"Arquivo temporário '{temp_path}' removido.")
            except Exception as e:
                logging.error(f"Erro ao remover arquivo temporário {temp_path}: {e}")

