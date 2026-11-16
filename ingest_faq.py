"""FR-14: load data/faq.csv into the `faq` collection (1 row = 1 document)."""
import csv

from langchain_core.documents import Document

from config import FAQ_PATH
from ingest_common import write_collection


def load_faq() -> tuple[list[Document], list[str]]:
    docs, ids = [], []
    with open(FAQ_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doc_id = f"FAQ-{row['id']}"
            docs.append(
                Document(
                    page_content=f"Q: {row['question']}\nA: {row['answer']}",
                    metadata={"source": "FAQ", "doc_id": doc_id, "category": row["category"],
                              "title": row["question"]},
                )
            )
            ids.append(doc_id)
    return docs, ids


def main() -> None:
    write_collection("faq", *load_faq())


if __name__ == "__main__":
    main()
