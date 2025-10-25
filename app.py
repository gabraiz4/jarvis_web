import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from pathlib import Path
import pytesseract
from PIL import Image
import PyPDF2
import docx
from groq import Groq
from dotenv import load_dotenv

# -------------------------------
# 🔹 Config inicial
# -------------------------------
load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_KEY:
    raise RuntimeError("❌ Falta a variável GROQ_API_KEY no arquivo .env")

client = Groq(api_key=GROQ_KEY)

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXT = {".txt",".md",".py",".csv",".json",".log",".pdf",".docx",".png",".jpg",".jpeg",".gif",".bmp"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

STATE = {
    "last_doc_text": None,
    "last_doc_name": None,
    "last_img_text": None,
    "last_img_name": None
}

# -------------------------------
# 🧩 Funções auxiliares
# -------------------------------
def extract_text_from_file(path: Path):
    ext = path.suffix.lower()
    if ext in (".txt", ".md", ".py", ".csv", ".json", ".log"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        text_pages = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for i, p in enumerate(reader.pages):
                txt = p.extract_text() or ""
                text_pages.append(f"--- Página {i+1} ---\n{txt}\n")
        return "\n".join(text_pages)
    if ext == ".docx":
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return f"[Formato {ext} não suportado]"

def ocr_image(path: Path):
    try:
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang='eng+por')
        return text.strip()
    except Exception as e:
        return f"[OCR falhou: {e}]"

# -------------------------------
# 🤖 Função de IA (Groq)
# -------------------------------
def ask_ai(prompt):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Erro ao chamar Groq: {e}]"

# -------------------------------
# 🌐 Rotas Flask
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html", state=STATE)

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return redirect(url_for("index"))
    filename = secure_filename(f.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return "Extensão não permitida", 400
    dest = UPLOAD_FOLDER / filename
    f.save(dest)

    if ext in (".png",".jpg",".jpeg",".gif",".bmp"):
        txt = ocr_image(dest)
        STATE["last_img_text"] = txt
        STATE["last_img_name"] = filename
    else:
        content = extract_text_from_file(dest)
        STATE["last_doc_text"] = content
        STATE["last_doc_name"] = filename

    return redirect(url_for("index"))

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error":"Nenhuma pergunta enviada"}), 400

    doc_text = STATE.get("last_doc_text") or STATE.get("last_img_text")
    doc_name = STATE.get("last_doc_name") or STATE.get("last_img_name")

    if doc_text:
        prompt = f"Você é o Jarvis. Documento: {doc_name}\nConteúdo:\n{doc_text}\n\nUsuário perguntou: {text}\nResponda de forma direta e clara."
    else:
        prompt = f"Você é o Jarvis, um assistente que responde de forma simples e direta. Pergunta: {text}"

    ai_resp = ask_ai(prompt)
    return jsonify({"answer": ai_resp})

if __name__ == "__main__":
    app.run(debug=True)