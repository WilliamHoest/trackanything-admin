from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Table, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

# Association table for many-to-many relationship between topics and keywords
topic_keywords = Table(
    'topic_keywords',
    Base.metadata,
    Column('topic_id', BigInteger, ForeignKey('topics.id'), primary_key=True),
    Column('keyword_id', BigInteger, ForeignKey('keywords.id'), primary_key=True)
)

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(Text, nullable=True)
    contact_email = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    brands = relationship("Brand", back_populates="profile", cascade="all, delete-orphan")
    integration_configs = relationship("IntegrationConfig", back_populates="profile", cascade="all, delete-orphan")

class Platform(Base):
    __tablename__ = "platforms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    mentions = relationship("Mention", back_populates="platform")

class Brand(Base):
    __tablename__ = "brands"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    profile = relationship("Profile", back_populates="brands")
    topics = relationship("Topic", back_populates="brand", cascade="all, delete-orphan")
    mentions = relationship("Mention", back_populates="brand", cascade="all, delete-orphan")

class Topic(Base):
    __tablename__ = "topics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    brand_id = Column(BigInteger, ForeignKey("brands.id"), nullable=False)
    name = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    brand = relationship("Brand", back_populates="topics")
    keywords = relationship("Keyword", secondary=topic_keywords, back_populates="topics")
    mentions = relationship("Mention", back_populates="topic", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    text = Column(Text, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    topics = relationship("Topic", secondary=topic_keywords, back_populates="keywords")

class Mention(Base):
    __tablename__ = "mentions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    caption = Column(Text, nullable=False)
    post_link = Column(Text, unique=True, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    platform_id = Column(BigInteger, ForeignKey("platforms.id"), nullable=False)
    brand_id = Column(BigInteger, ForeignKey("brands.id"), nullable=False)
    topic_id = Column(BigInteger, ForeignKey("topics.id"), nullable=False)
    read_status = Column(Boolean, default=False)
    notified_status = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    platform = relationship("Platform", back_populates="mentions")
    brand = relationship("Brand", back_populates="mentions")
    topic = relationship("Topic", back_populates="mentions")

class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    integration_name = Column(Text, nullable=False)
    webhook_url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    profile = relationship("Profile", back_populates="integration_configs")