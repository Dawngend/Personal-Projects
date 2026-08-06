import os

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_module(uploaded_file) -> str:
    """Saves a file uploaded via Streamlit to the local uploads directory."""
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def get_available_modules() -> list[str]:
    """Returns a list of filenames currently saved in the uploads directory."""
    return [f for f in os.listdir(UPLOAD_DIR) if f.endswith(('.pdf', '.pptx'))]