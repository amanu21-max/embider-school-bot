import os
import logging
import sqlite3
from datetime import datetime
from io import BytesIO
from typing import Optional, List

import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, InputFile, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)
from dotenv import load_dotenv

load_dotenv()

# ====================== CONFIG - እዚህ ይቀይሩ ======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SCHOOL_NAME = "እምድብር አጠቃላይ ሁለተኛ ደረጃ ትምህርት ቤት"
DEVELOPER = "አማኑኤል መኮንን"
PHONE = "0920772686"
EMAIL = "amanuel@example.com"          # የእርስዎን ኢሜይል ያስገቡ

# የስራ ክፍሎች - በቀላሉ መጨመር / መቀየር ይችላሉ
DEPARTMENTS = [
    "አስተዳደር",
    "ሪጅስትራር",
    "አካዳሚክ ዳይሬክተር",
    "ፋይናንስ",
    "ሪከርድና መህደር",
    "ንብረት ክፍል",
    "ዲፓርትመንት ሀላፊ",
    "አጠቃላይ እስታፍ"
]

GRADES = ["9ኛ", "10ኛ", "11ኛ", "12ኛ"]
SECTIONS = ["A", "B", "C", "D", "E"]
DAYS = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ"]
PERIODS = ["1ኛ", "2ኛ", "3ኛ", "4ኛ", "5ኛ", "6ኛ", "7ኛ"]

