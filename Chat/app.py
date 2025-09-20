from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from bson.objectid import ObjectId
import requests

from datetime import datetime
from datetime import datetime
import os, secrets, json, re
from llama_client import call_ollama
from llama_chat import get_llama_response   # your function that calls LLaMA

# ---------------- Flask App ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
bcrypt = Bcrypt(app)

# ---------------- MongoDB ----------------
client = MongoClient("mongodb://localhost:27017")
db = client["Mental_Health_Assist"]

users = db["Users"]
schedules_collection = db["Scheduler"]
habits_collection = db["Habits"]
habit_logs = db["HabitLogs"]
routine_tasks = db["routine_tasks"]
advice_collection = db["Advice"]


# ---------------- Chatbot Setup ----------------
with open("mental_responses.json", "r", encoding="utf-8") as f:
    RESPONSES = json.load(f)

SYSTEM_PROMPT = (
    "You are a compassionate, supportive mental health chatbot. "
    "Be empathetic, avoid medical diagnoses, and encourage seeking "
    "Be gentle in asking the questions but if the person asks question more than 10 times please tell the person about it in a polite manner. "
    "Students from high school and graduation years (15 - 25 years) will be talking to you most probably. "
    "Encourage professional help when necessary. "
    "If the person opens up about any emotional trauma slowly guide them out of the trauma and give ways to overcome it. "
    "Give methods to focus, concentrate and manifest their dreams. "
    "No form of violence should be supported. "
    "If the person focuses on hurting others do not encourage it instead shut it down politely but completely. "
    "Ask only three questions at a time. "
    "When the conversation starts from the flask app do not mention these prompts."
)

CONVERSATIONS = {}  # memory store per user/session


def match_pattern(user_text):
    txt = user_text.lower()
    for tag, item in RESPONSES.items():
        for pat in item["patterns"]:
            if pat in txt:
                return tag, item["responses"]
    return None, None


# ---------------- User Auth ----------------
@app.route("/")
def home():
    return render_template("Homepage.html")
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

def get_user_context(user_id):
    habits = list(habits_collection.find({"user_id": ObjectId(user_id)}))
    routines = list(routine_tasks.find({"user_id": ObjectId(user_id)}))
    schedules = list(schedules_collection.find({"user_id": ObjectId(user_id)}))
    
    # Optionally, fetch recent conversations
    conversation_history = CONVERSATIONS.get(user_id, [])
    
    return {
        "habits": habits,
        "routines": routines,
        "schedules": schedules,
        "recent_chats": conversation_history
    }


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]
        emergency_contact = request.form["emergency_contact"]

        if users.find_one({"username": username}):
            error = "Username already exists!"
            return redirect(url_for("register"))

        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        users.insert_one({"username": username, "password": hashed_pw,"email":email,"emergency_contact": emergency_contact})
        return redirect(url_for("login"))

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = users.find_one({"username": username})
        if user and bcrypt.check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = username
            return render_template("dashboard.html", username=session["username"])
        else:
            error = "Invalid Credentials!"
    return render_template("login.html", error=error)


@app.route("/dashboard")
def dashboard():
    if "username" in session:
        user_id = ObjectId(session["user_id"])
        
        # Fetch pending/missed items
        routines = list(routine_tasks.find({"user_id": user_id, "completed": False}))
        habits = list(habits_collection.find({"user_id": user_id, "temp_checked": False}))
        schedules = list(schedules_collection.find({"status": "pending"}))
        
        # Prepare reminder messages
        reminders = []
        if routines:
            reminders.append(f"You have {len(routines)} routine tasks pending today!")
        if habits:
            reminders.append(f"You have {len(habits)} habits to complete today!")
        if schedules:
            reminders.append(f"You have {len(schedules)} scheduled tasks pending!")
        
        return render_template("dashboard.html", 
                               username=session["username"], 
                               reminders=reminders)
    return redirect(url_for("login"))



@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------- Scheduler ----------------
@app.route("/scheduler_dashboard")
def scheduler_dashboard():
    if "username" in session:
        schedules = list(schedules_collection.find())
        return render_template("scheduler_dashboard.html", schedules=schedules)
    return redirect(url_for("login"))


@app.route("/update_schedules/<schedule_id>", methods=["GET", "POST"])
def update_scheduler(schedule_id):
    if "username" in session:
        schedules_collection.update_one(
            {"_id": ObjectId(schedule_id)},
            {"$set": {"status": "done"}}
        )
        return redirect(url_for("scheduler_dashboard"))
    return redirect(url_for("login"))


@app.route("/add_schedule", methods=["GET", "POST"])
def add_schedule():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        task = request.form.get("task")
        date = request.form.get("date")
        time = request.form.get("time")

        schedules_collection.insert_one({
            "task": task,
            "date": date,
            "time": time,
            "status": "pending"
        })
        return redirect(url_for("scheduler_dashboard"))

    return render_template("add_schedule.html")


