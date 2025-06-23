from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import aiofiles
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from Api_Gemini import processar_pdf_com_gemini

# Carregar variáveis de ambiente (.env)
load_dotenv()

app = FastAPI()

# --- INÍCIO DA CONFIGURAÇÃO CORS ---
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8080",
    "https://dra-clausula.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- FIM DA CONFIGURAÇÃO CORS ---

@app.post("/api/contrato/analisar")
async def analisar_contrato(
    nome: str = Form(...),
    email: str = Form(...),
    parte: str = Form(...),
    arquivo: UploadFile = File(...)
):
    if not arquivo:
        return JSONResponse(status_code=400, content={"erro": "Arquivo não enviado."})

    # Salvar o arquivo temporariamente
    temp_path = f"temp_{arquivo.filename}"
    async with aiofiles.open(temp_path, 'wb') as out_file:
        content = await arquivo.read()
        await out_file.write(content)

    # Prompt para IA
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

    resposta_ia = processar_pdf_com_gemini(Prompt, temp_path)

    # Enviar e-mail
    try:
        EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS") or "dra.clausula@hotmail.com"
        EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") or "kphtrhucqjwdmmgv"

        msg = EmailMessage()
        msg["Subject"] = "Resultado da Análise Contratual"
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = email
        msg.set_content(resposta_ia, subtype='html')

        with open(temp_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=arquivo.filename)

        with smtplib.SMTP("smtp.office365.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return JSONResponse(status_code=500, content={"erro": f"Falha ao enviar e-mail: {str(e)}"})

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {"mensagem": "Análise enviada por e-mail com sucesso! Verifique sua caixa de entrada e spam."}
