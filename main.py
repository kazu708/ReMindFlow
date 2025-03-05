import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# データベース接続
conn = sqlite3.connect('forgetting_curve.db', check_same_thread=False)
c = conn.cursor()

# 必要なテーブルを作成
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
        review_interval INTEGER DEFAULT 1,
        correct_count INTEGER DEFAULT 0,
        total_count INTEGER DEFAULT 0,
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

# 関数：復習タイミングの更新
def update_review_date(problem_id, is_correct):
    c.execute('SELECT review_interval, correct_count, total_count FROM problems WHERE id = ?', (problem_id,))
    data = c.fetchone()
    
    if data:
        interval, correct, total = data
        total += 1

        if is_correct:
            correct += 1
            interval = min(interval * 2, 30)  # 最大30日まで
        else:
            interval = 1  # 間隔リセット

        next_review = datetime.now().date() + timedelta(days=interval)

        # 更新
        c.execute('''
            UPDATE problems 
            SET next_review_date = ?, review_interval = ?, correct_count = ?, total_count = ?
            WHERE id = ?
        ''', (next_review, interval, correct, total, problem_id))
        conn.commit()

# 関数：正解率の推移グラフ
def plot_correct_rate(problem_id):
    c.execute('''
        SELECT date, result FROM results WHERE problem_id = ? ORDER BY date ASC
    ''', (problem_id,))
    data = c.fetchall()

    if not data:
        return

    dates, results = zip(*data)
    correct_count = [sum(results[:i+1]) / (i+1) * 100 for i in range(len(results))]

    plt.figure(figsize=(8, 4))
    plt.plot(dates, correct_count, marker='o', linestyle='-', color='blue')
    plt.title("正解率の推移")
    plt.xlabel("日付")
    plt.ylabel("正解率 (%)")
    plt.xticks(rotation=45)
    plt.grid(True)
    st.pyplot(plt)

# 関数：復習スケジュールの棒グラフ
def plot_review_schedule():
    c.execute('SELECT problem_number, next_review_date FROM problems ORDER BY next_review_date ASC')
    data = c.fetchall()

    if not data:
        return

    problems, dates = zip(*data)
    dates = [datetime.strptime(d, "%Y-%m-%d") for d in dates]

    plt.figure(figsize=(8, 4))
    plt.bar(problems, dates, color='orange')
    plt.title("schedule")
    plt.xlabel("No")
    plt.ylabel("Next")
    plt.xticks(rotation=45)
    plt.grid(True)
    st.pyplot(plt)

# ---- UI ----
st.title("エビングハウスの忘却曲線 - 復習アプリ")

# **1. 問題集の登録**
st.subheader("問題集の登録")
new_set = st.text_input("問題集のタイトルを入力:")
if st.button("問題集を登録"):
    if new_set:
        c.execute("INSERT INTO problem_sets (title) VALUES (?)", (new_set,))
        conn.commit()
        st.success(f"問題集 '{new_set}' を登録しました！")

# **2. 問題番号の登録**
st.subheader("問題番号の登録")
c.execute("SELECT * FROM problem_sets")
sets = c.fetchall()
set_options = {title: set_id for set_id, title in sets}

selected_set = st.selectbox("問題集を選択:", list(set_options.keys()))

new_problem = st.text_input("問題番号を入力:")
if st.button("問題番号を登録"):
    if new_problem:
        set_id = set_options[selected_set]
        next_review = datetime.now().date() + timedelta(days=1)
        c.execute("INSERT INTO problems (set_id, problem_number, next_review_date) VALUES (?, ?, ?)",
                  (set_id, new_problem, next_review))
        conn.commit()
        st.success(f"問題番号 '{new_problem}' を登録しました！")

# **3. 今日の復習**
st.subheader("今日の復習")
today = datetime.now().date()
c.execute('''
    SELECT problems.id, problem_sets.title, problems.problem_number, problems.correct_count, problems.total_count 
    FROM problems 
    JOIN problem_sets ON problems.set_id = problem_sets.id
    WHERE next_review_date = ?
''', (today,))
reviews_today = c.fetchall()

if reviews_today:
    for problem_id, set_title, problem_number, correct, total in reviews_today:
        st.markdown(f"### {set_title} - 問題番号: {problem_number}")
        st.markdown(f"正解率: {correct}/{total} 回")

        # 正解・不正解の選択
        result = st.radio(f"結果を選択:", ["正解", "不正解"], key=f"radio_{problem_id}")

        # 結果保存ボタン
        if st.button(f"結果を保存: {problem_number}", key=f"save_{problem_id}"):
            is_correct = result == "正解"
            update_review_date(problem_id, is_correct)
            st.success(f"問題 {problem_number} の結果を保存しました！")
            st.rerun()

else:
    st.info("今日の復習はありません。")

# **4. グラフ表示**
st.subheader("復習スケジュール")
plot_review_schedule()

st.subheader("正解率の推移")
problem_id_input = st.number_input("問題IDを入力:", min_value=1, step=1)
if st.button("正解率を表示"):
    plot_correct_rate(problem_id_input)

# データベースの初期化関数
def reset_database():
    c.execute("DELETE FROM results")
    c.execute("DELETE FROM problems")
    c.execute("DELETE FROM problem_sets")
    conn.commit()
    
    # データ削除後、データベースを整理
    c.execute("VACUUM")
    conn.commit()

# **データベース初期化**
st.subheader("データベースの初期化")

if st.button("データベースを初期化する"):
    st.warning("本当に初期化しますか？ この操作は元に戻せません！")
    
    if st.button("はい、初期化する"):
        reset_database()
        st.success("データベースを初期化しました！")

        # **セッション情報をクリアして完全リフレッシュ**
        st.session_state.clear()
        st.rerun()

conn.close()