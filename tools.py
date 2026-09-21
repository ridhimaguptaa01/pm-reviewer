from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


def iter_document_blocks(document):
    """
    Yield paragraphs and tables in the same order
    they appear in the Word document.
    """

    if isinstance(document, DocumentObject):
        parent_element = document.element.body
    else:
        parent_element = document._tc

    for child in parent_element.iterchildren():

        if isinstance(child, CT_P):
            yield Paragraph(child, document)

        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def extract_docx_text(source) -> str:
    """
    Extract paragraphs and tables from a .docx
    while preserving their original document order.

    source may be:
    - a file path
    - a BytesIO object
    """

    document = Document(source)

    content = []

    for block in iter_document_blocks(document):

        if isinstance(block, Paragraph):

            text = block.text.strip()

            if text:
                content.append(text)

        elif isinstance(block, Table):

            content.append("[TABLE]")

            for row in block.rows:

                cells = [
                    cell.text.strip()
                    for cell in row.cells
                ]

                row_text = " | ".join(cells)

                if row_text.strip():
                    content.append(row_text)

            content.append("[END TABLE]")

    return "\n".join(content)


def read_supporting_document(file_path: str) -> str:

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            "Supporting document not found."
        )

    suffix = path.suffix.lower()

    if suffix in [".txt", ".md"]:

        return path.read_text(
            encoding="utf-8",
            errors="replace"
        )

    if suffix == ".docx":

        return extract_docx_text(path)

    raise ValueError(
        "Only .txt, .md, and .docx documents are supported."
    )