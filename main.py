from fastapi import FastAPI, UploadFile, File, Form  # Corrigido aqui
from fastapi.responses import JSONResponse
import aiofiles
import os
import smtplib
from email.message import EmailMessage
from Api_Gemini import processar_pdf_com_gemini

app = FastAPI()

@app.post("/api/contrato/analisar")
async def analisar_contrato(
    nome: str = Form(...),
    email: str = Form(...),
    parte: str = Form(...),
       arquivo: UploadFile = File(...)  # Corrigido aqui
):
    if not arquivo:
        return JSONResponse(status_code=400, content={"erro": "Arquivo não enviado."})

    # Salvar o arquivo temporariamente
    temp_path = f"temp_{arquivo.filename}"
    async with aiofiles.open(temp_path, 'wb') as out_file:
        content = await arquivo.read()
        await out_file.write(content)

    # Simular resposta de IA
    resposta_ia = f"Olá {nome}, segue análise simulada para parte: {parte}.\n\n(IA responderia aqui...)"
    resposta_ia += processar_pdf_com_gemini(f"Analise Esse Contrato\n\n Comprador: {nome} \n\n Vendedora: MRV ENGENHARIA", arquivo.filename)

    # Enviar e-mail
    try:
        msg = EmailMessage()
        msg["Subject"] = "Resultado da Análise Contratual"
        msg["From"] = "sistema@drogaquinze.com.br"
        msg["To"] = email
        msg.set_content(resposta_ia)

        with open(temp_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=arquivo.filename)

        with smtplib.SMTP("smtp-legacy.office365.com", 587) as smtp:
            smtp.starttls()
            smtp.login("sistema@drogaquinze.com.br", "$ec@252")
            smtp.send_message(msg)

    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": f"Falha ao enviar e-mail: {str(e)}"})


    finally:
        os.remove(temp_path)

    return {"mensagem": "Análise enviada por e-mail com sucesso! Não esqueça de olhar na sua caixa de entrada e na caixa de spam."}

"""
Comandos para publicar alterações no GitHub:

--git add main.py
git add .
git commit -m "Atualiza mensagem de retorno com aviso sobre spam"
git push origin main  # ou a branch que estiver usando
"""