# ====================== DATABASE ======================
def get_db():
    return sqlite3.connect("school.db", check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        role TEXT,
        department TEXT,
        phone TEXT,
        approved INTEGER DEFAULT 0,
        registered_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE,
        full_name TEXT,
        gender TEXT,
        grade TEXT,
        section TEXT,
        parent_phone TEXT,
        registered_by INTEGER,
        registered_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id TEXT UNIQUE,
        full_name TEXT,
        gender TEXT,
        subject TEXT,
        phone TEXT,
        department TEXT,
        telegram_id INTEGER,
        registered_by INTEGER,
        registered_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS class_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id TEXT,
        teacher_name TEXT,
        grade TEXT,
        section TEXT,
        subject TEXT,
        day TEXT,
        period TEXT,
        assigned_by INTEGER,
        assigned_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_name TEXT,
        grade TEXT,
        subject TEXT,
        exam_date TEXT,
        max_score REAL DEFAULT 100,
        created_by INTEGER,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        exam_id INTEGER,
        subject TEXT,
        score REAL,
        recorded_by INTEGER,
        recorded_at TEXT,
        UNIQUE(student_id, exam_id)
    )''')

    conn.commit()
    conn.close()

init_db()

# ====================== HELPERS ======================
def get_user(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, role, department, phone, approved FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "full_name": row[1], "role": row[2],
            "department": row[3], "phone": row[4], "approved": row[5]
        }
    return None

def is_approved(user_id: int) -> bool:
    user = get_user(user_id)
    return user and user["approved"] == 1

def has_role(user_id: int, roles: List[str]) -> bool:
    user = get_user(user_id)
    return user and user["approved"] == 1 and user["role"] in roles

def main_menu_keyboard(role: str):
    buttons = []

    if role in ["አስተዳደር", "ሪጅስትራር", "አካዳሚክ ዳይሬክተር"]:
        buttons.append([KeyboardButton("👨‍🎓 ተማሪ መመዝገቢያ")])
        buttons.append([KeyboardButton("👩‍🏫 መምህር መመዝገቢያ")])

    if role in ["አስተዳደር", "አካዳሚክ ዳይሬክተር", "ዲፓርትመንት ሀላፊ"]:
        buttons.append([KeyboardButton("📅 የክፍል ድልድል")])
        buttons.append([KeyboardButton("📝 ፈተና መፍጠር")])
        buttons.append([KeyboardButton("📊 ውጤት ማስገባት")])

    buttons.append([KeyboardButton("📋 የኔ ሰሌዳ")])
    buttons.append([KeyboardButton("📈 ሪፖርቶች")])
    buttons.append([KeyboardButton("👤 የኔ መረጃ")])

    if role == "አስተዳደር":
        buttons.append([KeyboardButton("⚙️ አስተዳደር ፓነል")])

    buttons.append([KeyboardButton("ℹ️ ስለ ትምህርት ቤቱ")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ====================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user(user.id)

    if not db_user:
        kb = [[KeyboardButton("📝 እንደ ሰራተኛ መመዝገብ")]]
        await update.message.reply_text(
            f"ሰላም {user.first_name}!\n\n"
            f"🏫 **{SCHOOL_NAME}**\n"
            f"የትምህርት ቤት አስተዳደር ቦት\n\n"
            f"በ**{DEVELOPER}** የተሰራ\n"
            f"📞 {PHONE}\n"
            f"📧 {EMAIL}\n\n"
            "እባክዎ መጀመሪያ እንደ ሰራተኛ ይመዝገቡ።",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return

    if db_user["approved"] != 1:
        await update.message.reply_text(
            "⏳ መመዝገቢያዎ በአስተዳዳሪ እስካልጸደቀ ድረስ መጠቀም አይችሉም።\n"
            "እባክዎ ይጠብቁ።"
        )
        return

    await update.message.reply_text(
        f"ሰላም **{db_user['full_name']}**!\n"
        f"ሚናዎ፡ **{db_user['role']}**\n\n"
        "እባክዎ የሚፈልጉትን ይምረጡ፦",
        reply_markup=main_menu_keyboard(db_user["role"]),
        parse_mode="Markdown"
    )

# ====================== STAFF REGISTRATION ======================
async def staff_reg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ሙሉ ስምዎን ይጻፉ፦", reply_markup=ReplyKeyboardRemove())
    return "STAFF_NAME"

async def staff_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text.strip()
    kb = [[KeyboardButton(d)] for d in DEPARTMENTS]
    await update.message.reply_text(
        "የስራ ክፍልዎን ይምረጡ፦",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return "STAFF_DEPT"

async def staff_dept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["department"] = update.message.text
    await update.message.reply_text("ስልክ ቁጥርዎን ያስገቡ (09xxxxxxxx)፦", reply_markup=ReplyKeyboardRemove())
    return "STAFF_PHONE"

async def staff_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user = update.effective_user
    full_name = context.user_data["full_name"]
    dept = context.user_data["department"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]

    # የመጀመሪያው ሰው አስተዳዳሪ ይሆናል
    role = "አስተዳደር" if count == 0 else dept
    approved = 1 if count == 0 else 0

    c.execute('''INSERT OR REPLACE INTO users 
        (user_id, full_name, role, department, phone, approved, registered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (user.id, full_name, role, dept, phone, approved, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    if approved:
        await update.message.reply_text(
            f"✅ እንኳን ደህና መጡ **አስተዳዳሪ**!\n"
            f"ሙሉ መብት ተሰጥቶዎታል።\n\n"
            f"/start ይጫኑ",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "✅ መመዝገቢያዎ ተቀብሏል።\n"
            "አስተዳዳሪው እስኪያጸድቅዎ ድረስ ይጠብቁ።\n\n"
            "ማጽደቂያ እንደደረሰ /start ይጫኑ።"
        )
    return ConversationHandler.END

# ====================== STUDENT REGISTRATION ======================
async def student_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር", "ሪጅስትራር", "አካዳሚክ ዳይሬክተር"]):
        await update.message.reply_text("❌ ይህን ተግባር ለማከናወን መብት የለዎትም።")
        return ConversationHandler.END
    await update.message.reply_text("የተማሪውን ሙሉ ስም ያስገቡ፦", reply_markup=ReplyKeyboardRemove())
    return "STU_NAME"

async def stu_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stu_name"] = update.message.text.strip()
    kb = [[KeyboardButton("ወንድ"), KeyboardButton("ሴት")]]
    await update.message.reply_text("ጾታ፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "STU_GENDER"

async def stu_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stu_gender"] = update.message.text
    kb = [[KeyboardButton(g)] for g in GRADES]
    await update.message.reply_text("ክፍል፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "STU_GRADE"

async def stu_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stu_grade"] = update.message.text
    kb = [[KeyboardButton(s)] for s in SECTIONS]
    await update.message.reply_text("ሴክሽን፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "STU_SECTION"

async def stu_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stu_section"] = update.message.text
    await update.message.reply_text("የወላጅ / አሳዳጊ ስልክ ቁጥር፦", reply_markup=ReplyKeyboardRemove())
    return "STU_PHONE"

async def stu_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parent_phone = update.message.text.strip()
    user = update.effective_user
    name = context.user_data["stu_name"]
    gender = context.user_data["stu_gender"]
    grade = context.user_data["stu_grade"]
    section = context.user_data["stu_section"]

    student_id = f"{grade[0]}{section}{datetime.now().strftime('%y%m%d%H%M%S')[-5:]}"

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO students 
        (student_id, full_name, gender, grade, section, parent_phone, registered_by, registered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (student_id, name, gender, grade, section, parent_phone, user.id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    role = get_user(user.id)["role"]
    await update.message.reply_text(
        f"✅ **ተማሪ ተመዝግቧል!**\n\n"
        f"🆔 ID: `{student_id}`\n"
        f"👤 ስም: {name}\n"
        f"📚 ክፍል: {grade} {section}\n"
        f"📞 ወላጅ: {parent_phone}",
        reply_markup=main_menu_keyboard(role),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================== TEACHER REGISTRATION ======================
async def teacher_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር", "ሪጅስትራር", "አካዳሚክ ዳይሬክተር"]):
        await update.message.reply_text("❌ መብት የለዎትም።")
        return ConversationHandler.END
    await update.message.reply_text("የመምህሩን ሙሉ ስም ያስገቡ፦", reply_markup=ReplyKeyboardRemove())
    return "TCH_NAME"

async def tch_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tch_name"] = update.message.text.strip()
    kb = [[KeyboardButton("ወንድ"), KeyboardButton("ሴት")]]
    await update.message.reply_text("ጾታ፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "TCH_GENDER"

async def tch_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tch_gender"] = update.message.text
    await update.message.reply_text("የሚያስተምረውን ትምህርት (Subject) ያስገቡ፦", reply_markup=ReplyKeyboardRemove())
    return "TCH_SUBJECT"

async def tch_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tch_subject"] = update.message.text.strip()
    kb = [[KeyboardButton(d)] for d in DEPARTMENTS]
    await update.message.reply_text("ዲፓርትመንት፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "TCH_DEPT"

async def tch_dept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tch_dept"] = update.message.text
    await update.message.reply_text("ስልክ ቁጥር፦", reply_markup=ReplyKeyboardRemove())
    return "TCH_PHONE"

async def tch_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user = update.effective_user
    name = context.user_data["tch_name"]
    gender = context.user_data["tch_gender"]
    subject = context.user_data["tch_subject"]
    dept = context.user_data["tch_dept"]

    teacher_id = f"T{datetime.now().strftime('%y%m%d%H%M%S')[-6:]}"

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO teachers 
        (teacher_id, full_name, gender, subject, phone, department, registered_by, registered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (teacher_id, name, gender, subject, phone, dept, user.id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    role = get_user(user.id)["role"]
    await update.message.reply_text(
        f"✅ **መምህር ተመዝግቧል!**\n\n"
        f"🆔 ID: `{teacher_id}`\n"
        f"👤 ስም: {name}\n"
        f"📚 ትምህርት: {subject}\n"
        f"🏢 ዲፓርትመንት: {dept}\n"
        f"📞 {phone}",
        reply_markup=main_menu_keyboard(role),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================== CLASS ASSIGNMENT ======================
async def assign_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር", "አካዳሚክ ዳይሬክተር", "ዲፓርትመንት ሀላፊ"]):
        await update.message.reply_text("❌ መብት የለዎትም።")
        return ConversationHandler.END

    conn = get_db()
    df = pd.read_sql_query("SELECT teacher_id, full_name, subject FROM teachers ORDER BY full_name", conn)
    conn.close()

    if df.empty:
        await update.message.reply_text("መጀመሪያ መምህራንን ይመዝገቡ።")
        return ConversationHandler.END

    context.user_data["teachers_df"] = df
    kb = [[KeyboardButton(f"{row['teacher_id']} - {row['full_name']} ({row['subject']})")] for _, row in df.iterrows()]
    await update.message.reply_text(
        "መምህር ይምረጡ፦",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return "ASG_TEACHER"

async def asg_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    teacher_id = text.split(" - ")[0]
    context.user_data["asg_teacher_id"] = teacher_id
    context.user_data["asg_teacher_name"] = text.split(" - ")[1].split(" (")[0]

    kb = [[KeyboardButton(g)] for g in GRADES]
    await update.message.reply_text("ክፍል፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "ASG_GRADE"

async def asg_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["asg_grade"] = update.message.text
    kb = [[KeyboardButton(s)] for s in SECTIONS]
    await update.message.reply_text("ሴክሽን፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "ASG_SECTION"

async def asg_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["asg_section"] = update.message.text
    await update.message.reply_text("ትምህርቱን ያስገቡ (Subject)፦", reply_markup=ReplyKeyboardRemove())
    return "ASG_SUBJECT"

async def asg_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["asg_subject"] = update.message.text.strip()
    kb = [[KeyboardButton(d)] for d in DAYS]
    await update.message.reply_text("ቀን፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "ASG_DAY"

async def asg_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["asg_day"] = update.message.text
    kb = [[KeyboardButton(p)] for p in PERIODS]
    await update.message.reply_text("ፔሪየድ፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "ASG_PERIOD"

async def asg_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    period = update.message.text
    user = update.effective_user
    data = context.user_data

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO class_assignments 
        (teacher_id, teacher_name, grade, section, subject, day, period, assigned_by, assigned_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data["asg_teacher_id"], data["asg_teacher_name"], data["asg_grade"], data["asg_section"],
         data["asg_subject"], data["asg_day"], period, user.id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    # ማሳወቂያ ለመምህር (telegram_id ካለ)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM teachers WHERE teacher_id = ?", (data["asg_teacher_id"],))
    row = c.fetchone()
    conn.close()

    notify_text = (
        f"📢 **አዲስ የክፍል ድልድል!**\n\n"
        f"መምህር: {data['asg_teacher_name']}\n"
        f"ክፍል: {data['asg_grade']} {data['asg_section']}\n"
        f"ትምህርት: {data['asg_subject']}\n"
        f"ቀን: {data['asg_day']}\n"
        f"ፔሪየድ: {period}"
    )

    if row and row[0]:
        try:
            await context.bot.send_message(chat_id=row[0], text=notify_text, parse_mode="Markdown")
        except:
            pass

    role = get_user(user.id)["role"]
    await update.message.reply_text(
        f"✅ **ድልድል ተሳክቷል!**\n\n{notify_text}",
        reply_markup=main_menu_keyboard(role),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================== EXAM CREATION ======================
async def exam_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር", "አካዳሚክ ዳይሬክተር", "ዲፓርትመንት ሀላፊ"]):
        await update.message.reply_text("❌ መብት የለዎትም።")
        return ConversationHandler.END
    await update.message.reply_text("የፈተናውን ስም ያስገቡ (ለምሳሌ፡ 1ኛ ሴሚስተር ሚድተርም)፦", reply_markup=ReplyKeyboardRemove())
    return "EXAM_NAME"

async def exam_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam_name"] = update.message.text.strip()
    kb = [[KeyboardButton(g)] for g in GRADES]
    await update.message.reply_text("ለየትኛው ክፍል፦", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return "EXAM_GRADE"

async def exam_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam_grade"] = update.message.text
    await update.message.reply_text("ትምህርቱን ያስገቡ፦", reply_markup=ReplyKeyboardRemove())
    return "EXAM_SUBJECT"

async def exam_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam_subject"] = update.message.text.strip()
    await update.message.reply_text("የፈተና ቀን (YYYY-MM-DD)፦")
    return "EXAM_DATE"

async def exam_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exam_date = update.message.text.strip()
    user = update.effective_user
    data = context.user_data

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO exams (exam_name, grade, subject, exam_date, created_by, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (data["exam_name"], data["exam_grade"], data["exam_subject"], exam_date, user.id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    role = get_user(user.id)["role"]
    await update.message.reply_text(
        f"✅ **ፈተና ተፈጥሯል!**\n\n"
        f"📝 {data['exam_name']}\n"
        f"📚 {data['exam_grade']} - {data['exam_subject']}\n"
        f"📅 {exam_date}",
        reply_markup=main_menu_keyboard(role),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================== RESULT ENTRY ======================
async def result_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር", "አካዳሚክ ዳይሬክተር", "ዲፓርትመንት ሀላፊ"]):
        await update.message.reply_text("❌ መብት የለዎትም።")
        return ConversationHandler.END

    conn = get_db()
    df = pd.read_sql_query("SELECT id, exam_name, grade, subject FROM exams ORDER BY id DESC LIMIT 20", conn)
    conn.close()

    if df.empty:
        await update.message.reply_text("መጀመሪያ ፈተና ይፍጠሩ።")
        return ConversationHandler.END

    kb = [[KeyboardButton(f"{row['id']} | {row['exam_name']} | {row['grade']} | {row['subject']}")] for _, row in df.iterrows()]
    await update.message.reply_text(
        "ፈተና ይምረጡ፦",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return "RES_EXAM"

async def res_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    exam_id = int(text.split(" | ")[0])
    context.user_data["res_exam_id"] = exam_id
    context.user_data["res_exam_info"] = text

    await update.message.reply_text(
        "የተማሪውን **Student ID** ያስገቡ፦\n(ለምሳሌ 9A12345)",
        reply_markup=ReplyKeyboardRemove()
    )
    return "RES_STUDENT"

async def res_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    student_id = update.message.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT full_name, grade, section FROM students WHERE student_id = ?", (student_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("❌ ተማሪ አልተገኘም። እንደገና Student ID ያስገቡ፦")
        return "RES_STUDENT"

    context.user_data["res_student_id"] = student_id
    context.user_data["res_student_name"] = row[0]
    await update.message.reply_text(
        f"ተማሪ: **{row[0]}** ({row[1]} {row[2]})\n\n"
        f"ውጤቱን ያስገቡ (0-100)፦",
        parse_mode="Markdown"
    )
    return "RES_SCORE"

async def res_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        score = float(update.message.text.strip())
        if not (0 <= score <= 100):
            raise ValueError
    except:
        await update.message.reply_text("እባክዎ ከ0 እስከ 100 ያለ ቁጥር ያስገቡ፦")
        return "RES_SCORE"

    user = update.effective_user
    data = context.user_data

    conn = get_db()
    c = conn.cursor()
    # subject ከ exam እንውሰድ
    c.execute("SELECT subject FROM exams WHERE id = ?", (data["res_exam_id"],))
    subject = c.fetchone()[0]

    c.execute('''INSERT OR REPLACE INTO results 
        (student_id, exam_id, subject, score, recorded_by, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (data["res_student_id"], data["res_exam_id"], subject, score, user.id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    role = get_user(user.id)["role"]
    await update.message.reply_text(
        f"✅ **ውጤት ተመዝግቧል!**\n\n"
        f"ተማሪ: {data['res_student_name']}\n"
        f"ID: {data['res_student_id']}\n"
        f"ውጤት: **{score}**",
        reply_markup=main_menu_keyboard(role),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================== MY SCHEDULE ======================
async def my_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_user(user.id)

    conn = get_db()
    # መምህር ከሆነ በስም ይፈልግ
    df = pd.read_sql_query(
        "SELECT grade, section, subject, day, period FROM class_assignments WHERE teacher_name LIKE ? ORDER BY day, period",
        conn, params=(f"%{db_user['full_name']}%",)
    )
    conn.close()

    if df.empty:
        await update.message.reply_text("ለእርስዎ የተመደበ ክፍል የለም።")
        return

    text = f"📋 **የእርስዎ የክፍል ሰሌዳ**\n\n"
    for _, row in df.iterrows():
        text += f"• {row['day']} {row['period']} → {row['grade']}{row['section']} | {row['subject']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ====================== ADMIN PANEL ======================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_role(update.effective_user.id, ["አስተዳደር"]):
        await update.message.reply_text("❌ የአስተዳዳሪ መብት ብቻ።")
        return

    conn = get_db()
    df = pd.read_sql_query(
        "SELECT user_id, full_name, department, phone FROM users WHERE approved = 0",
        conn
    )
    conn.close()

    if df.empty:
        await update.message.reply_text("✅ ምንም የሚጠብቅ መመዝገቢያ የለም።")
        return

    text = "⏳ **የሚጠብቁ መመዝገቢያዎች**\n\n"
    keyboard = []
    for _, row in df.iterrows():
        text += f"• {row['full_name']} ({row['department']}) - {row['phone']}\n"
        keyboard.append([
            InlineKeyboardButton(f"✅ {row['full_name']}", callback_data=f"approve_{row['user_id']}"),
            InlineKeyboardButton("❌", callback_data=f"reject_{row['user_id']}")
        ])

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        uid = int(data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET approved = 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        try:
            await context.bot.send_message(uid, "✅ መመዝገቢያዎ ጸድቋል! አሁን /start ይጫኑ።")
        except:
            pass
        await query.edit_message_text("✅ ተጽድቋል።")

    elif data.startswith("reject_"):
        uid = int(data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ ተሰርዟል።")

# ====================== REPORTS ======================
async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("👨‍🎓 ተማሪዎች በክፍል", callback_data="rep_stu")],
        [InlineKeyboardButton("👩‍🏫 መምህራን", callback_data="rep_tch")],
        [InlineKeyboardButton("📅 የክፍል ድልድሎች", callback_data="rep_asg")],
        [InlineKeyboardButton("📊 ውጤቶች ማጠቃለያ", callback_data="rep_res")],
        [InlineKeyboardButton("📈 ግራፍ", callback_data="rep_graph")],
        [InlineKeyboardButton("📄 PDF ሪፖርት", callback_data="rep_pdf")],
    ]
    await update.message.reply_text("ሪፖርት ይምረጡ፦", reply_markup=InlineKeyboardMarkup(kb))

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db()

    if query.data == "rep_stu":
        df = pd.read_sql_query(
            "SELECT grade, section, COUNT(*) as ብዛት FROM students GROUP BY grade, section ORDER BY grade, section", conn)
        text = "👨‍🎓 **ተማሪዎች በክፍል**\n\n"
        if df.empty:
            text += "ምንም ተማሪ የለም።"
        else:
            for _, r in df.iterrows():
                text += f"{r['grade']} {r['section']}: **{r['ብዛት']}**\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "rep_tch":
        df = pd.read_sql_query("SELECT full_name, subject, department, phone FROM teachers", conn)
        text = "👩‍🏫 **መምህራን**\n\n"
        for _, r in df.iterrows():
            text += f"• {r['full_name']} — {r['subject']} ({r['department']})\n"
        await query.edit_message_text(text or "መምህር የለም።")

    elif query.data == "rep_asg":
        df = pd.read_sql_query(
            "SELECT teacher_name, grade, section, subject, day, period FROM class_assignments ORDER BY day, period LIMIT 30", conn)
        text = "📅 **የክፍል ድልድሎች**\n\n"
        for _, r in df.iterrows():
            text += f"• {r['day']} {r['period']}: {r['teacher_name']} → {r['grade']}{r['section']} ({r['subject']})\n"
        await query.edit_message_text(text or "ድልድል የለም።")

    elif query.data == "rep_res":
        df = pd.read_sql_query('''
            SELECT e.exam_name, e.grade, e.subject, ROUND(AVG(r.score),1) as አማካይ, COUNT(*) as ብዛት
            FROM results r JOIN exams e ON r.exam_id = e.id
            GROUP BY e.id ORDER BY e.id DESC LIMIT 10
        ''', conn)
        text = "📊 **ውጤቶች ማጠቃለያ**\n\n"
        for _, r in df.iterrows():
            text += f"• {r['exam_name']} ({r['grade']} {r['subject']}): አማካይ **{r['አማካይ']}** ({r['ብዛት']} ተማሪ)\n"
        await query.edit_message_text(text or "ውጤት የለም።", parse_mode="Markdown")

    elif query.data == "rep_graph":
        df = pd.read_sql_query("SELECT grade, COUNT(*) as count FROM students GROUP BY grade ORDER BY grade", conn)
        if df.empty:
            await query.edit_message_text("ምንም ተማሪ የለም።")
            return
        plt.figure(figsize=(8, 5))
        plt.bar(df['grade'], df['count'], color='#1B4F72')
        plt.title(f"{SCHOOL_NAME}\nየተማሪዎች ብዛት በክፍል")
        plt.ylabel("ብዛት")
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        await query.message.reply_photo(photo=buf, caption="📈 የተማሪዎች ስታቲስቲክስ")

    elif query.data == "rep_pdf":
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"<b>{SCHOOL_NAME}</b>", styles['Title']))
        elements.append(Paragraph("አጠቃላይ የትምህርት ቤት ሪፖርት", styles['Heading2']))
        elements.append(Paragraph(f"ቀን: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        elements.append(Paragraph(f"በ{DEVELOPER} የተሰራ | {PHONE}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # ተማሪዎች
        df = pd.read_sql_query("SELECT grade, section, COUNT(*) as count FROM students GROUP BY grade, section", conn)
        data = [["ክፍል", "ሴክሽን", "ብዛት"]] + df.values.tolist()
        t = Table(data, colWidths=[100, 80, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B4F72')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#D4E6F1')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(Paragraph("<b>ተማሪዎች በክፍል</b>", styles['Heading3']))
        elements.append(t)
        elements.append(Spacer(1, 15))

        # መምህራን ብዛት
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM teachers")
        tch_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM students")
        stu_count = c.fetchone()[0]
        elements.append(Paragraph(f"<b>አጠቃላይ:</b> {stu_count} ተማሪዎች | {tch_count} መምህራን", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)

        await query.message.reply_document(
            document=InputFile(buffer, filename=f"Report_{datetime.now().strftime('%Y%m%d')}.pdf"),
            caption="📄 አጠቃላይ የትምህርት ቤት ሪፖርት"
        )

    conn.close()

# ====================== INFO & PROFILE ======================
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🏫 **{SCHOOL_NAME}**\n\n"
        f"የትምህርት ቤት አስተዳደር ቦት\n\n"
        f"👨‍💻 በ**{DEVELOPER}** የተሰራ\n"
        f"📞 {PHONE}\n"
        f"📧 {EMAIL}\n\n"
        f"© 2026",
        parse_mode="Markdown"
    )

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("መረጃ አልተገኘም።")
        return
    await update.message.reply_text(
        f"👤 **የእርስዎ መረጃ**\n\n"
        f"ስም: {user['full_name']}\n"
        f"ሚና: {user['role']}\n"
        f"ክፍል: {user['department']}\n"
        f"ስልክ: {user['phone']}",
        parse_mode="Markdown"
    )

# ====================== MAIN ======================
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ እባክዎ .env ፋይል ውስጥ BOT_TOKEN ያስገቡ!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Staff registration
    staff_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 እንደ ሰራተኛ መመዝገብ$"), staff_reg_start)],
        states={
            "STAFF_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, staff_name)],
            "STAFF_DEPT": [MessageHandler(filters.TEXT & ~filters.COMMAND, staff_dept)],
            "STAFF_PHONE": [MessageHandler(filters.TEXT & ~filters.COMMAND, staff_phone)],

        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    # Student
    stu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👨‍🎓 ተማሪ መመዝገቢያ$"), student_start)],
    states={
            "STU_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_name)],
            "STU_GENDER": [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_gender)],
            "STU_GRADE": [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_grade)],
            "STU_SECTION": [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_section)],
            "STU_PHONE": [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_phone)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

# Teacher
tch_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👨‍🏫 መምህር መመዝገብ$"), teacher_start)],
        states={
            "TCH_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, tch_name)],
            "TCH_GENDER": [MessageHandler(filters.TEXT & ~filters.COMMAND, tch_gender)],
            "TCH_SUBJECT": [MessageHandler(filters.TEXT & ~filters.COMMAND, tch_subject)],

        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    # Class assignment
    asg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📅 የክፍል ድልድል$"), assign_start)],
        states={
            "ASG_TEACHER": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_teacher)],
            "ASG_GRADE": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_grade)],
            "ASG_SECTION": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_section)],
            "ASG_SUBJECT": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_subject)],
            "ASG_DAY": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_day)],
            "ASG_PERIOD": [MessageHandler(filters.TEXT & \~filters.COMMAND, asg_period)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    # Exam
    exam_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 ፈተና መፍጠር$"), exam_start)],
        states={
            "EXAM_NAME": [MessageHandler(filters.TEXT & \~filters.COMMAND, exam_name)],
            "EXAM_GRADE": [MessageHandler(filters.TEXT & \~filters.COMMAND, exam_grade)],
            "EXAM_SUBJECT": [MessageHandler(filters.TEXT & \~filters.COMMAND, exam_subject)],
            "EXAM_DATE": [MessageHandler(filters.TEXT & \~filters.COMMAND, exam_date)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    # Result
    res_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📊 ውጤት ማስገባት$"), result_start)],
        states={
            "RES_EXAM": [MessageHandler(filters.TEXT & \~filters.COMMAND, res_exam)],
            "RES_STUDENT": [MessageHandler(filters.TEXT & \~filters.COMMAND, res_student)],
            "RES_SCORE": [MessageHandler(filters.TEXT & \~filters.COMMAND, res_score)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(staff_conv)
    app.add_handler(stu_conv)
    app.add_handler(tch_conv)
    app.add_handler(asg_conv)
    app.add_handler(exam_conv)
    app.add_handler(res_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 የኔ ሰሌዳ$"), my_schedule))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ አስተዳደር ፓነል$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📈 ሪፖርቶች$"), reports_menu))
    app.add_handler(MessageHandler(filters.Regex("^👤 የኔ መረጃ$"), my_info))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ ስለ ትምህርት ቤቱ$"), about))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(report_callback, pattern="^rep_"))

    print(f"✅ {SCHOOL_NAME} ቦት በተሳካ ሁኔታ ተጀምሯል...")
    print(f"📞 {PHONE} | በ{DEVELOPER} የተሰራ")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
