"""FR-16: chunk data/telecom_guide.pdf (600 chars, 100 overlap) into the `guides` collection."""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from config import CHUNK_OVERLAP, CHUNK_SIZE, GUIDE_PDF_PATH
from ingest_common import write_collection


def load_guides() -> tuple[list[Document], list[str]]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    reader = PdfReader(GUIDE_PDF_PATH)
    docs, ids = [], []
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        for i, chunk in enumerate(splitter.split_text(text), start=1):
            doc_id = f"GUIDE-p{page_no}-c{i}"
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={"source": "GUIDE", "doc_id": doc_id, "page": page_no,
                              "title": f"{GUIDE_PDF_PATH.name}, page {page_no}"},
                )
            )
            ids.append(doc_id)
    return docs, ids


def main() -> None:
    write_collection("guides", *load_guides())


if __name__ == "__main__":
    main()
