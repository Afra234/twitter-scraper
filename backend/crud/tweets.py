# crud/tweets.py
from sqlalchemy.orm import Session
from models import Tweet, Account
from datetime import datetime
from typing import Optional, List

def create_tweet(db: Session, account: Account, content: str, timestamp: Optional[datetime] = None):
    tweet = Tweet(
        account=account,
        content=content,
        timestamp=timestamp or datetime.utcnow()
    )
    db.add(tweet)
    db.commit()
    db.refresh(tweet)
    return tweet

def tweet_exists(db: Session, account: Account, content: str) -> bool:
    return db.query(Tweet).filter(
        Tweet.account_id == account.id,
        Tweet.content == content
    ).first() is not None

def list_tweets(db: Session, account_username: Optional[str] = None, read: Optional[bool] = None) -> List[Tweet]:
    query = db.query(Tweet)
    if account_username:
        query = query.join(Account).filter(Account.username == account_username)
    if read is not None:
        query = query.filter(Tweet.read == read)
    return query.order_by(Tweet.timestamp.desc()).all()

def update_read_status(db: Session, tweet_id: int, read: bool):
    tweet = db.query(Tweet).filter(Tweet.id == tweet_id).first()
    if not tweet:
        return None
    tweet.read = read
    db.commit()
    db.refresh(tweet)
    return tweet
