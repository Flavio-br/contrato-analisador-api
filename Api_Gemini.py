import os
import fitz  # PyMuPDF
import google.generativeai as genai

# ===============================
# Carregamento do .env (LOCAL)
# ===============================
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # Em produção (Render), ignora

API_GEMINI_INTERNAL_VERSION = "1.03"

# ===============================
# Configuração da API Gemini
# ===============================
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

_gemini_model = None
_gemini_init_error = None

def _get_model():
    """Inicializa o modelo do Gemini sob demanda.
    Não levanta exceção no import para não derrubar a API inteira se faltar chave.
    """
    global _gemini_model, _gemini_init_error

    if _gemini_model is not None:
        return _gemini_model

    if _gemini_init_error is not None:
        return None

    if not API_KEY:
        _gemini_init_error = "GEMINI_API_KEY não definida. Configure no Render > Environment."
        return None

    try:
        genai.configure(api_key=API_KEY)
        _gemini_model = genai.GenerativeModel(MODEL_NAME)
        return _gemini_model
    except Exception as e:
        _gemini_init_error = f"Erro ao inicializar o modelo Gemini '{MODEL_NAME}': {e}"
        return None

# ===============================
# Leitura de PDF

# ===============================
def _read_pdf_content(pdf_file_path: str):
    try:
        doc = fitz.open(pdf_file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"[Api_Gemini] Erro ao ler PDF: {e}")
        return None

# ===============================
# Processamento com Gemini
# ===============================
def processar_pdf_com_gemini(prompt: str, pdf_file_path: str) -> str:
    print(f"[Api_Gemini v{API_GEMINI_INTERNAL_VERSION}] PDF recebido: {pdf_file_path}")

    pdf_text = _read_pdf_content(pdf_file_path)
    if not pdf_text:
        return "Erro: não foi possível ler o conteúdo do PDF."

    full_prompt = (
        f"{prompt}\n\n"
        f"=== CONTEÚDO DO DOCUMENTO ===\n\n"
        f"{pdf_text}"
    )

    model = _get_model()
    if model is None:
        return f"Erro ao gerar resposta do Gemini: {_gemini_init_error or 'modelo indisponível.'}"

    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Erro ao gerar resposta do Gemini: {e}"

# ===============================
# Execução direta (debug)
# ===============================
if __name__ == "__main__":
    print("Api_Gemini carregado com sucesso.")
    print(f"Versão interna: {API_GEMINI_INTERNAL_VERSION}")
    print(f"Modelo: {MODEL_NAME}")