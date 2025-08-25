import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///profitbliss.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Gmail SMTP Settings
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")   # your Gmail
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")   # your Gmail App Password
