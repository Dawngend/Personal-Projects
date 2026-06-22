import streamlit as st
import random
import json
import os
import database as db 
from generator import generate_custom_deck 

# ── Theme & Configuration ────────────────────────────────────────────────────
# We set layout to "centered" natively, but our CSS will strictly enforce the width
st.set_page_config(page_title="Andy: Study Buddy", page_icon="🤖", layout="centered")

# The Premium "Dark Navy & Cream" CSS Injection
st.markdown("""
    <style>
    /* 1. Force the main background to a rich, dark navy for Dark Mode compatibility */
    .stApp {
        background-color: #0D1B2A !important; 
    }
    
    /* 2. Centralize and restrict the width of the main content block */
    .main .block-container {
        max-width: 750px !important;
        padding-top: 3rem !important;
        padding-bottom: 3rem !important;
        margin: 0 auto !important;
    }

    /* 3. The "Cream Card" styling for questions and forms */
    .quiz-card {
        background-color: #FDFDF9 !important;
        color: #1A365D !important;
        padding: 30px !important;
        border-radius: 16px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.4) !important;
        margin-bottom: 25px !important;
        text-align: center;
        border-top: 5px solid #2B6CB0;
    }
    
    /* Typography inside the card */
    .quiz-card h3 {
        color: #1A365D !important;
        font-weight: 700 !important;
        margin-bottom: 10px !important;
    }
    .quiz-card p {
        font-size: 1.1rem !important;
        color: #334155 !important;
    }

    /* 4. Upgrade Button Aesthetics */
    div.stButton > button {
        width: 100%;
        border-radius: 12px;
        background-color: #1E293B; /* Dark slate for default buttons */
        color: #FDFDF9;
        font-weight: 600;
        border: 2px solid transparent;
        transition: all 0.2s ease-in-out;
        padding: 10px;
    }
    div.stButton > button:hover {
        border: 2px solid #2B6CB0;
        background-color: #0D1B2A;
    }
    
    /* Primary buttons (Correct answers / Submit) */
    div.stButton > button[kind="primary"] {
        background-color: #2B6CB0 !important;
        color: #FDFDF9 !important;
        border: none !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1A365D !important;
    }

    /* Remove Streamlit default header/footer for an app-like feel */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ── Backend Storage Setup ────────────────────────────────────────────────────
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_module_for_andy(uploaded_file) -> str:
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def get_available_modules() -> list[str]:
    if not os.path.exists(UPLOAD_DIR):
        return []
    return [f for f in os.listdir(UPLOAD_DIR) if f.endswith(('.pdf', '.pptx'))]

# ── Session State Initialization ─────────────────────────────────────────────
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "cards_queue" not in st.session_state:
    st.session_state.cards_queue = []
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "wrong_attempts_on_card" not in st.session_state:
    st.session_state.wrong_attempts_on_card = set() 
if "failed_cards_pool" not in st.session_state:
    st.session_state.failed_cards_pool = [] 
if "card_status" not in st.session_state:
    st.session_state.card_status = "unanswered" 
if "answered_correctly" not in st.session_state:         
    st.session_state.answered_correctly = False          

# ── App Navigation ───────────────────────────────────────────────────────────
st.sidebar.title("🤖 Andy's Hub")
app_mode = st.sidebar.radio("Navigation", ["📚 Study Dashboard", "✨ Create New Reviewer"])
st.sidebar.divider()
st.sidebar.caption("Designed for optimal focus. Blue & Cream Theme Active.")

# =============================================================================
# MODE 1: CREATE NEW REVIEWER (ANDY'S WORKSHOP)
# =============================================================================
if app_mode == "✨ Create New Reviewer":
    st.markdown("<h1 style='color: #FDFDF9; text-align: center;'>✨ Craft a Reviewer</h1>", unsafe_allow_html=True)
    
    st.markdown("""
        <div class="quiz-card">
            <h3>1. Upload Materials</h3>
            <p>Feed Andy your PDFs or PPTs so he can analyze the concepts.</p>
        </div>
    """, unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Drop files here", type=['pdf', 'pptx'], accept_multiple_files=True, label_visibility="collapsed")
    
    if uploaded_files:
        for file in uploaded_files:
            save_module_for_andy(file)
        st.success(f"Successfully saved {len(uploaded_files)} file(s)!")

    st.markdown("""
        <div class="quiz-card" style="margin-top: 2rem;">
            <h3>2. Configure Output</h3>
            <p>Set your parameters for the perfect situational quiz.</p>
        </div>
    """, unsafe_allow_html=True)
    available_files = get_available_modules()
    
    if not available_files:
        st.info("Upload some files above to unlock the generator.")
    else:
        with st.form("generation_form"):
            selected_files = st.multiselect("Select modules to include:", available_files)
            deck_name = st.text_input("Reviewer Name (e.g., Midterm Coverage)")
            subject_name = st.text_input("Subject (e.g., Computer Science)")
            
            # The upgraded exact number input we discussed
            target_questions = st.number_input("How many total situational questions do you want?", min_value=1, max_value=100, value=20, step=1)
            
            submit_button = st.form_submit_button("🚀 Generate with Andy", type="primary")
            
            if submit_button:
                if not selected_files:
                    st.error("Please select at least one module!")
                elif not deck_name or not subject_name:
                    st.error("Please fill out the Reviewer Name and Subject.")
                else:
                    with st.spinner(f"Andy is reading and crafting exactly {target_questions} tricky scenarios..."):
                        new_deck_id = generate_custom_deck(
                            selected_files=selected_files,
                            deck_name=deck_name,
                            subject=subject_name,
                            total_questions=target_questions
                        )
                        if new_deck_id:
                            st.success(f"Done! Andy created '{deck_name}'. Switch to the Study Dashboard!")
                            st.balloons()
                        else:
                            st.error("Andy couldn't generate the deck. Check terminal logs.")

# =============================================================================
# MODE 2: STUDY DASHBOARD 
# =============================================================================
elif app_mode == "📚 Study Dashboard":
    st.markdown("<h1 style='color: #FDFDF9; text-align: center;'>📚 The Dojo</h1>", unsafe_allow_html=True)
    decks = db.get_decks()

    if not decks:
        st.warning("No decks found. Head over to 'Create New Reviewer'!")
    else:
        deck_options = {d[0]: f"{d[1]} ({d[3]})" for d in decks}
        selected_deck_id = st.selectbox("Select a Reviewer Deck", options=list(deck_options.keys()), format_func=lambda x: deck_options[x], label_visibility="collapsed")

        if st.button("Launch Session", type="primary"):
            raw_cards = db.get_cards_for_deck(selected_deck_id)
            if not raw_cards:
                st.error("This deck has no questions!")
            else:
                random.shuffle(raw_cards)
                st.session_state.cards_queue = []
                for c in raw_cards:
                    st.session_state.cards_queue.append({
                        "id": c[0],
                        "type": c[2],
                        "question": c[3],
                        "correct_answer": c[4],
                        "options": json.loads(c[5]) if c[5] else []
                    })
                st.session_state.current_index = 0
                st.session_state.wrong_attempts_on_card = set()
                st.session_state.failed_cards_pool = []
                st.session_state.answered_correctly = False
                st.session_state.quiz_started = True

    if st.session_state.quiz_started and st.session_state.current_index < len(st.session_state.cards_queue):
        current_card = st.session_state.cards_queue[st.session_state.current_index]
        
        # Visual Progress Bar
        progress_val = st.session_state.current_index / len(st.session_state.cards_queue)
        st.progress(progress_val)
        st.markdown(
            f"<div style='text-align: center; color: #94A3B8;'>Question {st.session_state.current_index + 1} of {len(st.session_state.cards_queue)}</div>",
            unsafe_allow_html=True,
        )
        
        # Centralized Cream Question Card
        st.markdown(f"""
            <div class="quiz-card">
                <h3 style="font-size: 1rem; color: #64748B !important;">🤖 Andy Asks:</h3>
                <p style="font-weight: 500;">{current_card["question"]}</p>
            </div>
        """, unsafe_allow_html=True)
        
        options = current_card["options"]
        correct = current_card["correct_answer"]
        
        # --- PHASE 1: GUESSING ---
        if not st.session_state.answered_correctly:
            for option in options:
                if option in st.session_state.wrong_attempts_on_card:
                    st.button(f"❌ {option}", key=f"wrong_{st.session_state.current_index}_{option}", disabled=True)
                else:
                    if st.button(option, key=f"opt_{st.session_state.current_index}_{option}"):
                        if option == correct:
                            st.session_state.answered_correctly = True 
                            st.rerun()
                        else:
                            st.session_state.wrong_attempts_on_card.add(option)
                            if current_card not in st.session_state.failed_cards_pool:
                                st.session_state.failed_cards_pool.append(current_card)
                                db.update_card_miss_count(current_card["id"]) 
                            st.rerun()

            if st.session_state.wrong_attempts_on_card:
                st.warning("Not quite right. Analyze the scenario and try again.")

        # --- PHASE 2: REVIEW MODE ---
        else:
            for option in options:
                if option == correct:
                    st.button(f"✅ {option}", key=f"correct_{st.session_state.current_index}_{option}", disabled=True, type="primary")
                else:
                    st.button(option, key=f"gray_{st.session_state.current_index}_{option}", disabled=True)
            
            st.success("🎯 Spot on! Take a moment to review your logic before moving on.")
            
            # Use columns to center the Next Question button nicely
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("➡️ Next Question", type="primary"):
                    st.session_state.current_index += 1
                    st.session_state.wrong_attempts_on_card.clear()
                    st.session_state.answered_correctly = False 
                    st.rerun()

    elif st.session_state.quiz_started:
        st.balloons()
        st.markdown("""
            <div class="quiz-card" style="margin-top: 3rem;">
                <h3>🏁 Round Cleared!</h3>
                <p>Excellent work. Andy has recorded your stats.</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reflash Entire Deck"):
                st.session_state.current_index = 0
                st.session_state.wrong_attempts_on_card.clear()
                st.session_state.failed_cards_pool = []
                st.session_state.answered_correctly = False
                st.rerun()
                
        with col2:
            if st.session_state.failed_cards_pool:
                if st.button(f"🔴 Practice Missed ({len(st.session_state.failed_cards_pool)})"):
                    st.session_state.cards_queue = list(st.session_state.failed_cards_pool)
                    st.session_state.failed_cards_pool = []
                    st.session_state.current_index = 0
                    st.session_state.wrong_attempts_on_card.clear()
                    st.session_state.answered_correctly = False
                    st.rerun()
            else:
                st.button("✨ Perfect Score Achieved!", disabled=True, type="primary")