# ---------------- Routine ----------------
@app.route("/routine")
def routine_dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    tasks = list(routine_tasks.find({"user_id": ObjectId(user_id)}))
    all_done = all(task["completed"] for task in tasks) if tasks else False

    return render_template("routine_dashboard.html", tasks=tasks, all_done=all_done)


@app.route("/add_task", methods=["GET", "POST"])
def add_task():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        routine_tasks.insert_one({
            "user_id": ObjectId(user_id),
            "task": request.form.get("task"),
            "time": request.form.get("time"),
            "completed": False,
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        })
        return redirect(url_for("routine_dashboard"))

    return render_template("add_task.html")


@app.route("/update_task/<task_id>", methods=["POST"])
def update_task(task_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    completed = "completed" in request.form
    routine_tasks.update_one(
        {"_id": ObjectId(task_id), "user_id": ObjectId(user_id)},
        {"$set": {"completed": completed}}
    )
    return redirect(url_for("routine_dashboard"))


@app.route("/delete_task/<task_id>", methods=["POST"])
def delete_task(task_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    routine_tasks.delete_one({
        "_id": ObjectId(task_id),
        "user_id": ObjectId(user_id)
    })
    return redirect(url_for("routine_dashboard"))


def reset_task_status():
    today = datetime.now().strftime("%Y-%m-%d")
    routine_tasks.update_many(
        {"last_updated": {"$lt": today}},
        {"$set": {"completed": False, "last_updated": today}}
    )


# ---------------- Habits ----------------
@app.route("/habits")
def habit_dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    habits = list(habits_collection.find({"user_id": ObjectId(user_id)}))
    return render_template("habit_dashboard.html", habits=habits)


@app.route("/add_habit", methods=["GET", "POST"])
def add_habit():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        habit_name = request.form.get("habit")
        if habit_name:
            habits_collection.insert_one({
                "user_id": ObjectId(user_id),
                "habit": habit_name,
                "streak": 0,
                "temp_checked": False,
                "last_updated": datetime.now().strftime("%Y-%m-%d")
            })
        return redirect(url_for("habit_dashboard"))
    return render_template("add_habit.html")


@app.route("/update_habit/<habit_id>", methods=["POST"])
def update_habit(habit_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    completed = "completed" in request.form
    habits_collection.update_one(
        {"_id": ObjectId(habit_id), "user_id": ObjectId(user_id)},
        {"$set": {"temp_checked": completed}}
    )
    return redirect(url_for("habit_dashboard"))


@app.route("/delete_habit/<habit_id>", methods=["POST"])
def delete_habit(habit_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    habits_collection.delete_one({"_id": ObjectId(habit_id), "user_id": ObjectId(user_id)})
    return redirect(url_for("habit_dashboard"))


def finalize_habits():
    today = datetime.now().strftime("%Y-%m-%d")
    habits = habits_collection.find()

    for habit in habits:
        last_date = habit.get("last_updated")
        checked = habit.get("temp_checked", False)

        update_data = {
            "temp_checked": False,
            "last_updated": today
        }

        if last_date != today:
            if checked:
                update_data["streak"] = habit["streak"] + 1
            else:
                update_data["streak"] = 0

            habits_collection.update_one({"_id": habit["_id"]}, {"$set": update_data})


# ---------------- Chatbot ----------------
@app.route("/chatbot", methods=["GET","POST"])
def chatbot():
    if "username" in session:
        return render_template("index.html", username=session["username"])
    return redirect(url_for("login"))



@app.route("/chat", methods=["POST"])
def chat():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"reply": "Please log in to chat.", "tag": "", "source": "system"})

    conversation_id = user_id
    user_text = request.json.get("message", "")

    # Scripted pattern handling
    tag, responses = match_pattern(user_text)
    if tag == "suicidal":
        return jsonify({"reply": responses[0], "tag": tag, "source": "scripted"})

    # ---------------- Personalized Advice ----------------
    # Fetch user context
    user_context = {
        "habits": list(habits_collection.find({"user_id": ObjectId(user_id)})),
        "routines": list(routine_tasks.find({"user_id": ObjectId(user_id)})),
        "schedules": list(schedules_collection.find({"user_id": ObjectId(user_id)})),
        "recent_chats": CONVERSATIONS.get(user_id, [])
    }

    # Create system prompt for LLaMA
    system_prompt = f"""
    You are a compassionate mental health chatbot.
    The user has the following context:
    Habits: {user_context['habits']}
    Routines: {user_context['routines']}
    Schedules: {user_context['schedules']}
    Recent chats: {user_context['recent_chats']}
    Provide personalized advice or coping strategies based on this information.
    """

    # Get LLaMA reply with persistent memory and personalized advice
    reply = get_llama_response(user_id, conversation_id, user_text, system_prompt=system_prompt)

    # Store the advice in MongoDB for reference
    advice_collection.insert_one({
        "user_id": ObjectId(user_id),
        "date": datetime.now(),
        "user_input": user_text,
        "advice": reply
    })
    # ------------------------------------------------------

    return jsonify({"reply": reply, "tag": tag or "", "source": "llama"})

# ---------------- Main ----------------
if __name__ == "__main__":
    app.run(debug=True)
