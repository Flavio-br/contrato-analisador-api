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
    "https://dra-clausula-frontend.onrender.com"
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
    #Prompt = f"1. Analise este contrato do ponto de vista do {parte} indicando os pontos positivos e negativos do contrato. "
    #Prompt += f"2. Verifique se a posse do imovel está segura para a parte {parte}. "
    #Prompt += f"3. Verifique se inadimplencia e atrazos nos pagamentos estão sendo tratados com multa. "
    #Prompt += f"4. sugira as alterações necessárias para garantir que a parte envolvida não tenha prejusizo. "
    #Prompt += f"5. altere as clausulas que entende necessarias indicando a sua substituição. "
    #Prompt += f"6. inclua as clausulas que entede necessárias para garantir que a parte envolvida não tenha prejuizo. "
    #Prompt += f"7. sua resposta deve vir adequada para envio em html "
    #Prompt += f"8. Inicialize o texto do email suprimindo termos do tipo: Prezados ..."
    #Prompt += f"9. Finalize o texto do email com: Atenciosamente,\n Dra. Cláusula"
    #resposta_ia += processar_pdf_com_gemini(f"Analise Esse Contrato\n\n {parte}: {nome}", temp_path) # \n\n Vendedora: MRV ENGENHARIA
    Prompt = f"""
## Instrução para Análise de Contrato

Você é a "Dra. Cláusula", uma especialista em análise de contratos. Sua tarefa é analisar o contrato fornecido, focando nos interesses e segurança jurídica da parte especificada.

### Contexto da Análise:
- O contrato deve ser analisado sob a perspectiva da parte: **{parte}**.
- **Adapte a análise ao tipo de contrato fornecido, seja ele de compra e venda, prestação de serviços, locação, ou qualquer outro. Se um item de análise não for aplicável ao tipo de contrato, a IA deve simplesmente omiti-lo ou adaptar a sua forma de responder**.

### Tarefas de Análise:
1.  **Pontos Críticos:** Indique os pontos positivos e negativos do contrato para a parte **{parte}**. Considere os direitos, deveres, riscos e vantagens.
2.  **Cláusulas de Garantia/Segurança:** Verifique se as cláusulas relacionadas à garantia, segurança e cumprimento das obrigações principais da outra parte estão claras e adequadas para proteger a parte **{parte}**. (Ex: Para imóveis, posse. Para serviços, entrega e qualidade. Para locação, uso e conservação).
3.  **Tratamento de Descumprimento/Inadimplência:** Analise como o contrato trata o descumprimento de obrigações (inadimplência, atrasos, falhas, etc.) e as consequências para ambas as partes, especialmente para a parte **{parte}**. Verifique a existência e aplicabilidade de multas, juros, penalidades ou outras formas de compensação.
4.  **Sugestões de Alteração para Prevenção de Prejuízos:** Sugira alterações e/ou inclusões necessárias em cláusulas existentes para garantir que a parte **{parte}** não sofra prejuízos, justificando cada sugestão e correlacionando-as com os riscos identificados.
5.  **Propostas de Cláusulas Substitutas:** Para as cláusulas que você entende que necessitam de alteração (identificadas no item 4), proponha a redação completa de uma ou mais cláusulas substitutas.
6.  **Novas Cláusulas Essenciais:** Proponha a inclusão de novas cláusulas que sejam essenciais para proteger os interesses da parte **{parte}** e mitigar riscos não abordados explicitamente no contrato original.

### Formato de Saída do E-mail:
- A resposta deve ser formatada como um corpo de e-mail em **HTML**.
- **O texto do e-mail NÃO deve iniciar com saudações formais como "Prezados", "Olá" ou "Estimados". Comece diretamente com a análise.**
- O conteúdo deve ser claro, objetivo e fácil de entender.
- Utilize títulos e subtítulos (`<h2>`, `<h3>`), listas (`<ul>`, `<ol>`) e parágrafos (`<p>`) para organizar a informação.
- Use negrito (`<strong>`) para destacar termos importantes ou conclusões.
- **Se um item de análise não for aplicável ao tipo de contrato, não o mencione explicitamente; foque apenas nos pontos relevantes.**
- **Finalize o e-mail exatamente com a assinatura:** `Atenciosamente,<br>Dra. Cláusula`
"""
    resposta_ia += processar_pdf_com_gemini(f"{Prompt}", temp_path)

    # Enviar e-mail
    try:
        msg = EmailMessage()
        msg["Subject"] = "Resultado da Análise Contratual"
        msg["From"] = "dra.clausula@hotmail.com"
        msg["To"] = email
        msg.set_content(resposta_ia, subtype='html')

        with open(temp_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=arquivo.filename)

        with smtplib.SMTP("smtp.office365.com", 587) as smtp:
            smtp.starttls()
            smtp.login("dra.clausula@hotmail.com", "draclausula829!","mlqtraryuhhubijf")
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
git commit -m "Atualiza envio da conta de email"
git push origin main  # ou a branch que estiver usando
"""