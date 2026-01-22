"""
Dra.Cláusula Backend (FastAPI)
Tag interna: MAIN_INTERNAL_VERSION
"""
from __future__ import annotations

import os
import json
import logging
import base64
from datetime import datetime, timezone
from typing import Any, Optional

import aiofiles
import requests
import mercadopago
import firebase_admin
from firebase_admin import credentials, firestore

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


# =========================
# TAG INTERNA DE VERSÃO
# =========================
MAIN_INTERNAL_VERSION = "1.15"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="Dra.Cláusula API", version=MAIN_INTERNAL_VERSION)

# =========================
# CORS
# =========================
# Ajuste no Render conforme necessário
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://dra-clausula.onrender.com").split(",")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ENV / CONFIG
# =========================
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
if not MERCADOPAGO_ACCESS_TOKEN:
    logging.warning("MERCADOPAGO_ACCESS_TOKEN não configurado. Endpoints de pagamento ficarão indisponíveis até configurar a variável de ambiente.")

sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN) if MERCADOPAGO_ACCESS_TOKEN else None

# helper: garante que pagamentos estão configurados
from fastapi import HTTPException

def _require_mp_sdk():
    if sdk is None:
        raise HTTPException(status_code=500, detail="Configuração ausente: MERCADOPAGO_ACCESS_TOKEN não está definido no servidor.")

#
# (continua)
#
# SDK instantiation already done above
#
#
# marker
#
#

# Brevo (e-mail por API HTTP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Dra. Cláusula <draclausula@gmail.com>")

# Voucher de bypass (sem pagamento)
BYPASS_VOUCHER = os.getenv("BYPASS_VOUCHER", "jfm2!").strip().lower()

# Firebase / Firestore
db: Optional[firestore.Client] = None
try:
    fb_json = os.getenv("FIREBASE_KEY_JSON")  # recomendado: JSON completo em 1 ENV
    fb_path = os.getenv("FIREBASE_KEY_PATH")  # alternativa: path para arquivo
    if fb_json:
        cred_dict = json.loads(fb_json)
        cred = credentials.Certificate(cred_dict)
    elif fb_path:
        cred = credentials.Certificate(fb_path)
    else:
        cred = None

    if cred and not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase Admin SDK inicializado com sucesso.")
    elif firebase_admin._apps:
        db = firestore.client()
        logging.info("Firebase Admin SDK já estava inicializado.")
    else:
        logging.warning("Firebase não configurado (FIREBASE_KEY_JSON/FIREBASE_KEY_PATH ausente).")
except Exception as e:
    logging.exception(f"Falha ao inicializar Firebase: {e}")
    db = None


# =========================
# Helpers
# =========================
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _store_transaction(user_id: str, payment_id: str, payload: dict) -> None:
    if not db:
        return
    db.collection("payments").document(user_id).collection("transactions").document(payment_id).set(payload, merge=True)

def _find_latest_approved(user_id: str) -> Optional[dict]:
    if not db:
        return None
    payments_ref = db.collection("payments").document(user_id).collection("transactions")
    # status == approved, order by timestamp desc, limit 1
    q = payments_ref.where("status", "==", "approved").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1)
    docs = q.get()
    if not docs:
        return None
    return docs[0].to_dict()

def _find_latest_transaction(user_id: str) -> Optional[dict]:
    if not db:
        return None
    ref = db.collection("payments").document(user_id).collection("transactions")
    q = ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1)
    docs = q.get()
    if not docs:
        return None
    return docs[0].to_dict()

