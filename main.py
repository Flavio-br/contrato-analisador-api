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

# --- CONFIGURAÇÃO MERCADO PAGO ---
# Obtém o Access Token do Mercado Pago das variáveis de ambiente
MERCADOPAGO_ACCESS_TOKEN = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")

if not MERCADOPAGO_ACCESS_TOKEN:
    logging.error("ERRO CRÍTICO: MERCADOPAGO_ACCESS_TOKEN não configurado nas variáveis de ambiente.")
    # Em um ambiente de produção real, você poderia querer que a aplicação não inicie
    # ou logue um erro fatal, dependendo da criticidade.
    # raise Exception("MERCADOPAGO_ACCESS_TOKEN é obrigatório para a API do Mercado Pago.")

# Inicializa a SDK do Mercado Pago com o Access Token
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# --- FIM DA CONFIGURAÇÃO MERCADO PAGO ---


@app.post("/api/pagamento/criar-checkout")
async def criar_checkout_mercadopago(
    item_title: str = Form("Análise de Contrato Dra. Cláusula"),
    item_price: float = Form(29.99), # Preço da análise (ajuste conforme necessário)
    user_email: str = Form(...) # E-mail do usuário para associar ao pagamento
):
    """
    Endpoint para criar uma preferência de pagamento no Mercado Pago e retornar o link de checkout.
    """
    if not MERCADOPAGO_ACCESS_TOKEN:
        logging.error("Tentativa de criar checkout sem MERCADOPAGO_ACCESS_TOKEN configurado.")
        raise HTTPException(status_code=500, detail="Serviço de pagamento não configurado. Por favor, contate o suporte.")

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
            "success": "https://dra-clausula.onrender.com/pagamento-sucesso", # Página de sucesso
            "failure": "https://dra-clausula.onrender.com/pagamento-falha",   # Página de falha
            "pending": "https://dra-clausula.onrender.com/pagamento-pendente" # Página de pagamento pendente
        },
        "auto_return": "approved", # Redireciona automaticamente se o pagamento for aprovado
        "payer": {
            "email": user_email # Opcional: E-mail do pagador para pré-preencher no checkout
        },
        # URL do seu Webhook para receber notificações assíncronas do Mercado Pago
        # VOCÊ DEVE SUBSTITUIR 'https://sua-api-dra-clausula.onrender.com' PELA URL REAL DA SUA API NO RENDER!
        "notification_url": f"https://sua-api-dra-clausula.onrender.com/api/pagamento/webhook-mercadopago?source=webhooks", 
        "external_reference": f"ANALISE-{user_email}-{os.urandom(4).hex()}" # Um ID único para sua transação
    }

    try:
        logging.info(f"Iniciando criação de preferência de pagamento no Mercado Pago para {user_email}...")
        preference_response = sdk.preference().create(preference_data)
        
        preference = preference_response["response"]
        
        if "init_point" not in preference:
            logging.error(f"Erro: 'init_point' não encontrado na resposta do Mercado Pago. Resposta completa: {preference}")
            raise HTTPException(status_code=500, detail="Erro interno ao gerar link de pagamento. Tente novamente ou contate o suporte.")

        logging.info(f"Preferência de pagamento criada com sucesso. Link de checkout: {preference['init_point']}")
        return JSONResponse(status_code=200, content={
            "checkout_url": preference["init_point"],
            "preference_id": preference["id"]
        })

    except mercadopago.exceptions.MPException as e:
        logging.exception(f"Erro na SDK do Mercado Pago ao criar preferência (Status: {e.status_code}, Mensagem: {e.message})")
        raise HTTPException(status_code=e.status_code if hasattr(e, 'status_code') else 500, detail=f"Erro no serviço de pagamento: {e.message}")
    except Exception as e:
        logging.exception(f"Erro inesperado ao criar preferência de pagamento: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao criar pagamento: {str(e)}")

