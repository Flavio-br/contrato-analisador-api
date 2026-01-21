import google.generativeai as genai
import os
import fitz  # PyMuPDF para leitura de PDF

API_GEMINI_INTERNAL_VERSION = "1.01"

# --- Configuração da API Gemini ---
# Certifique-se de que sua chave de API está definida como uma variável de ambiente.
# Ex: export GEMINI_API_KEY='SUA_CHAVE_AQUI' (Linux/macOS)
# ou set GEMINI_API_KEY=SUA_CHAVE_AQUI (Windows)

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não está definida. Configure-a no Render (Environment) para habilitar a análise.")

genai.configure(api_key=API_KEY)

# --- Nome do Modelo Gemini ---
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

try:
    # A inicialização do modelo pode ser feita uma vez ou dentro da função, dependendo do uso.
    # Para simplicidade e eficiência, vamos inicializá-lo aqui no escopo do módulo.
    _gemini_model = genai.GenerativeModel(MODEL_NAME)
except Exception as e:
    raise RuntimeError(f"Erro ao inicializar o modelo '{MODEL_NAME}': {e}. Verifique o nome do modelo e sua chave de API. (Dica: use genai.list_models() para ver modelos disponíveis)")

# --- Função para Ler Conteúdo de PDF Local ---
def _read_pdf_content(pdf_file_path: str) -> str:
    """
    Lê um arquivo PDF do caminho fornecido e extrai todo o texto.
    Função interna (prefixo _) pois é um auxiliar para 'processar_pdf_com_gemini'.
    """
    full_text = ""
    try:
        doc = fitz.open(pdf_file_path)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            full_text += page.get_text()
        doc.close()
        return full_text
    except FileNotFoundError:
        print(f"Erro: O arquivo PDF não foi encontrado no caminho '{pdf_file_path}'.")
        return None
    except Exception as e:
        print(f"Ocorreu um erro ao ler o PDF: {e}")
        return None

# --- Função Principal para Processar PDF com Gemini ---
def processar_pdf_com_gemini(prompt: str, pdf_file_path: str) -> str:
    """
    Lê um arquivo PDF, combina seu conteúdo com um prompt e obtém
    uma resposta do modelo Gemini 1.5 Flash.

    Args:
        prompt (str): O prompt de texto a ser enviado ao Gemini.
        pdf_file_path (str): O caminho completo para o arquivo PDF.

    Returns:
        str: A resposta gerada pelo modelo Gemini, ou uma mensagem de erro.
    """
    print(f"\n[Api_gemini.py] Processando PDF: {pdf_file_path}")
    print(f"[Api_gemini.py] Prompt recebido: '{prompt}'")

    # 1. Ler o conteúdo do PDF
    pdf_text_content = _read_pdf_content(pdf_file_path)

    if not pdf_text_content:
        return "Erro: Não foi possível obter o conteúdo do PDF."

    # 2. Combinar o prompt com o conteúdo do PDF
    # Sugestão: você pode ajustar este formato de prompt conforme sua necessidade.
    # Por exemplo, pode ser "prompt\n\n[CONTEUDO_PDF]\n{pdf_text_content}"
    full_gemini_prompt = f"{prompt}\n\nConteúdo do Documento:\n\n{pdf_text_content}"

    # 3. Enviar para o Gemini e obter a resposta
    print("[Api_gemini.py] Enviando conteúdo e prompt para o Gemini...")
    try:
        response = _gemini_model.generate_content(full_gemini_prompt)
        return response.text
    except Exception as e:
        return f"Erro ao gerar resposta do Gemini: {e}"

# Este bloco garante que o código dentro dele só seja executado se o arquivo for rodado diretamente,
# e não quando é importado como um módulo.
if __name__ == "__main__":
    print("Este arquivo (Api_gemini.py) é um módulo.")
    print("Para usá-lo, importe 'processar_pdf_com_gemini' em outro script.")
    # Exemplo de como você o usaria se rodasse diretamente para teste:
    # prompt_exemplo = "Resuma este documento em três frases."
    # caminho_pdf_exemplo = "caminho/para/o/seu/documento.pdf" # MUDAR ESTE CAMINHO PARA TESTE DIRETO
    #
    # try:
    #     resultado = processar_pdf_com_gemini(prompt_exemplo, caminho_pdf_exemplo)
    #     print("\n--- Resultado do Teste Direto ---")
    #     print(resultado)
    # except ValueError as e:
    #     print(f"Erro de configuração: {e}")
    # except RuntimeError as e:
    #     print(f"Erro de inicialização do modelo: {e}")