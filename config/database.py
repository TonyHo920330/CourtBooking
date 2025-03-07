# config/database.py
import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="192.168.101.128",
        user="remote_user",
        password="XXXXXXXXX",
        database="LineBot"
    )

