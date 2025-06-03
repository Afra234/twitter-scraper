import os
import time
import threading
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import SessionLocal, engine, Base
import crud.accounts as accounts_crud
import crud.tweets as tweets_crud
from scraper.service import fetch_and_store_tweets
from flask_cors import CORS
import atexit

# ── Initialize DB ─────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

app = Flask(__name__)
CORS(app)
executor = ThreadPoolExecutor(max_workers=1)
scrape_lock = threading.Lock()

# ── Endpoints ─────────────────────────────────────────────────

@app.route("/subscribe/<username>", methods=["POST"])
def subscribe_account(username):
    with SessionLocal() as db:
        if accounts_crud.get_account(db, username):
            return jsonify({"error": "Account already subscribed"}), 400
        new_acct = accounts_crud.create_account(db, username)
        return jsonify({
            "message": f"Subscribed to {username}",
            "account": {"id": new_acct.id, "username": new_acct.username}
        })

@app.route("/unsubscribe/<username>", methods=["DELETE"])
def unsubscribe_account(username):
    with SessionLocal() as db:
        account = accounts_crud.get_account(db, username)
        if not account:
            return jsonify({"error": "Account not found"}), 404
        accounts_crud.delete_account(db, username)
        return jsonify({"message": f"Unsubscribed from {username}"})

@app.route("/accounts", methods=["GET"])
def list_accounts():
    with SessionLocal() as db:
        return jsonify([acct.username for acct in accounts_crud.list_accounts(db)])

@app.route("/refresh/<username>", methods=["POST"])
def manual_refresh(username):
    with SessionLocal() as db:
        if not accounts_crud.get_account(db, username):
            return jsonify({"error": "Account not subscribed"}), 404
    executor.submit(scrape_account_threadsafe, username)
    return jsonify({"message": f"Started tweet scraping for {username} in background"})

@app.route("/tweets", methods=["GET"])
def list_tweets():
    account = request.args.get("account")
    read_arg = request.args.get("read")
    read_filter = None if read_arg is None else read_arg.lower() == "true"
    with SessionLocal() as db:
        tweets = tweets_crud.list_tweets(db, account, read_filter)
        return jsonify([{
            "id": t.id,
            "account": t.account.username,
            "content": t.content,
            "timestamp": t.timestamp.isoformat(),
            "read": t.read,
        } for t in tweets])

@app.route("/tweet/<int:tweet_id>/read", methods=["PATCH"])
def mark_read(tweet_id):
    with SessionLocal() as db:
        tweet = tweets_crud.update_read_status(db, tweet_id, True)
        return jsonify({"message": "Tweet marked as read"} if tweet else {"error": "Tweet not found"}, 200 if tweet else 404)

@app.route("/tweet/<int:tweet_id>/unread", methods=["PATCH"])
def mark_unread(tweet_id):
    with SessionLocal() as db:
        tweet = tweets_crud.update_read_status(db, tweet_id, False)
        return jsonify({"message": "Tweet marked as unread"} if tweet else {"error": "Tweet not found"}, 200 if tweet else 404)

# ── Scrape Logic ──────────────────────────────────────────────

def scrape_account_threadsafe(username):
    with scrape_lock:
        try:
            print(f"⏳ Scraping @{username}...")
            count = fetch_and_store_tweets(username, 20)
            print(f"✅ Scraped {count} tweets for @{username}")
        except Exception as e:
            print(f"❌ Error while scraping @{username}: {e}")
        finally:
            time.sleep(60)  # enforce 60s gap before next scrape allowed

# ── Scrape Accounts One-by-One Every 60s ─────────────────────

def scrape_accounts_sequentially(usernames, index=0):
    if index >= len(usernames):
        return

    username = usernames[index]
    executor.submit(scrape_account_threadsafe, username)

    scheduler.add_job(
        lambda: scrape_accounts_sequentially(usernames, index + 1),
        trigger=IntervalTrigger(seconds=60),
        id=f"staggered_scrape_{index}",
        replace_existing=True
    )

# ── Master Scheduler Task ─────────────────────────────────────

def auto_fetch_all():
    with SessionLocal() as db:
        accounts = accounts_crud.list_accounts(db)
        usernames = [acct.username for acct in accounts]

    if not usernames:
        print("⚠️ No accounts to scrape.")
        return

    # Scrape first account immediately
    executor.submit(scrape_account_threadsafe, usernames[0])
    # Schedule rest
    scrape_accounts_sequentially(usernames, index=1)

# ── Start Scheduler ───────────────────────────────────────────

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=auto_fetch_all,
    trigger=IntervalTrigger(minutes=5),  # total loop reset every 5 min
    id="auto_fetch_job",
    replace_existing=True
)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ── Entry Point ───────────────────────────────────────────────

if __name__ == "__main__":
    print("→ Scheduler started: first account scrapes instantly, others every 60s.")
    app.run(debug=True, port=5000)