def _send_email_brevo(
    to_email: str,
    subject: str,
    html: str,
    attachment_name: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
) -> tuple[bool, Optional[str]]:
    """Envia e-mail via Brevo. Retorna (ok, erro)."""
    if not BREVO_API_KEY:
        return False, "BREVO_API_KEY não configurada."

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }
    payload: dict[str, Any] = {
        "sender": {"name": "Dra. Cláusula", "email": EMAIL_FROM.split("<")[-1].strip(" >")},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    if attachment_bytes and attachment_name:
        payload["attachment"] = [{
            "name": attachment_name,
            "content": base64.b64encode(attachment_bytes).decode("utf-8"),
        }]

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code >= 400:
        return False, f"Brevo erro {r.status_code}: {r.text[:500]}"

    return True, None

# =========================
# Rotas

# =========================

@app.get("/")
def root():
    return {"ok": True, "service": "Dra.Cláusula API", "version": MAIN_INTERNAL_VERSION}

@app.post("/api/pagamento/criar-checkout")
async def criar_checkout(
    item_title: str = Form(...),
    item_price: str = Form(...),
    user_email: str = Form(...),
    user_id: str = Form(...),
):
    _require_mp_sdk()

    try:
        price_float = float(item_price)
    except Exception:
        raise HTTPException(status_code=400, detail="item_price inválido")

    # ✅ Defina aqui (evita NameError)
    BASE_URL = os.getenv("BASE_URL", "https://contrato-analisador-api.onrender.com")

    preference_data = {
        "items": [{
            "title": item_title,
            "quantity": 1,
            "unit_price": price_float,
        }],
        "external_reference": user_id,
        "metadata": {"user_id": user_id, "user_email": user_email},
        "notification_url": f"{BASE_URL}/api/pagamento/webhook-mercadopago",
        "back_urls": {
            "success": "https://dra-clausula.onrender.com/pagamento/sucesso",
            "failure": "https://dra-clausula.onrender.com/pagamento/erro",
            "pending": "https://dra-clausula.onrender.com/pagamento/pendente",
        },
        "auto_return": "approved",
    }

    try:
        pref = sdk.preference().create(preference_data)
        logging.info(f"[MP] preference.create status={pref.get('status')} response_keys={list((pref.get('response') or {}).keys())}")

        if not pref or pref.get("status") not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Falha ao criar preferência Mercado Pago: {pref}")

        body = pref.get("response", {})
        checkout_url = body.get("init_point") or body.get("sandbox_init_point")
        preference_id = body.get("id")

        if not checkout_url or not preference_id:
            raise HTTPException(status_code=500, detail=f"Resposta do Mercado Pago incompleta: {body}")

        payment_id = preference_id  # seu id interno

        _store_transaction(user_id, payment_id, {
            "status": "pending",
            "preference_id": preference_id,
            "checkout_url": checkout_url,
            "user_email": user_email,
            "timestamp": _now_utc(),
        })

        return {"checkout_url": checkout_url, "payment_id": payment_id}

    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"[MP] Erro criando checkout: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar checkout Mercado Pago: {str(e)}")

@app.get("/api/pagamento/verificar-status")
async def verificar_status(user_id: str):
    if not db:
        raise HTTPException(status_code=500, detail="Firestore indisponível")

    try:
        tx = _find_latest_transaction(user_id)
        if not tx:
            return JSONResponse(status_code=200, content={"status": "not_found", "message": "Nenhuma transação encontrada."})

        status = (tx.get("status") or "").lower()

        if status == "approved":
            return JSONResponse(status_code=200, content={"status": "approved", "message": "Pagamento confirmado com sucesso."})

        if status == "pending":
            return JSONResponse(status_code=200, content={"status": "pending", "message": "PIX pendente. Aguardando confirmação do pagamento."})

        return JSONResponse(status_code=200, content={"status": status or "unknown", "message": "Pagamento não aprovado."})
    except Exception as e:
        logging.exception(f"Erro ao verificar status de pagamento para User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao verificar status de pagamento.")


@app.post("/api/pagamento/webhook-mercadopago")
async def webhook_mercadopago(request: Request):
    _require_mp_sdk()

    # Sempre responda 200 rápido; mas vamos registrar o que chegou
    try:
        params = dict(request.query_params)
        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}

        logging.info(f"[MP WEBHOOK] query={params} body_keys={list(body.keys())}")

        # Mercado Pago pode mandar:
        # - query: ?type=payment&data.id=123
        # - body: {"type":"payment","data":{"id":"123"}}  (ou variações)
        payment_type = params.get("type") or params.get("topic") or body.get("type") or body.get("topic")

        data_id = (
            params.get("data.id")
            or params.get("id")
            or (body.get("data") or {}).get("id")
            or body.get("id")
        )

        if payment_type != "payment" or not data_id:
            return {"ok": True}

        payment = sdk.payment().get(str(data_id))
        if not payment or payment.get("status") != 200:
            logging.warning(f"[MP WEBHOOK] payment.get falhou para id={data_id} status={payment.get('status') if payment else None}")
            return {"ok": True}

        p = payment.get("response", {})
        status = p.get("status")

        # ✅ fonte mais confiável para vincular ao seu pedido/usuário
        user_id = p.get("external_reference") or (p.get("metadata") or {}).get("user_id")

        logging.info(f"[MP WEBHOOK] payment_id={data_id} status={status} user_id={user_id}")

        if db and user_id:
            _store_transaction(str(user_id), str(data_id), {
                "status": status,
                "payment_id": str(data_id),
                "timestamp": _now_utc(),
                "raw": p,
            })

        return {"ok": True}
    except Exception as e:
        logging.exception(f"[MP WEBHOOK] erro: {e}")
        return {"ok": True}

