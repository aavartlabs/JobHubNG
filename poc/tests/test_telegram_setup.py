from jobhub_poc.ops.telegram_setup import chats_from_updates


def test_lists_each_private_chat_once_with_a_name():
    updates = [
        {"message": {"chat": {"id": 4242, "type": "private", "first_name": "Ada", "username": "ada"}}},
        {"message": {"chat": {"id": -100, "type": "group", "title": "ops"}}},
        {"edited_message": {"chat": {"id": 4242, "type": "private", "first_name": "Ada", "username": "ada"}}},
        {"message": {"chat": {"id": 7, "type": "private"}}},
        {"my_chat_member": {}},
    ]
    assert chats_from_updates(updates) == [("4242", "Ada (@ada)"), ("7", "?")]
