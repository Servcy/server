from inbox.models import InboxItem
from inbox.repository.google import GoogleMailRepository


class InboxRepository:
    """
    Inbox Repository
    """

    @staticmethod
    def add_items(items: list[dict]) -> list[InboxItem]:
        """
        Add items to the inbox.
        """
        return InboxItem.objects.bulk_create([InboxItem(**item) for item in items])

    @staticmethod
    def archive_item(item_ids: list[int]) -> InboxItem:
        """
        Archive an item in the inbox.
        """
        return InboxItem.objects.filter(id__in=item_ids).update(is_archived=True)

    @staticmethod
    def delete_item(item_ids: list[int]) -> InboxItem:
        """
        Delete an item in the inbox.
        """
        return InboxItem.objects.filter(id__in=item_ids).update(is_deleted=True)
