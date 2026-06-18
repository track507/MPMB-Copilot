from app.model.orm import Message, MessageFeedback


def test_table_name() -> None:
    assert MessageFeedback.__tablename__ == "message_feedback"


def test_message_id_is_unique_and_not_null() -> None:
    col = MessageFeedback.__table__.c.message_id
    assert col.unique is True
    assert col.nullable is False


def test_note_is_nullable() -> None:
    assert MessageFeedback.__table__.c.note.nullable is True


def test_message_has_one_to_one_feedback() -> None:
    rel = Message.__mapper__.relationships["feedback"]
    assert rel.uselist is False
