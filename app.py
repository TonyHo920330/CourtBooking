from flask import Flask, request, jsonify, redirect, session,render_template
from datetime import timedelta,datetime
import requests
import os
import secrets

# 導入設定
from config.line import *
from config.database import get_db_connection

app = Flask(__name__)
app.config.from_pyfile('config/config.py')

@app.route("/",methods=["POST"])
def index():
    return 'OK', 200

# LINE Login 授權 URL
@app.route("/login")
def login():
    login_url = (
        f"https://access.line.me/oauth2/v2.1/authorize"
        f"?response_type=code&client_id={LINE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&scope=profile%20openid"
        f"&state=random_state_string"
    )
    return redirect(login_url)

# LINE 授權回傳
@app.route("/callback")
def callback():
    session.permanent = True
    code = request.args.get("code")
    if not code:
        return "未授權，請重新登入"

    token_url = "https://api.line.me/oauth2/v2.1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": LINE_CLIENT_ID,
        "client_secret": LINE_CLIENT_SECRET,
    }
    response = requests.post(token_url, headers=headers, data=data).json()
    
    if "access_token" not in response:
        return "授權失敗，請重新登入"

    access_token = response["access_token"]
    profile_url = "https://api.line.me/v2/profile"
    headers = {"Authorization": f"Bearer {access_token}"}
    profile = requests.get(profile_url, headers=headers).json()

    if "userId" not in profile or "displayName" not in profile:
        return "取得使用者資訊失敗"
    
    session["user_id"] = profile["userId"]
    session["display_name"] = profile["displayName"]
    return redirect("/welcome")

# 預約頁面
@app.route("/booking", methods=["GET"])
def booking():
    if "user_id" not in session:
        return redirect("/login")
    return render_template('booking.html')

# 查詢場地狀況
@app.route("/courtStatus",methods=["GET"])
def courtStatus():
    if "user_id" not in session:
        return redirect("/login")
    return render_template('courtStatus.html')

# 取得可預約時段
@app.route("/get-reserved-times", methods=["GET"])
def get_reserved_times():
    date = request.args.get("date")
    court_id = request.args.get("venue")
    if not date or not court_id:
        return jsonify({"error": "缺少必要參數"}), 400
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 查詢已預約時段
    cursor.execute(
        "SELECT reservation_time FROM Reservations WHERE reservation_date = %s AND court_id = %s",
        (date, court_id)
    )
    reserved_slots = '、'.join([row["reservation_time"] for row in cursor.fetchall()]).split('、')
    conn.close()

    return jsonify({"reserved_slots": reserved_slots})

# 送出訂單
@app.route("/submit-booking", methods=["POST"])
def submit_booking():
    data = request.json
    print("收到預約資料:", data)
    name = data['name']
    phone_number = data['phone']
    court_id = data['venue']
    price = data['price']
    time_date = data['date']
    time_slot = "、".join(data['timeSlots'])
    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO Reservations (user_id,name,phone_number,court_id,reservation_date, reservation_time,price) VALUES (%s, %s,%s, %s,%s, %s,%s)", (user_id,name,phone_number,court_id,time_date, time_slot,price))
    conn.commit()
    conn.close()
    return jsonify({"message": "預約成功！"}), 200

# 檢視個人預約紀錄
@app.route("/viewBookings",methods=["GET"])
def viewBookings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template('viewBookings.html')

# 取得個人預約紀錄
@app.route("/get-user-bookings", methods=["GET"])
def get_user_bookings():
    user_id = session["user_id"]
    """取得所有未來的預約（不包含過去的預約）"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT id,DATE_FORMAT(reservation_date, '%Y-%m-%d') AS reservation_date,reservation_time,court_id,name,price
        FROM Reservations
        WHERE reservation_date >= %s and user_id = %s
        ORDER BY reservation_date ASC
    """, (today,user_id,))
    
    bookings = cursor.fetchall()
    conn.close()
    return jsonify(bookings)

# 取消個人預約紀錄
@app.route("/cancel-booking", methods=["POST"])
def cancel_booking():
    """取消預約，當日的預約不可取消"""
    data = request.json
    booking_id = data.get("booking_id")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 確認該預約是否存在
    cursor.execute("SELECT DATE_FORMAT(reservation_date, '%Y-%m-%d') AS reservation_date FROM Reservations WHERE id = %s", (booking_id,))
    booking = cursor.fetchone()
    print(booking)
    
    if not booking:
        conn.close()
        return jsonify({"success": False, "message": "預約不存在"}), 400
    
    today = datetime.now().strftime("%Y-%m-%d")
    if booking["reservation_date"] == today:
        conn.close()
        return jsonify({"success": False, "message": "當日預約不可取消"}), 400

    # 刪除預約
    cursor.execute("DELETE FROM Reservations WHERE id = %s", (booking_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "預約已取消"})

# 登入後的歡迎頁面
@app.route("/welcome")
def welcome():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("welcome.html", username=session["display_name"])

# 整體性的預約表
@app.route("/bookingOverview")
def bookingOverview():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("bookingOverview.html")

# 取得球場狀況資訊
@app.route("/get-allcourts", methods=["GET"])
def get_all_courts():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, availability FROM Courts")
    courts = cursor.fetchall()
    conn.close()
    return jsonify([{ "id": court["id"], "name": court["name"], "availability": court["availability"] } for court in courts])

# 取得所有預約資訊
@app.route("/get-allBooking", methods=["GET"])
def get_all_booking():
    date = request.args.get("date")

    if not date:
        return jsonify({"error": "請提供日期"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 取得所有場地
    cursor.execute("SELECT id, name FROM Courts")
    courts = cursor.fetchall()

    # 取得當天所有預約紀錄
    cursor.execute("""
        SELECT court_id, reservation_time,name as customer FROM Reservations 
        WHERE reservation_date = %s
    """, (date,))
    bookings = cursor.fetchall()
    conn.close()

    # 整理資料
    booking_dict = {}
    for court in courts:
        booking_dict[court["id"]] = {
            "name": court["name"],
            "bookings": [],
            "user":[]
        }

    for booking in bookings:
        reservation_times = booking["reservation_time"].split("、")
        for time in reservation_times:
            booking_dict[booking["court_id"]]["bookings"].append(time)
            booking_dict[booking["court_id"]]["user"].append(booking["customer"])
    return jsonify(list(booking_dict.values()))

# 更新球場狀況
@app.route("/courtsUpdate")
def courts_update_page():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("courtsUpdate.html")

# 更新球場狀況方法
@app.route("/update-court-status", methods=["POST"])
def update_court_status():
    data = request.get_json()
    court_id = data.get("court_id")
    availability = data.get("availability")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE Courts SET availability = %s WHERE id = %s", (availability, court_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "修改成功！"})

if __name__ == "__main__":
    app.run(debug=True)
