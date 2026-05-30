import os

from sqlalchemy import create_engine, Column, String, Float, Integer, JSON, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Session
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(BASE_DIR, 'cara_sessions.db')}",
)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

class Base(DeclarativeBase):
    pass

class SessionEvent(Base):
    __tablename__ = "session_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    consumer_id = Column(String)
    event_type = Column(String)
    agent_name = Column(String, nullable=True)
    payload = Column(JSON)
    brainfry_score = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    agent_name = Column(String)
    status = Column(String)
    input_data = Column(JSON)
    output_data = Column(JSON, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    role = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

def get_db():
    with Session(engine) as session:
        yield session