@app.post("/api/contrato/analisar")
async def analisar_contrato(
    nome: str = Form(...),
    email: str = Form(...),
    parte: str = Form(...),
    arquivo: UploadFile = File(...),
    user_id: str = Form(...),
    voucher: str = Form(""),
):
    """
    Analisa contrato via Gemini e devolve HTML.
    Se voucher == BYPASS_VOUCHER, pula verificação de pagamento.
    """
    # --- Pagamento / bypass ---
    voucher_norm = (voucher or "").strip().lower()
    bypass_pagamento = bool(BYPASS_VOUCHER) and voucher_norm == BYPASS_VOUCHER

    logging.info(f"API Analisar Contrato: Voucher='{voucher}' | bypass_pagamento={bypass_pagamento} | user_id={user_id}")

    if not bypass_pagamento:
        if not db:
            raise HTTPException(status_code=500, detail="Serviço de banco de dados indisponível para verificar pagamento.")
        approved = _find_latest_approved(user_id)
        if not approved:
            raise HTTPException(status_code=403, detail="Pagamento não confirmado para este serviço. Por favor, conclua o pagamento.")

    if not arquivo:
        raise HTTPException(status_code=400, detail="Arquivo não enviado.")

    temp_path = ""
    try:
        temp_path = f"temp_{arquivo.filename}"
        async with aiofiles.open(temp_path, "wb") as out_file:
            content = await arquivo.read()
            await out_file.write(content)
        logging.info(f"Arquivo temporário '{arquivo.filename}' salvo em: {temp_path}")

        # --- IA (Gemini) ---
        try:
            from Api_Gemini import processar_pdf_com_gemini  # no seu repo
        except Exception as e:
            logging.exception(f"Erro import Api_Gemini: {e}")
            raise HTTPException(status_code=500, detail="Módulo de IA indisponível (Api_Gemini).")

        prompt = f"""
## Instrução para Análise de Contrato
Você é a "Dra. Cláusula", uma especialista em análise de contratos. Sua tarefa é analisar o contrato fornecido, focando nos interesses e segurança jurídica da parte especificada.
### Contexto da Análise:
- O contrato deve ser analisado sob a perspectiva da parte: **{parte}**.
- **Adapte a análise ao tipo de contrato fornecido.**
### Formato:
- Responda em **HTML**, sem saudações iniciais.
- Use títulos (`<h2>`), listas (`<ul>`), parágrafos (`<p>`) e negrito (`<strong>`).
- **Finalize com:** `Atenciosamente,<br>Dra. Cláusula`
"""
        logging.info("Chamando a função de processamento de IA...")
        resposta_html = processar_pdf_com_gemini(prompt, temp_path)
        if not resposta_html:
            raise HTTPException(status_code=500, detail="IA não retornou conteúdo.")
        logging.info("Resposta da IA recebida com sucesso.")

        # --- E-mail (Brevo) ---
        email_enviado = False
        email_erro: Optional[str] = None
        assunto = "Resultado da Análise Contratual - Dra. Cláusula"

        try:
            # opcional: anexar o PDF original
            attachment_bytes = content if content else None
            email_ok, email_err = _send_email_brevo(
                to_email=email,
                subject=assunto,
                html=resposta_html,
                attachment_name=arquivo.filename,
                attachment_bytes=attachment_bytes,
            )
            email_enviado = bool(email_ok)
            email_erro = email_err
            if email_ok:
                logging.info(f"E-mail enviado via Brevo com sucesso para {email}")
            else:
                logging.warning(f"E-mail não enviado via Brevo: {email_err}")
        except Exception as e:
            # NÃO derruba o endpoint
            email_enviado = False
            email_erro = str(e)
            logging.exception(f"Falha ao enviar e-mail (Brevo): {email_erro}")

        return {
            "ok": True,
            "mensagem": "Análise concluída. Confira o resultado abaixo.",
            "html": resposta_html,
            "email_enviado": email_enviado,
            "email_erro": email_erro,
            "bypass_pagamento": bypass_pagamento,
            "version": MAIN_INTERNAL_VERSION,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"Erro interno ao analisar contrato: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao analisar contrato.")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logging.info(f"Arquivo temporário '{temp_path}' removido.")
            except Exception as e:
                logging.error(f"Erro ao remover arquivo temporário {temp_path}: {e}")
