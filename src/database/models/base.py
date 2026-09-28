from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    @classmethod
    def default_order_by(cls):
        """
        Return no default ordering for the base model.

        Returns:
            None: No default ordering.
        """
        return None
