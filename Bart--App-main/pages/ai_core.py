import re
import json
import datetime
from difflib import SequenceMatcher

import streamlit as st
from groq import Groq

# =========================================================
# 🔐 GROQ CLIENT
# =========================================================
client = Groq(api_key=st.secrets["GROQ_API_KEY"])


# =========================================================
# 🧠 TEXT NORMALIZATION
# =========================================================
def normalize(text):
    if not text:
        return ""

    text = str(text).lower().strip()
    text = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# 🧠 SIMILARITY SCORE
# =========================================================
def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize(a),
        normalize(b)
    ).ratio()


# =========================================================
# 📅 DATE PARSER
# =========================================================
def parse_date(text):

    text = normalize(text)

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if "yesterday" in text:
        return yesterday.strftime("%Y-%m-%d")

    if "today" in text:
        return today.strftime("%Y-%m-%d")

    # YYYY-MM-DD
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group()

    # DAY + MONTH (e.g. 6 may)
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    match = re.search(
        r"(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        text
    )

    if match:
        day = int(match.group(1))
        month = month_map[match.group(2)]
        year = today.year

        try:
            return datetime.date(year, month, day).strftime("%Y-%m-%d")
        except:
            pass

    return today.strftime("%Y-%m-%d")


# =========================================================
# 🏢 FIND BRANCH
# =========================================================
def find_branch(user_input, branch_list):

    text = normalize(user_input)

    best_branch = None
    best_score = 0

    for branch in branch_list:

        if normalize(branch) in text:
            return branch

        score = similarity(text, branch)

        if score > best_score:
            best_score = score
            best_branch = branch

    return best_branch if best_score >= 0.45 else None


# =========================================================
# 📦 FIND ITEM
# =========================================================
def find_item(user_input, item_list):

    text = normalize(user_input)

    best_item = None
    best_score = 0

    for item in item_list:

        item_norm = normalize(item)

        if text in item_norm:
            return item

        score = similarity(text, item)

        # keyword boost
        for word in text.split():
            if len(word) > 2 and word in item_norm:
                score += 0.15

        if score > best_score:
            best_score = score
            best_item = item

    return best_item if best_score >= 0.35 else None


# =========================================================
# 📊 STOCK EXTRACTION
# =========================================================
def extract_stock_data(all_data, item_name, target_date, target_branch=None):

    results = []

    for branch_name, raw in all_data:

        if target_branch and normalize(branch_name) != normalize(target_branch):
            continue

        if not raw or len(raw) < 2:
            continue

        headers = raw[0]

        if target_date not in headers:
            continue

        date_index = headers.index(target_date)

        for row in raw:

            if not row or not row[0]:
                continue

            row_item = str(row[0]).strip()

            if similarity(item_name, row_item) < 0.40:
                continue

            try:
                qty = float(row[date_index] or 0) if len(row) > date_index else 0
            except:
                qty = 0

            results.append({
                "branch": branch_name,
                "item": row_item,
                "qty": qty,
                "date": target_date
            })

    return results


# =========================================================
# 🚨 MANAGEMENT INSIGHTS ENGINE
# =========================================================
def generate_insights(total_stock, branch_summary):

    insights = []

    if total_stock == 0:
        insights.append("🚨 OUT OF STOCK - Immediate action required")

    elif total_stock < 10:
        insights.append("⚠️ LOW STOCK - Restock recommended")

    elif total_stock > 50:
        insights.append("📦 HIGH STOCK - No urgent action needed")

    if len(branch_summary) == 1:
        insights.append("📍 Stock concentrated in single branch")

    if len(branch_summary) > 3:
        insights.append("🌍 Distributed stock across multiple branches")

    return insights


# =========================================================
# 🤖 MAIN AI FUNCTION (MANAGEMENT VERSION)
# =========================================================
def run_ai(user_input, context):

    try:

        all_data = context.get("cache_data", [])
        branch_list = context.get("branch_list", [])
        master_items = context.get("master_items", [])

        if not all_data:
            return "⚠️ Stock data not loaded."

        # ---------------- PARSE ----------------
        target_date = parse_date(user_input)
        matched_branch = find_branch(user_input, branch_list)
        matched_item = find_item(user_input, master_items)

        if not matched_item:
            return "❌ Item not found in inventory."

        # ---------------- STOCK ----------------
        stock_results = extract_stock_data(
            all_data,
            matched_item,
            target_date,
            matched_branch
        )

        total_stock = sum(x["qty"] for x in stock_results)

        branch_summary = {}
        for x in stock_results:
            branch_summary[x["branch"]] = branch_summary.get(x["branch"], 0) + x["qty"]

        insights = generate_insights(total_stock, branch_summary)

        # ---------------- FINAL DATA ----------------
        payload = {
            "query": user_input,
            "item": matched_item,
            "branch": matched_branch,
            "date": target_date,
            "total_stock": total_stock,
            "branch_summary": branch_summary,
            "insights": insights
        }

        # ---------------- GROQ PROMPT ----------------
        prompt = f"""
You are BART MANAGEMENT AI.

You are a decision-making assistant for inventory managers.

RULES:
- Use ONLY provided data
- Do NOT invent stock
- Focus on actions and decisions
- Be concise and business-friendly

DATA:
{json.dumps(payload, indent=2, ensure_ascii=False)}

FORMAT:
- Summary
- Stock Status
- Branch Breakdown
- Action Needed
"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert inventory management AI assistant."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=450
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"
