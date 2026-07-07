from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    BORROWER = "borrower"
    INVESTOR = "investor"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.BORROWER)
    balance = Column(Float, default=0.0)
    rating = Column(Float, default=0.0)  # рейтинг заёмщика/инвестора

    # Связи
    loan_requests = relationship("LoanRequest", back_populates="borrower")
    investments = relationship("Investment", back_populates="investor")

class LoanRequest(Base):
    __tablename__ = "loan_requests"
    id = Column(Integer, primary_key=True, index=True)
    borrower_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float, nullable=False)
    term_months = Column(Integer, nullable=False)  # срок в месяцах
    interest_rate = Column(Float, nullable=False)  # годовая ставка, например 12.5
    purpose = Column(String)  # цель займа
    status = Column(String, default="pending")  # pending, funded, closed
    created_at = Column(Date)

    borrower = relationship("User", back_populates="loan_requests")
    investments = relationship("Investment", back_populates="loan_request")

class Investment(Base):
    __tablename__ = "investments"
    id = Column(Integer, primary_key=True, index=True)
    investor_id = Column(Integer, ForeignKey("users.id"))
    loan_request_id = Column(Integer, ForeignKey("loan_requests.id"))
    amount = Column(Float, nullable=False)
    invested_at = Column(Date)

    investor = relationship("User", back_populates="investments")
    loan_request = relationship("LoanRequest", back_populates="investments")