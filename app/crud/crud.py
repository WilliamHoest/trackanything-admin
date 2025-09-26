from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from typing import List, Optional
from app.models.models import Profile, Brand, Topic, Keyword, Mention, Platform, IntegrationConfig
from app.schemas import (
    brand as brand_schemas,
    topic as topic_schemas,
    keyword as keyword_schemas,
    mention as mention_schemas,
    platform as platform_schemas,
    profile as profile_schemas,
    integration_config as integration_schemas
)
import uuid

# Profile CRUD
def get_profile(db: Session, profile_id: uuid.UUID) -> Optional[Profile]:
    return db.query(Profile).filter(Profile.id == profile_id).first()

def create_profile(db: Session, profile: profile_schemas.ProfileCreate, profile_id: uuid.UUID) -> Profile:
    db_profile = Profile(
        id=profile_id,
        company_name=profile.company_name,
        contact_email=profile.contact_email
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

def update_profile(db: Session, profile_id: uuid.UUID, profile: profile_schemas.ProfileUpdate) -> Optional[Profile]:
    db_profile = get_profile(db, profile_id)
    if db_profile:
        for field, value in profile.model_dump(exclude_unset=True).items():
            setattr(db_profile, field, value)
        db.commit()
        db.refresh(db_profile)
    return db_profile

# Brand CRUD
def get_brand(db: Session, brand_id: int) -> Optional[Brand]:
    return db.query(Brand).filter(Brand.id == brand_id).first()

def get_brands_by_profile(db: Session, profile_id: uuid.UUID) -> List[Brand]:
    return db.query(Brand).filter(Brand.profile_id == profile_id).all()

def create_brand(db: Session, brand: brand_schemas.BrandCreate, profile_id: uuid.UUID) -> Brand:
    db_brand = Brand(
        name=brand.name,
        profile_id=profile_id
    )
    db.add(db_brand)
    db.commit()
    db.refresh(db_brand)
    return db_brand

def update_brand(db: Session, brand_id: int, brand: brand_schemas.BrandUpdate) -> Optional[Brand]:
    db_brand = get_brand(db, brand_id)
    if db_brand:
        for field, value in brand.model_dump(exclude_unset=True).items():
            setattr(db_brand, field, value)
        db.commit()
        db.refresh(db_brand)
    return db_brand

def delete_brand(db: Session, brand_id: int) -> bool:
    db_brand = get_brand(db, brand_id)
    if db_brand:
        db.delete(db_brand)
        db.commit()
        return True
    return False

# Topic CRUD
def get_topic(db: Session, topic_id: int) -> Optional[Topic]:
    return db.query(Topic).options(joinedload(Topic.keywords)).filter(Topic.id == topic_id).first()

def get_topics_by_brand(db: Session, brand_id: int) -> List[Topic]:
    return db.query(Topic).options(joinedload(Topic.keywords)).filter(Topic.brand_id == brand_id).all()

def create_topic(db: Session, topic: topic_schemas.TopicCreate, brand_id: int) -> Topic:
    db_topic = Topic(
        name=topic.name,
        is_active=topic.is_active,
        brand_id=brand_id
    )
    
    # Add keywords if provided
    if topic.keyword_ids:
        keywords = db.query(Keyword).filter(Keyword.id.in_(topic.keyword_ids)).all()
        db_topic.keywords = keywords
    
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    return db_topic

def update_topic(db: Session, topic_id: int, topic: topic_schemas.TopicUpdate) -> Optional[Topic]:
    db_topic = get_topic(db, topic_id)
    if db_topic:
        # Update basic fields
        for field, value in topic.model_dump(exclude_unset=True, exclude={'keyword_ids'}).items():
            setattr(db_topic, field, value)
        
        # Update keywords if provided
        if topic.keyword_ids is not None:
            keywords = db.query(Keyword).filter(Keyword.id.in_(topic.keyword_ids)).all()
            db_topic.keywords = keywords
            
        db.commit()
        db.refresh(db_topic)
    return db_topic

def delete_topic(db: Session, topic_id: int) -> bool:
    db_topic = get_topic(db, topic_id)
    if db_topic:
        db.delete(db_topic)
        db.commit()
        return True
    return False

# Keyword CRUD
def get_keyword(db: Session, keyword_id: int) -> Optional[Keyword]:
    return db.query(Keyword).filter(Keyword.id == keyword_id).first()

def get_keyword_by_text(db: Session, text: str) -> Optional[Keyword]:
    return db.query(Keyword).filter(Keyword.text == text).first()

def get_keywords(db: Session, skip: int = 0, limit: int = 100) -> List[Keyword]:
    return db.query(Keyword).offset(skip).limit(limit).all()

def create_keyword(db: Session, keyword: keyword_schemas.KeywordCreate) -> Keyword:
    # Check if keyword already exists
    existing = get_keyword_by_text(db, keyword.text)
    if existing:
        return existing
    
    db_keyword = Keyword(text=keyword.text)
    db.add(db_keyword)
    db.commit()
    db.refresh(db_keyword)
    return db_keyword

def delete_keyword(db: Session, keyword_id: int) -> bool:
    db_keyword = get_keyword(db, keyword_id)
    if db_keyword:
        db.delete(db_keyword)
        db.commit()
        return True
    return False

# Platform CRUD
def get_platform(db: Session, platform_id: int) -> Optional[Platform]:
    return db.query(Platform).filter(Platform.id == platform_id).first()

def get_platform_by_name(db: Session, name: str) -> Optional[Platform]:
    return db.query(Platform).filter(Platform.name == name).first()

def get_platforms(db: Session) -> List[Platform]:
    return db.query(Platform).all()

def create_platform(db: Session, platform: platform_schemas.PlatformCreate) -> Platform:
    # Check if platform already exists
    existing = get_platform_by_name(db, platform.name)
    if existing:
        return existing
        
    db_platform = Platform(name=platform.name)
    db.add(db_platform)
    db.commit()
    db.refresh(db_platform)
    return db_platform

# Mention CRUD
def get_mention(db: Session, mention_id: int) -> Optional[Mention]:
    return db.query(Mention).options(
        joinedload(Mention.platform),
        joinedload(Mention.brand),
        joinedload(Mention.topic)
    ).filter(Mention.id == mention_id).first()

def get_mentions_by_brand(db: Session, brand_id: int, skip: int = 0, limit: int = 100) -> List[Mention]:
    return db.query(Mention).options(
        joinedload(Mention.platform),
        joinedload(Mention.topic)
    ).filter(Mention.brand_id == brand_id).offset(skip).limit(limit).all()

def get_mention_by_link(db: Session, post_link: str) -> Optional[Mention]:
    return db.query(Mention).filter(Mention.post_link == post_link).first()

def create_mention(db: Session, mention: mention_schemas.MentionCreate) -> Mention:
    # Check if mention already exists
    existing = get_mention_by_link(db, mention.post_link)
    if existing:
        return existing
        
    db_mention = Mention(
        caption=mention.caption,
        post_link=mention.post_link,
        published_at=mention.published_at,
        platform_id=mention.platform_id,
        brand_id=mention.brand_id,
        topic_id=mention.topic_id,
        read_status=mention.read_status,
        notified_status=mention.notified_status
    )
    db.add(db_mention)
    db.commit()
    db.refresh(db_mention)
    return db_mention

def update_mention(db: Session, mention_id: int, mention: mention_schemas.MentionUpdate) -> Optional[Mention]:
    db_mention = get_mention(db, mention_id)
    if db_mention:
        for field, value in mention.model_dump(exclude_unset=True).items():
            setattr(db_mention, field, value)
        db.commit()
        db.refresh(db_mention)
    return db_mention

def delete_mention(db: Session, mention_id: int) -> bool:
    db_mention = get_mention(db, mention_id)
    if db_mention:
        db.delete(db_mention)
        db.commit()
        return True
    return False

# Integration Config CRUD
def get_integration_configs_by_profile(db: Session, profile_id: uuid.UUID) -> List[IntegrationConfig]:
    return db.query(IntegrationConfig).filter(IntegrationConfig.profile_id == profile_id).all()

def create_integration_config(db: Session, config: integration_schemas.IntegrationConfigCreate, profile_id: uuid.UUID) -> IntegrationConfig:
    db_config = IntegrationConfig(
        integration_name=config.integration_name,
        webhook_url=config.webhook_url,
        is_active=config.is_active,
        profile_id=profile_id
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def get_webhook_config_by_profile(db: Session, profile_id: uuid.UUID) -> Optional[IntegrationConfig]:
    """Get active webhook configuration for a profile"""
    return db.query(IntegrationConfig).filter(
        IntegrationConfig.profile_id == profile_id,
        IntegrationConfig.is_active == True,
        IntegrationConfig.webhook_url.isnot(None)
    ).first()

# Additional Mention CRUD for digest functionality
def get_unsent_mentions_by_brand(db: Session, brand_id: int) -> List[Mention]:
    """Get all mentions for a brand that haven't been sent in a notification"""
    return db.query(Mention).options(
        joinedload(Mention.platform),
        joinedload(Mention.topic),
        joinedload(Mention.brand)
    ).filter(
        Mention.brand_id == brand_id,
        Mention.notified_status == False
    ).all()

def update_mention_notified_status(db: Session, mention_id: int, status: bool) -> bool:
    """Update the notified_status for a specific mention"""
    db_mention = db.query(Mention).filter(Mention.id == mention_id).first()
    if db_mention:
        db_mention.notified_status = status
        db.commit()
        return True
    return False

def get_latest_mentions_by_profile(db: Session, profile_id: uuid.UUID, limit: int = 10) -> List[Mention]:
    """Get the latest mentions for a profile across all their brands"""
    return db.query(Mention).options(
        joinedload(Mention.platform),
        joinedload(Mention.topic),
        joinedload(Mention.brand)
    ).join(Brand).filter(
        Brand.profile_id == profile_id
    ).order_by(Mention.published_at.desc()).limit(limit).all()