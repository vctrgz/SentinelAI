import sqlite3

def query_logs(query):
    conn = sqlite3.connect("logs.db")
    cursor = conn.cursor()

    cursor.execute(query)
    result = cursor.fetchall()

    conn.close()
    return result