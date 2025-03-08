import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# ---- ユーザー認証 ----
st.sidebar.title("ログイン")
username = st.sidebar.text_input("ユーザー名を入力してください:", value="guest")
if st.sidebar.button("ログイン"):
    st.session_state["username"] = username
    st.sidebar.success(f"ログインしました: {username}")

# ---- ユーザーごとのデータベースを設定 ----
db_name = f"user_{st.session_state.get('username', 'guest')}.db"
conn = sqlite3.connect(db_name, check_same_thread=False)
c = conn.cursor()

# ---- データベースの初期化 ----
def init_db():
    c.execute('''
        CREATE TABLE IF NOT EXISTS problem_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER,
            problem_number TEXT,
            next_review_date TEXT,
            correct_streak INTEGER DEFAULT 0,
            FOREIGN KEY (set_id) REFERENCES problem_sets(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER,
            result INTEGER, -- 1: 正解, 0: 不正解
            date TEXT,
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    ''')
    conn.commit()

init_db()

## ---- 復習間隔を計算する関数（修正済み）----
def calculate_next_review(problem_id, is_correct):
    today = datetime.now().date()

    # `problem_id` が None の場合、何もしない（初回の登録時）
    if problem_id is None:
        return today + timedelta(days=2)  # 初回登録時のデフォルト復習日は 2 日後

    # 最新の復習結果を取得
    c.execute('''
        SELECT result FROM results WHERE problem_id = ? ORDER BY date DESC LIMIT 1
    ''', (problem_id,))
    last_result = c.fetchone()

    # `correct_streak` を取得（None の場合は 0 に設定）
    c.execute('SELECT correct_streak FROM problems WHERE id = ?', (problem_id,))
    correct_streak_data = c.fetchone()
    correct_streak = correct_streak_data[0] if correct_streak_data else 0

    if is_correct:
        if last_result and last_result[0] == 0:  # 不正解の次の正解 → 1日後
            next_review_interval = 1
            correct_streak = 1  # 連続正解をリセット
        else:
            correct_streak += 1
            next_review_interval = {1: 2, 2: 3, 3: 7, 4: 21}.get(correct_streak, 21)
    else:
        next_review_interval = 1  # 不正解 → 1日後
        correct_streak = 0  # 連続正解リセット

    next_review = today + timedelta(days=next_review_interval)

    # `problems` テーブルを更新
    c.execute('''
        UPDATE problems 
        SET next_review_date = ?, correct_streak = ?
        WHERE id = ?
    ''', (next_review, correct_streak, problem_id))

    conn.commit()
    return next_review

# **1. 問題集の登録**
st.subheader("問題集の登録")
new_set = st.text_input("問題集のタイトルを入力:")
if st.button("問題集を登録"):
    if new_set:
        c.execute("INSERT INTO problem_sets (title) VALUES (?)", (new_set,))
        conn.commit()
        st.success(f"問題集 '{new_set}' を登録しました！")

# ---- 問題登録（修正済み）----
st.subheader("📝 問題の登録")

c.execute("SELECT * FROM problem_sets")
sets = c.fetchall()
set_options = {title: set_id for set_id, title in sets}

selected_set = st.selectbox("問題集を選択:", list(set_options.keys()), key="set_select")
new_problem = st.text_input("問題番号を入力:")

# **キーを動的に変更し、重複エラーを防ぐ**
initial_result_key = f"initial_result_{new_problem}"
initial_result = st.radio("初回の挑戦結果:", ["正解", "不正解"], key=initial_result_key)

if st.button("問題を登録（初回挑戦含む）"):
    if new_problem:
        set_id = set_options[selected_set]
        today = datetime.now().date()
        is_correct = initial_result == "正解"

        # 問題を登録
        c.execute('''
            INSERT INTO problems (set_id, problem_number, next_review_date, correct_streak)
            VALUES (?, ?, ?, ?)
        ''', (set_id, new_problem, today + timedelta(days=1), int(is_correct)))
        conn.commit()

        # `problem_id` を取得
        c.execute("SELECT id FROM problems WHERE problem_number = ? AND set_id = ?", (new_problem, set_id))
        problem_data = c.fetchone()

        if problem_data:
            problem_id = problem_data[0]

            # 初回挑戦の結果を記録
            c.execute("INSERT INTO results (problem_id, result, date) VALUES (?, ?, ?)", 
                      (problem_id, int(is_correct), today))
            conn.commit()

            # 初回の復習日を計算し更新
            next_review = calculate_next_review(problem_id, is_correct)
            c.execute('''
                UPDATE problems 
                SET next_review_date = ?
                WHERE id = ?
            ''', (next_review, problem_id))
            conn.commit()

            st.success(f"問題 '{new_problem}' を登録し、初回挑戦（{initial_result}）を記録しました！ 次回の復習日は {next_review} です。")
        else:
            st.error("問題の登録に失敗しました。")

# ---- 本日の復習リスト ----
st.subheader("今日の復習")
today = datetime.now().date()
c.execute('''
    SELECT problems.id, problem_sets.title, problems.problem_number, problems.correct_streak 
    FROM problems 
    JOIN problem_sets ON problems.set_id = problem_sets.id
    WHERE next_review_date = ?
''', (today,))
reviews_today = c.fetchall()

if reviews_today:
    for problem_id, set_title, problem_number, correct_streak in reviews_today:
        st.markdown(f"### {set_title} - 問題番号: {problem_number}")
        st.markdown(f"連続正解数: {correct_streak}")

        result = st.radio(f"結果を選択:", ["正解", "不正解"], key=f"radio_{problem_id}")
        if st.button(f"結果を保存: {problem_number}", key=f"save_{problem_id}"):
            record_review_result(problem_id, result == "正解")
            st.rerun()
else:
    st.info("今日の復習はありません。")

conn.close()