# Endpoint para Webhook do Mercado Pago (ESSENCIAL PARA CONFIRMAÇÃO SEGURA)
# Este endpoint é chamado pelo Mercado Pago quando o status de um pagamento muda.
@app.post("/api/pagamento/webhook-mercadopago")
async def mercadopago_webhook(
    # O Mercado Pago envia o tópico e o ID da notificação como parâmetros de query
    # Ex: /webhook?topic=payment&id=12345
    topic: str = None, 
    id: str = None
):
    logging.info(f"Webhook do Mercado Pago recebido. Tópico: {topic}, ID da Notificação: {id}")

    if topic == "payment":
        try:
            # Para o tópico "payment", o 'id' que vem na URL de notificação é o payment_id
            payment_info = sdk.payment().get(id) # Busca os detalhes do pagamento no Mercado Pago
            payment_status = payment_info["response"]["status"]
            external_reference = payment_info["response"]["external_reference"] # Nosso ID único da transação
            user_email = payment_info["response"]["payer"]["email"] # E-mail do pagador
            
            logging.info(f"Detalhes do Pagamento - ID: {id}, Status: {payment_status}, Ref Externa: {external_reference}, Email: {user_email}")

            if payment_status == "approved":
                # --- AQUI É ONDE VOCÊ DEVE IMPLEMENTAR A LÓGICA PARA ATIVAR O SERVIÇO DO USUÁRIO ---
                # Exemplo: Marcar o usuário (identificado pelo user_email ou external_reference)
                # como "pagamento confirmado" em um BANCO DE DADOS.
                # Sem um banco de dados, o frontend não tem como saber o status real e seguro.
                logging.info(f"Pagamento APROVADO para {user_email} (Ref Externa: {external_reference}). Ativando serviço de análise...")
                # TODO: Implementar lógica de persistência para registrar o pagamento.
                # Ex: Salvar em um banco de dados {email: user_email, status: "pago", ref_externa: external_reference}
                # Isso permite que o endpoint /api/contrato/analisar verifique se o usuário já pagou.
                
            elif payment_status == "pending":
                logging.info(f"Pagamento PENDENTE para {user_email} (Ref Externa: {external_reference}). Aguardando confirmação.")
            elif payment_status == "rejected":
                logging.info(f"Pagamento REJEITADO para {user_email} (Ref Externa: {external_reference}).")
            else:
                logging.info(f"Status de pagamento desconhecido/não tratado: {payment_status}")
            
        except Exception as e:
            logging.exception(f"Erro ao processar webhook de pagamento {id}: {e}")
            # Em caso de erro, ainda retornar 200 OK para evitar que o MP reenvie infinitamente
            # Mas o log ajudará na depuração
            return JSONResponse(status_code=200, content={"status": "erro no processamento"})
    else:
        logging.info(f"Webhook de tópico '{topic}' recebido, mas não tratado.")

    # É fundamental retornar um status 200 OK para o Mercado Pago,
    # caso contrário, ele pode continuar tentando reenviar a notificação.
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/api/contrato/analisar")
async def analisar_contrato(
    nome: str = Form(...),
    email: str = Form(...),
    parte: str = Form(...),
    arquivo: UploadFile = File(...)
):
    # --- IMPORTANTE: VERIFICAÇÃO DE PAGAMENTO ---
    # Para um sistema real, você PRECISA verificar aqui se o usuário já pagou.
    # Esta verificação exigiria um BANCO DE DADOS onde o status de pagamento foi
    # atualizado pelo Webhook do Mercado Pago.
    #
    # EXEMPLO TEÓRICO (requer banco de dados e lógica implementada):
    # from database import check_payment_status # Exemplo de importação
    # if not await check_payment_status(email):
    #     logging.warning(f"Tentativa de análise para {email} sem pagamento confirmado.")
    #     raise HTTPException(status_code=403, detail="Pagamento não confirmado para este serviço.")
    # else:
    #     logging.info(f"Pagamento confirmado para {email}. Prosseguindo com a análise.")

    if not arquivo:
        logging.error("Erro: Arquivo não enviado na requisição.")
        return JSONResponse(status_code=400, content={"erro": "Arquivo não enviado."})

    temp_path = "" # Inicializa temp_path para garantir que seja acessível no finally
    try:
        temp_path = f"temp_{arquivo.filename}"
        async with aiofiles.open(temp_path, 'wb') as out_file:
            content = await arquivo.read()
            await out_file.write(content)
        logging.info(f"Arquivo temporário '{arquivo.filename}' salvo em: {temp_path}")

        # Importa a função processar_pdf_com_gemini (garante que Api_Gemini.py está acessível)
        from Api_Gemini import processar_pdf_com_gemini
        
        # Prompt para a IA
        Prompt = f"""
## Instrução para Análise de Contrato

Você é a "Dra. Cláusula", uma especialista em análise de contratos. Sua tarefa é analisar o contrato fornecido, focando nos interesses e segurança jurídica da parte especificada.

### Contexto da Análise:
- O contrato deve ser analisado sob a perspectiva da parte: **{parte}**.
- **Adapte a análise ao tipo de contrato fornecido.**

### Tarefas de Análise:
1.  **Pontos Críticos:** Indique os pontos positivos e negativos do contrato para a parte **{parte}**.
2.  **Cláusulas de Garantia/Segurança:** Verifique garantias, posse, entrega ou uso.
3.  **Descumprimento/Inadimplência:** Analise como o contrato trata inadimplência, multas e penalidades.
4.  **Sugestões de Alteração:** Sugira melhorias para proteger a parte **{parte}**.
5.  **Propostas de Cláusulas Substitutas:** Redija cláusulas melhores, se necessário.
6.  **Novas Cláusulas Essenciais:** Inclua cláusulas adicionais se for relevante.

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
        except ImportError:
            logging.exception("Erro de importação: Api_Gemini ou processar_pdf_com_gemini não encontrados. Verifique o arquivo e o caminho.")
            return JSONResponse(status_code=500, content={"erro": "Erro interno: Módulo de IA não encontrado ou com problema."})
        except Exception as e:
            logging.exception(f"Erro inesperado ao processar PDF com Gemini: {e}")
            return JSONResponse(status_code=500, content={"erro": f"Erro na análise de IA: {str(e)}. Verifique o log para mais detalhes."})

        # --- CONFIGURAÇÃO DE E-MAIL ---
        try:
            # Obtém credenciais de e-mail das variáveis de ambiente (MELHOR PRÁTICA)
            EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
            EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
            
            if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
                logging.error("Variáveis de ambiente EMAIL_ADDRESS ou EMAIL_PASSWORD não estão configuradas para o envio de e-mail.")
                return JSONResponse(status_code=500, content={"erro": "Falha na configuração de e-mail (credenciais ausentes)."})

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
            logging.exception("Erro de autenticação SMTP: Verifique as credenciais (EMAIL_ADDRESS, EMAIL_PASSWORD) e se há necessidade de senha de aplicativo.")
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