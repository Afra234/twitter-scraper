# crud/accounts.py
from sqlalchemy.orm import Session
from models import Account

def get_account(db: Session, username: str):
    return db.query(Account).filter(Account.username == username).first()

def create_account(db: Session, username: str):
    account = Account(username=username)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account

def delete_account(db: Session, username: str):
    account = get_account(db, username)
    if account:
        db.delete(account)
        db.commit()

def list_accounts(db: Session):
    return db.query(Account).all()
