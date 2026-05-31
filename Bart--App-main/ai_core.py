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
# 🧠 NORMALIZE TEXT
# =========================================================
def normalize(text):

    if not text:
        return ""

    text = str(text).lower().strip()

    text = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# 🧠 SIMILARITY
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

    # yyyy-mm-dd
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)

    if match:
        return match.group()

    # 06 may
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
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
            return datetime.date(
                year,
                month,
                day
            ).strftime("%Y-%m-%d")

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

        score = similarity(text, branch)

        if normalize(branch) in text:
            return branch

        if score > best_score:
            best_score = score
            best_branch = branch

    if best_score >= 0.45:
        return best_branch

    return None


# =========================================================
# 📦 FIND ITEM
# =========================================================
def find_item(user_input, item_list):

    text = normalize(user_input)

    best_item = None
    best_score = 0

    for item in item_list:

        item_norm = normalize(item)

        # direct contains
        if text in item_norm:
            return item

        score = similarity(text, item)

        # word boost
        for word in text.split():

            if len(word) < 2:
                continue

            if word in item_norm:
                score += 0.15

        if score > best_score:
            best_score = score
            best_item = item

    if best_score >= 0.35:
        return best_item

    return None


# =========================================================
# 📊 EXTRACT STOCK
# =========================================================
def extract_stock_data(
    all_data,
    item_name,
    target_date,
    target_branch=None
):

    results = []

    for branch_name, raw in all_data:

        if target_branch:

            if normalize(branch_name) != normalize(target_branch):
                continue

        if not raw or len(raw) < 2:
            continue

        headers = raw[0]

        if target_date not in headers:
            continue

        date_index = headers.index(target_date)

        for row in raw:

            if not row:
                continue

            if len(row) == 0:
                continue

            row_item = str(row[0]).strip()

            if not row_item:
                continue

            score = similarity(item_name, row_item)

            if normalize(item_name) not in normalize(row_item):

                if score < 0.40:
                    continue

            qty = 0

            try:

                if len(row) > date_index:
                    qty = float(row[date_index] or 0)

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
# 🤖 MAIN AI FUNCTION
# =========================================================
def run_ai(user_input, context):

    try:

        all_data = context.get("cache_data", [])
        branch_list = context.get("branch_list", [])
        master_items = context.get("master_items", [])

        if not all_data:
            return "⚠️ Stock data not loaded."

        # ---------------- DATE ----------------
        target_date = parse_date(user_input)

        # ---------------- BRANCH ----------------
        matched_branch = find_branch(
            user_input,
            branch_list
        )

        # ---------------- ITEM ----------------
        matched_item = find_item(
            user_input,
            master_items
        )

        if not matched_item:
            return (
                "❌ Could not identify item.\n\n"
                "Try:\n"
                "- crunchy cake\n"
                "- lotus crumble\n"
                "- cinnamoroll cup"
            )

        # ---------------- FETCH STOCK ----------------
        stock_results = extract_stock_data(
            all_data=all_data,
            item_name=matched_item,
            target_date=target_date,
            target_branch=matched_branch
        )

        if not stock_results:

            if matched_branch:
                return (
                    f"📦 No stock found for "
                    f"{matched_item} at "
                    f"{matched_branch} on "
                    f"{target_date}"
                )

            return (
                f"📦 No stock found for "
                f"{matched_item} on "
                f"{target_date}"
            )

        # ---------------- TOTAL ----------------
        total_stock = sum(
            x["qty"] for x in stock_results
        )

        payload = {
            "query": user_input,
            "item": matched_item,
            "branch": matched_branch,
            "date": target_date,
            "total_stock": total_stock,
            "results": stock_results
        }

        # =====================================================
        # 🤖 GROQ RESPONSE
        # =====================================================
        prompt = f"""
You are BART AI.

Use ONLY this stock JSON.

{json.dumps(payload, ensure_ascii=False, indent=2)}

Rules:
- Be natural like ChatGPT
- NEVER invent stock
- If branch requested, ONLY show that branch
- Keep response concise
"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an inventory AI assistant."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            max_tokens=400
        )

        return response.choices[0].message.content.strip()

    except Exception as e:

        return f"⚠️ AI Error: {str(e)}"
