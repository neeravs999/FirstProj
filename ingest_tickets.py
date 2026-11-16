"""FR-15: load resolved tickets from data/tickets.db into the `tickets` collection."""
import sqlite3

from langchain_core.documents import Document

from config import TICKETS_DB_PATH
from ingest_common import write_collection


def load_tickets() -> tuple[list[Document], list[str]]:
    con = sqlite3.connect(TICKETS_DB_PATH)
    try:
        rows = con.execute(
            "SELECT ticket_id, category, issue_type, description, resolution "
            "FROM tickets WHERE status = 'resolved' ORDER BY id"
        ).fetchall()
    finally:
        con.close()

    docs, ids = [], []
    for ticket_id, category, issue_type, description, resolution in rows:
        docs.append(
            Document(
                page_content=(f"Issue: {issue_type}\nCustomer report: {description}\n"
                              f"Resolution: {resolution}"),
                metadata={"source": "TICKET", "doc_id": ticket_id, "category": category,
                          "title": issue_type},
            )
        )
        ids.append(ticket_id)
    return docs, ids


def main() -> None:
    write_collection("tickets", *load_tickets())


if __name__ == "__main__":
    main()
