import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AccessType(str, enum.Enum):
    whitelist = "whitelist"
    referral = "referral"


class StaffRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    moderator = "moderator"


class GiveawayType(str, enum.Enum):
    photo = "photo"
    text = "text"
    complex = "complex"
    manager = "manager"
    reward = "reward"
    randomizer = "randomizer"


class GiveawayStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    closed = "closed"


class ParticipationStatus(str, enum.Enum):
    in_progress = "in_progress"
    on_review = "on_review"
    approved = "approved"
    rejected = "rejected"


class ModerationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rework = "rework"
    rejected_permanently = "rejected_permanently"


class GiftType(str, enum.Enum):
    gift = "gift"
    account = "account"


class UserGiftStatus(str, enum.Enum):
    available = "available"
    withdrawn = "withdrawn"


class WithdrawalStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


class TicketStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    star_balance: Mapped[int] = mapped_column(Integer, default=0)
    reserved_stars: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_streak_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    approved_tasks_count: Mapped[int] = mapped_column(Integer, default=0)
    access_type: Mapped[Optional[AccessType]] = mapped_column(Enum(AccessType), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_chest_claim: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    whitelist_entry: Mapped[Optional["WhitelistEntry"]] = relationship(back_populates="user", uselist=False)
    staff_role: Mapped[Optional["StaffRoleEntry"]] = relationship(back_populates="user", uselist=False)


class WhitelistEntry(Base):
    __tablename__ = "whitelist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="whitelist_entry")


class PendingWhitelist(Base):
    __tablename__ = "whitelist_pending"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffRoleEntry(Base):
    __tablename__ = "staff_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    role: Mapped[StaffRole] = mapped_column(Enum(StaffRole))

    user: Mapped["User"] = relationship(back_populates="staff_role")


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referrer_id", name="uq_referrer_one_friend"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    stars_awarded: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Giveaway(Base):
    __tablename__ = "giveaways"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    giveaway_type: Mapped[GiveawayType] = mapped_column(Enum(GiveawayType))
    description: Mapped[str] = mapped_column(Text, default="")
    media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[GiveawayStatus] = mapped_column(Enum(GiveawayStatus), default=GiveawayStatus.draft)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    star_reward: Mapped[int] = mapped_column(Integer, default=10)
    star_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winner_participation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("participations.id"), nullable=True
    )
    draw_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    channels: Mapped[list["GiveawayChannel"]] = relationship(back_populates="giveaway")
    steps: Mapped[list["TaskStep"]] = relationship(back_populates="giveaway", order_by="TaskStep.step_order")


class GiveawayChannel(Base):
    __tablename__ = "giveaway_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))

    giveaway: Mapped["Giveaway"] = relationship(back_populates="channels")
    channel: Mapped["Channel"] = relationship()


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id", ondelete="CASCADE"))
    step_order: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False)

    giveaway: Mapped["Giveaway"] = relationship(back_populates="steps")


class Participation(Base):
    __tablename__ = "participations"
    __table_args__ = (UniqueConstraint("user_id", "giveaway_id", name="uq_user_giveaway"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"))
    status: Mapped[ParticipationStatus] = mapped_column(
        Enum(ParticipationStatus), default=ParticipationStatus.in_progress
    )
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    step_answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_winner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GiveawayProposal(Base):
    __tablename__ = "giveaway_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    giveaway_type: Mapped[GiveawayType] = mapped_column(Enum(GiveawayType))
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    media: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[ModerationStatus] = mapped_column(Enum(ModerationStatus), default=ModerationStatus.pending)
    content_hash: Mapped[str] = mapped_column(String(64))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[ModerationStatus] = mapped_column(Enum(ModerationStatus), default=ModerationStatus.pending)
    content_hash: Mapped[str] = mapped_column(String(64))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModerationLog(Base):
    __tablename__ = "moderation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentHash(Base):
    __tablename__ = "content_hashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    star_cost: Mapped[int] = mapped_column(Integer)
    gift_type: Mapped[GiftType] = mapped_column(Enum(GiftType))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GiftDesign(Base):
    __tablename__ = "gift_designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    preview_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserGift(Base):
    __tablename__ = "user_gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    gift_id: Mapped[Optional[int]] = mapped_column(ForeignKey("gifts.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    star_cost: Mapped[int] = mapped_column(Integer)
    status: Mapped[UserGiftStatus] = mapped_column(Enum(UserGiftStatus), default=UserGiftStatus.available)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user_gift_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_gifts.id"), nullable=True)
    gift_id: Mapped[Optional[int]] = mapped_column(ForeignKey("gifts.id"), nullable=True)
    gift_design_id: Mapped[Optional[int]] = mapped_column(ForeignKey("gift_designs.id"), nullable=True)
    stars_amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[WithdrawalStatus] = mapped_column(Enum(WithdrawalStatus), default=WithdrawalStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StarTransaction(Base):
    __tablename__ = "star_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    tx_type: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserDraft(Base):
    __tablename__ = "user_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    draft_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SnoozeReminder(Base):
    __tablename__ = "snooze_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    participation_id: Mapped[int] = mapped_column(ForeignKey("participations.id"))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class GiveawayTemplate(Base):
    __tablename__ = "giveaway_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    giveaway_type: Mapped[GiveawayType] = mapped_column(Enum(GiveawayType))
    default_deadline_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    star_reward: Mapped[int] = mapped_column(Integer, default=10)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BroadcastLog(Base):
    __tablename__ = "broadcast_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
