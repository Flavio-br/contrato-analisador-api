from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
# IMPORTANTE: Adicione esta linha para importar o CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware
import aiofiles
import os
import smtplib
from email.message import EmailMessage
from Api_Gemini import processar_pdf_com_gemini

app = FastAPI()

# --- INÍCIO DA CONFIGURAÇÃO CORS ---
# Defina as origens (domínios) que terão permissão para acessar sua API.
# MUITO IMPORTANTE:
# 1. Se você está testando o HTML localmente abrindo o arquivo direto no navegador (ex: file:///C:/...),
#    a origem será 'null'. Inclua-o APENAS para desenvolvimento e testes locais.
#    Em produção, 'null' é um risco de segurança.
# 2. Se você está servindo o HTML localmente com um servidor simples (ex: http-server, python -m http.server),
#    a origem será algo como 'http://localhost:8000' ou 'http://127.0.0.1:8080'.
#    Verifique o console do seu servidor local para a porta exata.
# 3. Quando seu frontend HTML estiver em produção (publicado em um site),
#    substitua ou adicione o domínio desse site (ex: "https://www.meu-site-frontend.com").

origins = [
    "http://localhost",
    "http://localhost:8000", # Exemplo: se você usa 'python -m http.server'
    "http://127.0.0.1:8080", # Exemplo: se você usa 'http-server' (npm)
    #"null", # Permitir acesso de arquivos locais (file://). **Usar APENAS em desenvolvimento/testes!**
            # Remova esta linha em ambiente de produção para segurança.
    # Adicione aqui o domínio do seu frontend em produção, por exemplo:
    # "https://www.dra-clausula-frontend.com.br",
    "http://vendas.drogaquinze.com.br:45808"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # Lista de origens permitidas
    allow_credentials=True,       # Permite cookies e cabeçalhos de autorização
    allow_methods=["*"],          # Permite todos os métodos HTTP (GET, POST, etc.)
    allow_headers=["*"],          # Permite todos os cabeçalhos
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

    # Simular resposta de IA
    resposta_ia = f"Olá {nome}, segue análise solicitada." #\n\n(IA responderia aqui...)"
    Prompt = f"1. Analise este contrato do ponto de vista do {parte} indicando os pontos positivos e negativos do contrato. "
    Prompt += f"2. Verifique se a posse do imovel está segura para a parte {parte}. "
    Prompt += f"3. Verifique se inadimplencia e atrazos nos pagamentos estão sendo tratados com multa. "
    Prompt += f"4. sugira as alterações necessárias para garantir que a parte envolvida não tenha prejusizo. "
    Prompt += f"5. altere as clausulas que entende necessarias indicando a sua substituição. "
    Prompt += f"6. inclua as clausulas que entede necessárias para garantir que a parte envolvida não tenha prejuizo. "
    Prompt += f"7. sua resposta deve vir adequada para envio em html "
    Prompt += f"8. Inicialize o texto do email suprimindo termos do tipo: Prezados ..."
    Prompt += f"9. Finalize o texto do email com: Atenciosamente,\n Dra. Cláusula"
    #resposta_ia += processar_pdf_com_gemini(f"Analise Esse Contrato\n\n {parte}: {nome}", temp_path) # \n\n Vendedora: MRV ENGENHARIA
    resposta_ia += processar_pdf_com_gemini(f"{Prompt}", temp_path)

    # Enviar e-mail
    try:
        msg = EmailMessage()
        msg["Subject"] = "Resultado da Análise Contratual"
        msg["From"] = "sistema@drogaquinze.com.br"
        msg["To"] = email
        msg.set_content(resposta_ia, subtype='html')

        with open(temp_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=arquivo.filename)

        with smtplib.SMTP("smtp-legacy.office365.com", 587) as smtp:
            smtp.starttls()
            smtp.login("sistema@drogaquinze.com.br", "$ec@252")
            smtp.send_message(msg)

    except Exception as e:
        # É uma boa prática logar o erro completo no servidor para depuração
        print(f"Erro ao enviar e-mail: {e}")
        return JSONResponse(status_code=500, content={"erro": f"Falha ao enviar e-mail: {str(e)}"})


    finally:
        # Garante que o arquivo temporário seja removido mesmo se houver erro no envio do e-mail
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {"mensagem": "Análise enviada por e-mail com sucesso! Não esqueça de olhar na sua caixa de entrada e na caixa de spam."}

"""
GET DO PROJETO DANDO REPLACE - BAIXAR PROJETO

git reset --hard
git clean -fd
git pull origin main

Comandos para publicar alterações no GitHub:

git add .
git commit -m "Atualiza mensagem de retorno com aviso sobre spam"
git push origin main  # ou a branch que estiver usando
"""