import streamlit as st
import random
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import requests
from dotenv import load_dotenv
import bcrypt
import stripe

load_dotenv()

# -------------------------
# Configuration
# -------------------------
DATA_FILE = "users.json"
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_API")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# -------------------------
# Helper Functions
# -------------------------
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            users = {}
            for username, info in data.items():
                user = User(username, info["account_type"], info.get("hashed_password"))
                user.balance = info["balance"]
                user.trades = [Trade(**t) for t in info.get("trades", [])]
                user.history = info.get("history", [])
                user.hashed_password = info.get("hashed_password", None)
                user.premium_unlocked = info.get("premium_unlocked", False)
                users[username] = user
            return users
    return {}

def save_users(users):
    data = {
        username: {
            "account_type": user.account_type,
            "balance": user.balance,
            "trades": [vars(t) for t in user.trades],
            "history": user.history,
            "hashed_password": user.hashed_password,
            "premium_unlocked": user.premium_unlocked,
        } for username, user in users.items()
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def send_email(recipient, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = recipient
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

def get_real_market_trend():
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=SPY&interval=1min&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        times = list(data["Time Series (1min)"].keys())
        latest = data["Time Series (1min)"][times[0]]
        prev = data["Time Series (1min)"][times[1]]
        return "up" if float(latest["4. close"]) > float(prev["4. close"]) else "down"
    except:
        return random.choice(["up", "down"])

def create_stripe_checkout_session(user_email):
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': 'Trade with Laiba Premium',
                },
                'unit_amount': 500,  # $5.00 in cents
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url="https://trade-with-laiba.streamlit.app/?status=success",
        cancel_url="https://trade-with-laiba.streamlit.app/?status=cancel",
        customer_email=user_email,
        metadata={'username': st.session_state.user.username},
    )
    return session.url

def check_payment_and_unlock(username):
    try:
        payments = stripe.payment_intents.list(limit=20)
        for payment in payments.data:
            if payment.status == 'succeeded' and payment.metadata.get('username') == username:
                user = USERS.get(username)
                if user and not user.premium_unlocked:
                    user.premium_unlocked = True
                    user.account_type = "real"
                    user.balance = 100
                    save_users(USERS)
                    return True
        return False
    except Exception as e:
        st.error(f"Stripe API error: {e}")
        return False

# -------------------------
# OOP Classes
# -------------------------
class User:
    def __init__(self, username, account_type="demo", hashed_password=None):
        self.username = username
        self.account_type = account_type
        self.hashed_password = hashed_password
        self.balance = 10000 if account_type == "demo" else 0
        self.trades = []
        self.history = []
        self.premium_unlocked = False

    def update_balance(self, amount):
        self.balance += amount
        self.history.append({"timestamp": str(datetime.now()), "balance": self.balance})

    def get_level(self):
        count = len(self.trades)
        if count >= 31:
            return "🌟 Pro"
        elif count >= 11:
            return "🔥 Intermediate"
        else:
            return "🔰 Beginner"

class Trade:
    def __init__(self, amount, prediction, result):
        self.amount = amount
        self.prediction = prediction
        self.result = result

    def is_win(self):
        return self.prediction == self.result

class TradingSystem:
    def __init__(self, user):
        self.user = user

    def get_market_result(self):
        return get_real_market_trend()

    def place_trade(self, amount, prediction):
        result = self.get_market_result()
        trade = Trade(amount, prediction, result)
        self.user.trades.append(trade)

        if trade.is_win():
            win_amount = amount * 0.9
            self.user.update_balance(win_amount)
            return True, result, win_amount
        else:
            self.user.update_balance(-amount)
            return False, result, -amount

# -------------------------
# Load Users
# -------------------------
USERS = load_users()

# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Trade with Laiba", layout="centered", page_icon="📊")
st.title("📊 Trade with Laiba")

username = st.text_input("Enter your username")
password = st.text_input("Enter password", type="password")
email = st.text_input("Enter your email (for notifications)")
account_type = st.selectbox("Select Account Type", ["demo", "real"])

if st.button("Login / Create Account"):
    if username not in USERS:
        if not password:
            st.error("Please enter a password to register.")
        else:
            hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            USERS[username] = User(username, account_type, hashed_password=hashed_pw)
            save_users(USERS)
            st.session_state.user = USERS[username]
            st.session_state.email = email
            st.success(f"Account created for {username}")
    else:
        user = USERS[username]
        if user.hashed_password and bcrypt.checkpw(password.encode(), user.hashed_password.encode()):
            st.session_state.user = user
            st.session_state.email = email
            st.success(f"Welcome back, {username}")
        else:
            st.error("Incorrect password.")
    save_users(USERS)

if "user" in st.session_state:
    user = st.session_state.user
    trader = TradingSystem(user)

    st.subheader("Your Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"👤 **{user.username}** ({user.get_level()})")
        st.success(f"💰 Balance: ${user.balance:.2f}")
    with col2:
        st.write(f"🧾 Account: {user.account_type.title()}")
        if user.premium_unlocked:
            st.success("✅ Premium Features Unlocked")
        else:
            st.warning("🔒 Premium Features Locked")

    st.markdown("---")

    st.subheader("📈 Make a Trade")
    if user.balance < 1.0:
        st.warning("❌ You need at least $1.00 to trade.")
    else:
        amount = st.number_input("Amount", min_value=1.0, max_value=float(user.balance), value=min(10.0, float(user.balance)))
        prediction = st.radio("Prediction", ["up", "down"])
        if st.button("Place Trade"):
            won, result, delta = trader.place_trade(amount, prediction)
            if won:
                st.success(f"✅ Won! Market went {result}. Earned ${delta:.2f}.")
            else:
                st.error(f"❌ Lost. Market went {result}. Lost ${-delta:.2f}.")
            save_users(USERS)

    st.markdown("---")
    st.subheader("📊 Trade History")
    for i, trade in enumerate(user.trades[::-1][:10], 1):
        st.write(f"{i}. ${trade.amount} | {trade.prediction} -> {trade.result} | {'✅ Win' if trade.is_win() else '❌ Loss'}")

    if user.history:
        df = pd.DataFrame(user.history)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["balance"] = df["balance"].astype(float)
        st.line_chart(df.set_index("timestamp"))

    st.markdown("---")
    st.subheader("🏆 Leaderboard")
    top_users = sorted(USERS.values(), key=lambda u: u.balance, reverse=True)[:5]
    for i, u in enumerate(top_users, 1):
        st.write(f"{i}. {u.username} | ${u.balance:.2f} | {u.get_level()}")

    st.markdown("---")
    st.subheader("🔓 Unlock Real Account (Stripe Payment)")

    if not user.premium_unlocked:
        if not email:
            st.info("Please enter your email above for payment receipt.")
        else:
            if st.button("Unlock Now with Stripe ($5)"):
                try:
                    checkout_url = create_stripe_checkout_session(email)
                    st.markdown(f"[Click here to pay via Stripe]({checkout_url})")
                    st.info("After payment, please click the 'Verify Payment' button below to unlock premium.")
                except Exception as e:
                    st.error(f"Error creating Stripe session: {e}")

        if st.button("Verify Payment"):
            if check_payment_and_unlock(user.username):
                st.success("Payment confirmed! Premium features unlocked.")
            else:
                st.warning("No payment found yet. Please complete payment on Stripe.")
    else:
        st.info("✅ Already Premium.")

else:
    st.info("👆 Please log in to access your dashboard.")
